"""Always-on mic + wake-word + command/message router.

Two wake modes:
  - transcription  (default): every voiced segment is transcribed; if it
    starts with "Regis" or "Hey Regis", treat as wake. Works with the real
    character name immediately; slight extra latency per segment.
  - wake_word: openWakeWord pre-trained model (default "hey_jarvis").
    Lower latency, but requires custom model training for "Hey Regis".

Pipeline (transcription mode):
    mic -> voiced segments -> STT -> contains "regis"?
                                       yes + has message -> classify/route now
                                       yes alone         -> arm for next segment
                                       no                -> ignore

Pipeline (wake_word mode):
    mic -> packets -> wake-word detector -> voiced segments -> [armed?] -> STT -> classify/route

Usage:
    cd apps && source inference/.venv/bin/activate
    python -m mic_listener.run                                 # transcription mode, wake = "regis"
    DAYBOOK_WAKE_PHRASE=regis python -m mic_listener.run       # configurable phrase
    DAYBOOK_WAKE_MODE=wake_word python -m mic_listener.run     # use openWakeWord instead
    python -m mic_listener.run --no-speak                      # don't TTS replies
    python -m mic_listener.run --armed-seconds 10              # widen post-wake window
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

APPS_DIR = Path(__file__).resolve().parent.parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for _p in (APPS_DIR, INFERENCE_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from mic_listener.listener import AudioChunk, ContinuousMicListener  # noqa: E402
from wake_word import (  # noqa: E402
    CommandIntent,
    VoiceWakeWordDetector,
    WakeEvent,
    classify_intent,
)
from wake_word import handlers as wake_handlers  # noqa: E402

logger = logging.getLogger("mic_listener.run")

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
DEFAULT_WAKE_WORD = os.environ.get("DAYBOOK_WAKE_WORD", "hey_jarvis")
DEFAULT_WAKE_PHRASE = os.environ.get("DAYBOOK_WAKE_PHRASE", "regis")
# Force the MacBook built-in mic instead of the BT headset mic (which would be
# narrowband telephony-grade and wreck STT accuracy). sounddevice accepts a
# substring match of the device name. Override with DAYBOOK_INPUT_DEVICE=...
# (an exact name string or int index, or '' to use the OS default).
_INPUT_DEVICE_ENV = os.environ.get("DAYBOOK_INPUT_DEVICE", "MacBook Pro Microphone")
DEFAULT_INPUT_DEVICE: int | str | None = (
    None if _INPUT_DEVICE_ENV.strip() == "" else _INPUT_DEVICE_ENV
)
# Default mode is wake_word for now — uses pre-trained "hey_jarvis" model. When
# a custom "Hey Regis" model is trained (see apps/inference/wake_word/training/),
# point DAYBOOK_WAKE_WORD_MODEL_PATH at the .onnx file and set DAYBOOK_WAKE_WORD=hey_regis.
# Switch to DAYBOOK_WAKE_MODE=transcription for the whisper-based fallback.
DEFAULT_WAKE_MODE = os.environ.get("DAYBOOK_WAKE_MODE", "wake_word")
DEFAULT_ARMED_SECONDS = 8.0
DEFAULT_THRESHOLD = 0.5
# After a successful exchange, stay armed for this many seconds so the user can
# continue speaking without saying the wake word again. Standard "follow-up mode"
# like Alexa / Google. Tuned to feel like natural back-and-forth without the
# system reacting to background noise after long pauses.
DEFAULT_FOLLOWUP_SECONDS = float(os.environ.get("DAYBOOK_FOLLOWUP_SECONDS", "30"))
# Minimum loudness to count as a barge-in attempt while Regis is speaking. Below
# this is treated as ambient noise / Regis's own voice bleeding into the mic.
BARGE_IN_RMS_THRESHOLD = 0.012


def extract_message_after_wake(text: str, wake_phrase: str) -> str | None:
    """If `text` starts with optional 'hey' + `wake_phrase`, return whatever
    follows. Returns None if no wake phrase detected. Returns '' if the wake
    phrase appeared alone (arm for next segment).

    Conservative: wake phrase must be the first word OR follow 'hey'.
    Avoids mid-sentence false triggers like 'I was telling Regis about it.'
    """
    if not text:
        return None
    words = text.strip().split()
    if not words:
        return None

    def _norm(w: str) -> str:
        return w.lower().strip(",.!?:;-\"'`")

    wake_norm = wake_phrase.lower()
    first = _norm(words[0])

    # Case: "Hey Regis ..."
    if first == "hey" and len(words) >= 2 and _norm(words[1]) == wake_norm:
        remainder = " ".join(words[2:]).strip(",.!? ").strip()
        return remainder

    # Case: "Regis ..."
    if first == wake_norm:
        remainder = " ".join(words[1:]).strip(",.!? ").strip()
        return remainder

    return None


def _transcribe_segment(audio: np.ndarray, sample_rate: int) -> str:
    """Use the streaming STT backend on a captured voiced segment."""
    from llm.stt_streaming import _transcribe_chunk  # local import to defer model load

    if audio.dtype == np.int16:
        audio_f = audio.astype(np.float32) / 32768.0
    else:
        audio_f = audio.astype(np.float32, copy=False)
    if sample_rate != 16000:
        ratio = 16000 / float(sample_rate)
        target_len = int(round(audio_f.shape[0] * ratio))
        if target_len > 0:
            x_old = np.linspace(0.0, 1.0, num=audio_f.shape[0], endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
            audio_f = np.interp(x_new, x_old, audio_f).astype(np.float32)
    return _transcribe_chunk(audio_f, language="en").strip()


def _maybe_speak(text: str, *, speak_enabled: bool) -> None:
    """Speak `text` aloud in a background thread so the listener stays responsive
    for barge-in. Returns immediately; the speak call runs until completion or
    interruption via inference.audio.stop_speaking()."""
    if not text or not speak_enabled:
        if text:
            print(f"Regis: {text}")
        return

    print(f"Regis: {text}")

    def _bg() -> None:
        try:
            from inference.audio import speak_streaming

            speak_streaming(text, mode="companion")
        except Exception as e:
            logger.warning("TTS failed: %s", e)

    threading.Thread(target=_bg, daemon=True, name="regis-speak").start()


class TurnRunner:
    """Runs one turn at a time in a dedicated thread. New turns cancel old ones.

    The mic listener worker thread MUST NOT block on turn processing — that
    would freeze packet callbacks and kill barge-in detection. submit_turn()
    returns immediately; the turn runs in a daemon thread with its own asyncio
    loop (when streaming) so the listener stays responsive at ~80ms packet
    granularity.

    Cancellation strategy: a new turn calls stop_speaking() to signal the
    in-flight speak loop to bail. The old TTS chain exits cleanly (handler
    persists partial assistant text via GeneratorExit path). The new turn
    thread starts immediately without waiting on join — best-effort cancel.
    """

    def __init__(
        self,
        *,
        user_id: str,
        conversation_box: dict,
        speak_enabled: bool,
        streaming: bool,
    ) -> None:
        self.user_id = user_id
        self.conversation_box = conversation_box
        self.speak_enabled = speak_enabled
        self.streaming = streaming
        self._lock = threading.Lock()
        self._current_thread: threading.Thread | None = None
        self._on_complete: list[threading.Event] = []

    def submit_turn(self, user_text: str, *, on_complete: callable | None = None) -> None:
        """Submit a turn; cancel any in-flight one. Returns immediately."""
        with self._lock:
            prior = self._current_thread
            if prior is not None and prior.is_alive():
                logger.info("turn cancelled by new turn: %r", user_text[:60])
                try:
                    from inference.audio import stop_speaking

                    stop_speaking()
                except Exception:
                    logger.debug("stop_speaking during cancel failed", exc_info=True)
            t = threading.Thread(
                target=self._run_one,
                args=(user_text, on_complete),
                name=f"turn-{datetime.now().strftime('%H%M%S')}",
                daemon=True,
            )
            self._current_thread = t
            t.start()

    def _run_one(self, user_text: str, on_complete: callable | None) -> None:
        try:
            if self.streaming:
                asyncio.run(self._stream_turn(user_text))
            else:
                self._sync_turn(user_text)
        except Exception:
            logger.exception("turn processing failed: %r", user_text[:80])
        finally:
            if on_complete is not None:
                try:
                    on_complete()
                except Exception:
                    logger.exception("turn on_complete callback failed")

    def _resolve_conversation_id(self) -> str | None:
        """Look up or create the active conversation. Returns None on failure."""
        try:
            from chat.conversation import (
                create_conversation,
                most_recent_conversation,
            )
        except Exception:
            logger.exception("chat.conversation import failed")
            return None

        conv_id = self.conversation_box.get("id")
        if not conv_id:
            conv_id = most_recent_conversation(
                user_id=self.user_id
            ) or create_conversation(user_id=self.user_id)
            self.conversation_box["id"] = conv_id
        return conv_id

    async def _stream_turn(self, user_text: str) -> None:
        """Streaming turn: async chat + async TTS. Honors barge-in via
        stop_speaking() — speak_streaming_async exits at chunk boundary,
        which closes the tee() generator, which triggers GeneratorExit in
        handle_user_message_streaming and persists the partial message."""
        try:
            from chat.handler import handle_user_message_streaming
            from inference.audio import speak_streaming_async
        except Exception:
            logger.exception("streaming chat import failed; falling back to sync")
            self._sync_turn(user_text)
            return

        conv_id = self._resolve_conversation_id()
        if conv_id is None:
            return

        print("Regis: ", end="", flush=True)

        text_stream = handle_user_message_streaming(
            user_id=self.user_id,
            conversation_id=conv_id,
            user_text=user_text,
        )

        try:
            if self.speak_enabled:
                async def tee():
                    async for delta in text_stream:
                        print(delta, end="", flush=True)
                        yield delta

                await speak_streaming_async(tee(), mode="companion")
            else:
                async for delta in text_stream:
                    print(delta, end="", flush=True)
        finally:
            print()

    def _sync_turn(self, user_text: str) -> None:
        """Non-streaming fallback path."""
        try:
            from chat.handler import handle_user_message
        except Exception:
            logger.exception("chat.handler import failed")
            return

        conv_id = self._resolve_conversation_id()
        if conv_id is None:
            return

        try:
            resp = handle_user_message(
                user_id=self.user_id,
                conversation_id=conv_id,
                user_text=user_text,
            )
        except Exception:
            logger.exception("chat handler failed")
            return

        print(f"Regis: {resp.text}")
        _maybe_speak(resp.text, speak_enabled=self.speak_enabled)


class _ArmedState:
    """Tiny thread-safe holder for the post-wake 'armed' window."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._until: datetime | None = None

    def arm(self, seconds: float) -> None:
        with self._lock:
            self._until = datetime.now(timezone.utc) + timedelta(seconds=seconds)

    def disarm(self) -> None:
        with self._lock:
            self._until = None

    def is_armed(self) -> bool:
        with self._lock:
            if self._until is None:
                return False
            if datetime.now(timezone.utc) >= self._until:
                self._until = None
                return False
            return True


def _handle_message_text(
    text: str,
    *,
    user_id: str,
    runner: TurnRunner,
    speak_enabled: bool,
    arm_followup: callable,
) -> None:
    """Classify text as command or chat message, then dispatch (non-blocking).

    Commands run inline (they're fast). Chat turns are submitted to the
    TurnRunner so the caller (the mic listener worker thread) returns
    immediately and packet callbacks keep firing for barge-in detection.
    """
    intent = classify_intent(text)
    if intent != CommandIntent.NONE:
        result = wake_handlers.dispatch(
            intent,
            user_id=user_id,
            context={"transcript": text, "source_event": "voice_wake"},
        )
        print(f"[command] {intent.value} -> ok={result['ok']}")
        if result.get("ack"):
            _maybe_speak(result["ack"], speak_enabled=speak_enabled)
        arm_followup()
        return
    runner.submit_turn(text, on_complete=arm_followup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mic_listener.run")
    parser.add_argument("--wake-mode", choices=["transcription", "wake_word"], default=DEFAULT_WAKE_MODE,
                        help="transcription: whisper every segment, check for wake phrase; "
                             "wake_word: use openWakeWord model")
    parser.add_argument("--wake-phrase", default=DEFAULT_WAKE_PHRASE,
                        help="phrase to detect in transcription mode (default 'regis')")
    parser.add_argument("--wake-word", default=DEFAULT_WAKE_WORD,
                        help="openWakeWord model id for wake_word mode (default 'hey_jarvis')")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--armed-seconds", type=float, default=DEFAULT_ARMED_SECONDS)
    parser.add_argument("--followup-seconds", type=float, default=DEFAULT_FOLLOWUP_SECONDS,
                        help="how long to stay 'in conversation' after a turn (no wake needed). "
                             "Set to 0 to disable follow-up mode.")
    parser.add_argument("--user", default=DEFAULT_USER_ID)
    parser.add_argument("--no-speak", action="store_true")
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="disable streaming LLM + TTS (use legacy synchronous path)",
    )
    parser.add_argument("--silence-seconds-to-end", type=float, default=0.8)
    parser.add_argument("--input-device", default=DEFAULT_INPUT_DEVICE,
                        help="audio input device (name substring or int index). "
                             "Default: 'MacBook Pro Microphone' — forced to avoid "
                             "the narrowband BT headset mic which kills STT quality.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    user_id = args.user
    speak_enabled = not args.no_speak
    streaming_enabled = not args.no_streaming
    armed = _ArmedState()
    conversation_box: dict = {"id": None}
    runner = TurnRunner(
        user_id=user_id,
        conversation_box=conversation_box,
        speak_enabled=speak_enabled,
        streaming=streaming_enabled,
    )

    # Resolve device: int if numeric string, else string substring match for sounddevice
    resolved_device: int | str | None = args.input_device
    if isinstance(resolved_device, str) and resolved_device.strip().isdigit():
        resolved_device = int(resolved_device.strip())
    if resolved_device:
        print(f"[mic listener] input device: {resolved_device!r}")
    else:
        print("[mic listener] input device: (OS default)")

    listener = ContinuousMicListener(
        silence_seconds_to_end=args.silence_seconds_to_end,
        device=resolved_device,
    )

    # Only construct + warm-load the wake-word model if we're using wake_word mode.
    detector: VoiceWakeWordDetector | None = None
    if args.wake_mode == "wake_word":
        detector = VoiceWakeWordDetector(
            wake_word=args.wake_word, threshold=args.threshold
        )
        detector.get_model()

    if args.wake_mode == "transcription":
        print(
            f"[mic listener] mode=transcription wake-phrase={args.wake_phrase!r} "
            f"armed-window={args.armed_seconds}s follow-up={args.followup_seconds}s "
            f"speak={'on' if speak_enabled else 'off'} "
            f"streaming={'on' if streaming_enabled else 'off'}"
        )
        print(f"[mic listener] say '{args.wake_phrase}' or 'hey {args.wake_phrase}' to wake. "
              f"After a turn you have {args.followup_seconds}s to continue without re-waking.")
    else:
        print(
            f"[mic listener] mode=wake_word wake-word={args.wake_word} threshold={args.threshold} "
            f"armed-window={args.armed_seconds}s follow-up={args.followup_seconds}s "
            f"speak={'on' if speak_enabled else 'off'} "
            f"streaming={'on' if streaming_enabled else 'off'}"
        )
        print(f"[mic listener] say the wake word, then speak. After a turn you have "
              f"{args.followup_seconds}s to continue without re-waking. Speak over Regis to interrupt.")

    def _arm_followup() -> None:
        """After a successful turn, stay armed for follow-up mode."""
        if args.followup_seconds > 0:
            armed.arm(args.followup_seconds)
            print(f"[follow-up] armed {args.followup_seconds:.0f}s — keep talking, no wake needed")

    def on_packet(chunk: AudioChunk) -> None:
        # FAST barge-in: every ~80ms packet, check if Regis is speaking AND the
        # user is speaking. If both, cut Regis off immediately — don't wait for
        # the full voice segment to end. Drops barge-in latency from ~800ms to ~80ms.
        # This callback only works if the listener worker thread isn't blocked —
        # see TurnRunner which moves turn processing off the worker.
        if chunk.has_speech and chunk.energy >= BARGE_IN_RMS_THRESHOLD:
            try:
                from inference.audio import is_speaking, stop_speaking

                if is_speaking():
                    print(f"[barge-in:fast] user spoke over Regis (energy={chunk.energy:.3f})")
                    stop_speaking()
            except Exception:
                logger.debug("fast barge-in check failed", exc_info=True)

        # Wake-word detection (only used in wake_word mode).
        if detector is None:
            return
        try:
            ev = detector.process_audio_chunk(chunk.audio, chunk.sample_rate)
        except Exception:
            logger.exception("wake-word predict failed (continuing)")
            return
        if ev is None:
            return
        if armed.is_armed():
            return
        print(
            f"[wake] {ev.metadata.get('wake_word','?')} "
            f"conf={ev.confidence:.2f} — armed {args.armed_seconds:.1f}s"
        )
        armed.arm(args.armed_seconds)
        detector.reset()

    def _try_barge_in(chunk: AudioChunk) -> bool:
        """If Regis is speaking and this segment is loud enough to be intentional
        speech, interrupt the playback. Returns True if barge-in happened."""
        try:
            from inference.audio import is_speaking, stop_speaking
        except Exception:
            return False
        if not is_speaking():
            return False
        if chunk.energy < BARGE_IN_RMS_THRESHOLD:
            return False
        print(f"[barge-in] user spoke over Regis (energy={chunk.energy:.3f}) — stopping")
        stop_speaking()
        return True

    def on_voice_segment(chunk: AudioChunk) -> None:
        # Voice segments run on the listener worker thread. We MUST NOT block
        # here — the worker is shared with packet callbacks (which drive
        # barge-in). All chat work is dispatched via TurnRunner.
        barged_in = _try_barge_in(chunk)

        # Transcription mode: every voiced segment gets transcribed, then we
        # check whether it contains the wake phrase. STT is CPU-bound but
        # short (~hundreds of ms) — acceptable on the worker thread; the
        # multi-second LLM/TTS work is what we offload via TurnRunner.
        if args.wake_mode == "transcription":
            t0 = time.monotonic()
            text = _transcribe_segment(chunk.audio, chunk.sample_rate)
            stt_ms = int((time.monotonic() - t0) * 1000)
            if not text:
                return

            currently_armed = armed.is_armed() or barged_in
            after_wake = extract_message_after_wake(text, args.wake_phrase)

            if after_wake is not None:
                # Wake phrase detected (with or without message attached)
                if after_wake:
                    print(f"[stt {stt_ms}ms] [wake+msg] {text!r}")
                    armed.disarm()
                    _handle_message_text(
                        after_wake,
                        user_id=user_id,
                        runner=runner,
                        speak_enabled=speak_enabled,
                        arm_followup=_arm_followup,
                    )
                else:
                    print(f"[stt {stt_ms}ms] [wake] {text!r} — armed {args.armed_seconds:.1f}s")
                    armed.arm(args.armed_seconds)
                return

            if currently_armed:
                # Previously armed (initial wake, follow-up window, or barge-in)
                print(f"[stt {stt_ms}ms] [armed-msg{' barge' if barged_in else ''}] {text!r}")
                armed.disarm()
                _handle_message_text(
                    text,
                    user_id=user_id,
                    runner=runner,
                    speak_enabled=speak_enabled,
                    arm_followup=_arm_followup,
                )
                return

            # Not armed, no wake phrase — ignore
            return

        # wake_word mode: only act if pre-armed by openWakeWord packet handler
        # OR the user barged in over Regis OR follow-up window is open.
        if not (armed.is_armed() or barged_in):
            return
        armed.disarm()
        t0 = time.monotonic()
        text = _transcribe_segment(chunk.audio, chunk.sample_rate)
        stt_ms = int((time.monotonic() - t0) * 1000)
        if not text:
            print(f"[stt {stt_ms}ms] (empty)")
            return
        marker = "barge-msg" if barged_in else "msg"
        print(f"[stt {stt_ms}ms] [{marker}] {text!r}")
        _handle_message_text(
            text,
            user_id=user_id,
            runner=runner,
            speak_enabled=speak_enabled,
            arm_followup=_arm_followup,
        )

    if args.wake_mode == "wake_word":
        listener.register_packet_callback(on_packet)
    else:
        # In transcription mode the fast-barge-in check still wants to run on
        # every packet, even though we don't need the wake-word detector.
        listener.register_packet_callback(on_packet)
    listener.register_voice_callback(on_voice_segment)

    try:
        listener.start(blocking=True)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

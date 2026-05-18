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
# Default mode is wake_word for now — uses pre-trained "hey_jarvis" model. When
# a custom "Hey Regis" model is trained (see apps/inference/wake_word/training/),
# point DAYBOOK_WAKE_WORD_MODEL_PATH at the .onnx file and set DAYBOOK_WAKE_WORD=hey_regis.
# Switch to DAYBOOK_WAKE_MODE=transcription for the whisper-based fallback.
DEFAULT_WAKE_MODE = os.environ.get("DAYBOOK_WAKE_MODE", "wake_word")
DEFAULT_ARMED_SECONDS = 8.0
DEFAULT_THRESHOLD = 0.5


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
    if not text or not speak_enabled:
        if text:
            print(f"Regis: {text}")
        return
    try:
        from inference.audio import speak_streaming

        speak_streaming(text, mode="companion")
    except Exception as e:
        logger.warning("TTS failed (printing instead): %s", e)
        print(f"Regis: {text}")


def _route_message(
    *,
    user_id: str,
    conversation_id_box: dict,
    user_text: str,
    speak_enabled: bool,
) -> None:
    """Send transcribed text to the chat handler + speak response."""
    try:
        from chat.conversation import (
            create_conversation,
            most_recent_conversation,
        )
        from chat.handler import handle_user_message
    except Exception:
        logger.exception("chat handler import failed; cannot route message")
        return

    conv_id = conversation_id_box.get("id")
    if not conv_id:
        conv_id = most_recent_conversation(user_id=user_id) or create_conversation(
            user_id=user_id
        )
        conversation_id_box["id"] = conv_id

    try:
        resp = handle_user_message(
            user_id=user_id,
            conversation_id=conv_id,
            user_text=user_text,
        )
    except Exception:
        logger.exception("chat handler failed")
        return

    print(f"Regis: {resp.text}")
    _maybe_speak(resp.text, speak_enabled=speak_enabled)


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
    conversation_box: dict,
    speak_enabled: bool,
) -> None:
    """Classify text as command or chat message, then dispatch + (optionally) speak."""
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
        return
    _route_message(
        user_id=user_id,
        conversation_id_box=conversation_box,
        user_text=text,
        speak_enabled=speak_enabled,
    )


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
    parser.add_argument("--user", default=DEFAULT_USER_ID)
    parser.add_argument("--no-speak", action="store_true")
    parser.add_argument("--silence-seconds-to-end", type=float, default=0.8)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    user_id = args.user
    speak_enabled = not args.no_speak
    armed = _ArmedState()
    conversation_box: dict = {"id": None}

    listener = ContinuousMicListener(
        silence_seconds_to_end=args.silence_seconds_to_end,
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
            f"armed-window={args.armed_seconds}s speak={'on' if speak_enabled else 'off'}"
        )
        print(f"[mic listener] say '{args.wake_phrase}' or 'hey {args.wake_phrase}' to wake. Ctrl-C to quit.")
    else:
        print(
            f"[mic listener] mode=wake_word wake-word={args.wake_word} threshold={args.threshold} "
            f"armed-window={args.armed_seconds}s speak={'on' if speak_enabled else 'off'}"
        )
        print("[mic listener] say the wake word, then speak. Ctrl-C to quit.")

    def on_packet(chunk: AudioChunk) -> None:
        # Only used in wake_word mode.
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

    def on_voice_segment(chunk: AudioChunk) -> None:
        # Transcription mode: every voiced segment gets transcribed, then we
        # check whether it contains the wake phrase.
        if args.wake_mode == "transcription":
            t0 = time.monotonic()
            text = _transcribe_segment(chunk.audio, chunk.sample_rate)
            stt_ms = int((time.monotonic() - t0) * 1000)
            if not text:
                return

            currently_armed = armed.is_armed()
            after_wake = extract_message_after_wake(text, args.wake_phrase)

            if after_wake is not None:
                # Wake phrase detected (with or without message attached)
                if after_wake:
                    print(f"[stt {stt_ms}ms] [wake+msg] {text!r}")
                    armed.disarm()
                    _handle_message_text(
                        after_wake,
                        user_id=user_id,
                        conversation_box=conversation_box,
                        speak_enabled=speak_enabled,
                    )
                else:
                    print(f"[stt {stt_ms}ms] [wake] {text!r} — armed {args.armed_seconds:.1f}s")
                    armed.arm(args.armed_seconds)
                return

            if currently_armed:
                # Previously armed; treat THIS segment as the message
                print(f"[stt {stt_ms}ms] [armed-msg] {text!r}")
                armed.disarm()
                _handle_message_text(
                    text,
                    user_id=user_id,
                    conversation_box=conversation_box,
                    speak_enabled=speak_enabled,
                )
                return

            # Not armed, no wake phrase — ignore
            return

        # wake_word mode: only act if pre-armed by openWakeWord packet handler
        if not armed.is_armed():
            return
        armed.disarm()
        t0 = time.monotonic()
        text = _transcribe_segment(chunk.audio, chunk.sample_rate)
        stt_ms = int((time.monotonic() - t0) * 1000)
        if not text:
            print(f"[stt {stt_ms}ms] (empty)")
            return
        print(f"[stt {stt_ms}ms] {text!r}")
        _handle_message_text(
            text,
            user_id=user_id,
            conversation_box=conversation_box,
            speak_enabled=speak_enabled,
        )

    if args.wake_mode == "wake_word":
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

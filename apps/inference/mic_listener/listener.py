"""Continuous mic capture daemon with VAD-segmented voiced-segment dispatch.

Reads from the default input device in fixed short packets (~80 ms). Each packet
is fanned out to short-packet callbacks (for wake-word detectors). In parallel,
silero-VAD gates voiced segments — once sustained silence ends a voiced span,
the accumulated segment is dispatched to voice-segment callbacks.

Public surface:
  - AudioChunk
  - ContinuousMicListener
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from audio_context.vad import is_speech_now  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_PACKET_MS = 80  # openWakeWord wants multiples of 80ms (1280 samples @16k)
MAX_SEGMENT_SECONDS = 30.0  # safety cap: never emit a segment longer than this


@dataclass
class AudioChunk:
    audio: np.ndarray
    sample_rate: int
    captured_at_start: datetime
    captured_at_end: datetime
    energy: float
    has_speech: bool
    meta: dict = field(default_factory=dict)


VoiceCallback = Callable[[AudioChunk], None]
PacketCallback = Callable[[AudioChunk], None]
SilenceCallback = Callable[[], None]


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    flat = samples.astype(np.float32, copy=False).reshape(-1)
    return float(np.sqrt(np.mean(np.square(flat, dtype=np.float64))))


def _int16_to_float32(samples: np.ndarray) -> np.ndarray:
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    return samples.astype(np.float32, copy=False)


class ContinuousMicListener:
    """Always-on mic — fans short packets out + emits VAD-segmented voiced spans.

    Designed so multiple consumers (wake-word detector, audio-context processor,
    debug logger) can attach without each opening its own InputStream.
    """

    def __init__(
        self,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        packet_ms: int = DEFAULT_PACKET_MS,
        silence_seconds_to_end: float = 0.8,
        min_segment_seconds: float = 0.3,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.packet_ms = packet_ms
        self.packet_frames = int(sample_rate * packet_ms / 1000)
        self.silence_seconds_to_end = silence_seconds_to_end
        self.min_segment_seconds = min_segment_seconds
        self.device = device

        self._voice_cbs: list[VoiceCallback] = []
        self._packet_cbs: list[PacketCallback] = []
        self._silence_cbs: list[SilenceCallback] = []

        self._stop_event = threading.Event()
        self._audio_q: queue.Queue[np.ndarray | None] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._stream = None

    def register_voice_callback(self, cb: VoiceCallback) -> None:
        self._voice_cbs.append(cb)

    def register_packet_callback(self, cb: PacketCallback) -> None:
        self._packet_cbs.append(cb)

    def register_silence_callback(self, cb: SilenceCallback) -> None:
        self._silence_cbs.append(cb)

    def start(self, *, blocking: bool = True) -> None:
        """Start mic + worker. If blocking, returns when stop() is called."""
        import sounddevice as sd

        if self._stream is not None:
            raise RuntimeError("listener already started")

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_worker, name="mic-listener-worker", daemon=True
        )
        self._worker_thread.start()

        def callback(indata, _frames, _time_info, status):
            if status:
                logger.warning("sounddevice status: %s", status)
            mono = indata[:, 0] if indata.ndim > 1 else indata
            self._audio_q.put(mono.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.packet_frames,
                device=self.device,
                callback=callback,
            )
            self._stream.start()
        except Exception as e:
            self._stop_event.set()
            self._audio_q.put(None)
            raise RuntimeError(
                f"Could not open mic input stream: {e}. "
                "On macOS, grant terminal mic permission in System Settings > Privacy."
            ) from e

        logger.info(
            "mic listener started (sr=%d packet_ms=%d device=%s)",
            self.sample_rate,
            self.packet_ms,
            self.device,
        )

        if blocking:
            try:
                while not self._stop_event.is_set():
                    self._stop_event.wait(timeout=0.5)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self._audio_q.put(None)
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logger.exception("error stopping stream")
            self._stream = None
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None
        logger.info("mic listener stopped")

    def _run_worker(self) -> None:
        """Consume audio queue: run VAD, fan out packets, accumulate segments."""
        silence_packets_needed = max(
            1, int(round(self.silence_seconds_to_end * 1000 / self.packet_ms))
        )
        max_segment_packets = int(
            MAX_SEGMENT_SECONDS * 1000 / self.packet_ms
        )

        segment_packets: list[np.ndarray] = []
        segment_started_at: datetime | None = None
        silent_streak = 0
        sustained_silence_packets = silence_packets_needed * 4
        silence_emitted = False

        while not self._stop_event.is_set():
            try:
                packet = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if packet is None:
                break

            now_end = datetime.now(timezone.utc)
            now_start = now_end  # ~80 ms; close enough for downstream
            energy = _rms(packet)
            has_speech = False
            try:
                has_speech = is_speech_now(packet, sample_rate=self.sample_rate)
            except Exception as e:
                logger.debug("VAD failed on packet: %s", e)

            chunk = AudioChunk(
                audio=packet,
                sample_rate=self.sample_rate,
                captured_at_start=now_start,
                captured_at_end=now_end,
                energy=energy,
                has_speech=has_speech,
            )

            for cb in self._packet_cbs:
                try:
                    cb(chunk)
                except Exception:
                    logger.exception("packet callback failed")

            if has_speech:
                if segment_started_at is None:
                    segment_started_at = now_start
                segment_packets.append(packet)
                silent_streak = 0
                silence_emitted = False
                if len(segment_packets) >= max_segment_packets:
                    self._emit_segment(segment_packets, segment_started_at, now_end)
                    segment_packets = []
                    segment_started_at = None
            else:
                if segment_packets:
                    segment_packets.append(packet)
                    silent_streak += 1
                    if silent_streak >= silence_packets_needed:
                        # trim trailing silence
                        keep = len(segment_packets) - silent_streak
                        if keep > 0:
                            emit_packets = segment_packets[:keep]
                            ended_at = now_end
                            self._emit_segment(
                                emit_packets, segment_started_at, ended_at
                            )
                        segment_packets = []
                        segment_started_at = None
                        silent_streak = 0
                else:
                    silent_streak += 1
                    if (
                        not silence_emitted
                        and silent_streak >= sustained_silence_packets
                    ):
                        silence_emitted = True
                        for cb in self._silence_cbs:
                            try:
                                cb()
                            except Exception:
                                logger.exception("silence callback failed")

    def _emit_segment(
        self,
        packets: list[np.ndarray],
        started_at: datetime | None,
        ended_at: datetime,
    ) -> None:
        if not packets:
            return
        audio = np.concatenate(packets)
        duration_s = audio.shape[0] / self.sample_rate
        if duration_s < self.min_segment_seconds:
            return
        if started_at is None:
            started_at = ended_at
        chunk = AudioChunk(
            audio=audio,
            sample_rate=self.sample_rate,
            captured_at_start=started_at,
            captured_at_end=ended_at,
            energy=_rms(audio),
            has_speech=True,
            meta={"duration_s": duration_s},
        )
        for cb in self._voice_cbs:
            try:
                cb(chunk)
            except Exception:
                logger.exception("voice segment callback failed")


__all__ = ["AudioChunk", "ContinuousMicListener"]

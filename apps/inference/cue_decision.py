"""Stateful cue-firing decisions.

Wraps the realtime classifier output stream and applies safety + quality rules
to decide whether the wisp should speak in this 30-second window.

v0 fires only one cue kind: 'rem_whisper' (short contextual whisper during
stable REM). Morning recall prompts are scheduled by the Pi daemon on a
wake timer, not through this module.

Usage:
    from inference.cue_decision import CueDecider
    decider = CueDecider()
    decider.start_session(started_at=now)
    for pred in stream_of_predictions:
        decision = decider.update(pred)
        if decision.fire:
            wisp.speak(decision.cue_kind)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

try:
    from .realtime import RealtimePrediction
except ImportError:
    from realtime import RealtimePrediction  # type: ignore[no-redef]


@dataclass
class CueConfig:
    confidence_floor: float = 0.50          # min P(REM) to consider firing (above tuned 0.23 — be conservative)
    consecutive_high_epochs: int = 3        # require 3 consecutive epochs above floor (90s of stable REM)
    cooldown_seconds: int = 25 * 60         # 25-minute cooldown between cues
    no_fire_first_seconds: int = 60 * 60    # first hour of sleep is sleep-onset noise
    no_fire_last_seconds: int = 30 * 60     # last 30 min — don't risk interrupting natural wake
    max_cues_per_session: int = 4
    expected_session_seconds: int = 8 * 3600  # for last-30-min calculation
    cue_kind: str = "rem_whisper"


@dataclass
class CueDecision:
    fire: bool
    reason: str
    cue_kind: str | None = None
    proba: float | None = None
    next_eligible_at: datetime | None = None


class CueDecider:
    def __init__(self, config: CueConfig | None = None) -> None:
        self.config = config or CueConfig()
        self.session_started_at: datetime | None = None
        self.session_end_planned: datetime | None = None
        self.last_fire_at: datetime | None = None
        self.cues_fired: int = 0
        self._consecutive_high: int = 0

    def start_session(self, started_at: datetime, expected_seconds: int | None = None) -> None:
        self.session_started_at = started_at
        dur = expected_seconds if expected_seconds is not None else self.config.expected_session_seconds
        self.session_end_planned = started_at + timedelta(seconds=dur)
        self.last_fire_at = None
        self.cues_fired = 0
        self._consecutive_high = 0

    def update(self, pred: RealtimePrediction) -> CueDecision:
        if self.session_started_at is None:
            return CueDecision(fire=False, reason="session_not_started", proba=pred.rem_probability)

        # Track consecutive-high counter regardless of whether we'd fire
        if pred.rem_probability >= self.config.confidence_floor:
            self._consecutive_high += 1
        else:
            self._consecutive_high = 0

        now = pred.epoch_start_at
        elapsed = (now - self.session_started_at).total_seconds()
        time_to_end = (self.session_end_planned - now).total_seconds() if self.session_end_planned else float("inf")

        # Gate 1: session ramp-up
        if elapsed < self.config.no_fire_first_seconds:
            return CueDecision(
                fire=False,
                reason=f"in_ramp_up ({elapsed:.0f}s/{self.config.no_fire_first_seconds}s)",
                proba=pred.rem_probability,
            )

        # Gate 2: session end zone
        if time_to_end < self.config.no_fire_last_seconds:
            return CueDecision(
                fire=False,
                reason=f"in_end_zone ({time_to_end:.0f}s remaining)",
                proba=pred.rem_probability,
            )

        # Gate 3: max cues for session
        if self.cues_fired >= self.config.max_cues_per_session:
            return CueDecision(
                fire=False,
                reason=f"max_cues_reached ({self.cues_fired}/{self.config.max_cues_per_session})",
                proba=pred.rem_probability,
            )

        # Gate 4: cooldown
        if self.last_fire_at is not None:
            since_last = (now - self.last_fire_at).total_seconds()
            if since_last < self.config.cooldown_seconds:
                remaining = self.config.cooldown_seconds - since_last
                return CueDecision(
                    fire=False,
                    reason=f"in_cooldown ({remaining:.0f}s left)",
                    proba=pred.rem_probability,
                    next_eligible_at=self.last_fire_at + timedelta(seconds=self.config.cooldown_seconds),
                )

        # Gate 5: confidence + stability
        if pred.rem_probability < self.config.confidence_floor:
            return CueDecision(
                fire=False,
                reason=f"below_confidence_floor ({pred.rem_probability:.2f} < {self.config.confidence_floor:.2f})",
                proba=pred.rem_probability,
            )
        if self._consecutive_high < self.config.consecutive_high_epochs:
            return CueDecision(
                fire=False,
                reason=f"need_stability ({self._consecutive_high}/{self.config.consecutive_high_epochs} consecutive high epochs)",
                proba=pred.rem_probability,
            )

        # All gates passed — fire
        self.last_fire_at = now
        self.cues_fired += 1
        self._consecutive_high = 0  # reset so we don't immediately re-fire
        return CueDecision(
            fire=True,
            reason=f"rem_confirmed (p={pred.rem_probability:.2f}, cue {self.cues_fired}/{self.config.max_cues_per_session})",
            cue_kind=self.config.cue_kind,
            proba=pred.rem_probability,
        )


if __name__ == "__main__":
    # Smoke test: synthetic prediction stream simulating a night.
    from datetime import timezone

    cfg = CueConfig()
    dec = CueDecider(cfg)
    t0 = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    dec.start_session(started_at=t0, expected_seconds=8 * 3600)

    fires = []
    # 8 hours of 30-second epochs = 960 epochs
    for i in range(960):
        epoch_at = t0 + timedelta(seconds=i * 30)
        # Synthesize REM-likely chunks at minutes 90-120, 240-260, 360-380, 450-470
        minute = i * 0.5
        if 90 < minute < 120 or 240 < minute < 260 or 360 < minute < 380 or 450 < minute < 470:
            proba = 0.7
        else:
            proba = 0.1

        pred = RealtimePrediction(
            epoch_start_at=epoch_at,
            rem_probability=proba,
            is_rem=proba >= 0.23,
            threshold=0.23,
            n_in_window={"heart_rate": 3, "hrv": 0, "respiratory_rate": 1, "spo2": 0},
            features={},
        )
        d = dec.update(pred)
        if d.fire:
            fires.append((epoch_at, d.reason))

    print(f"Synthesized 8h session with 4 REM-like windows.")
    print(f"Cues fired: {len(fires)}")
    for at, reason in fires:
        mins = (at - t0).total_seconds() / 60
        print(f"  t+{mins:>5.1f}min  {reason}")
    if not fires:
        print("  (none — review gates / synthetic data)")

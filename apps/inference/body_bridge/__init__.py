"""Body bridge — sensor_readings (HealthKit) → user_state_estimate translator.

The first step toward the project's "live prediction from live raw sensory
data" north star. Closes the gap where iPhone HealthKit data uploads fine
but Regis can't see it: substrate.current_user_state was only ever written
by the sleep classifier during sleep sessions, leaving Regis blind to the
user's live body during waking hours.

Now: every 5 min (env-tunable), body_bridge.estimate_current_state pulls
recent HealthKit sensor_readings (heart_rate, hrv, sleep_stage), computes
a transparent heuristic state estimate, and writes a user_state_estimate
row with source='body_bridge'.
"""
from .estimator import estimate_current_state

__all__ = ["estimate_current_state"]

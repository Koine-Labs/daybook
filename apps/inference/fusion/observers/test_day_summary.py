"""Day-summary observer — synthetic sessions in, exact regis_observations INSERTs out."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

import pytest  # noqa: E402

from fusion.belief_state import AxisEstimate  # noqa: E402
from fusion.observers import SessionWindow, read_session_estimates, summarize_session  # noqa: E402
from fusion.observers.day_summary import SOURCE  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
T0 = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
WINDOW = SessionWindow(start=T0, end=T0 + timedelta(hours=8))


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self._conn.executed.append((" ".join(sql.split()), params))

    def fetchone(self) -> tuple[str]:
        return (f"obs-{len(self._conn.executed)}",)

    def fetchall(self) -> list[tuple]:
        return list(self._conn.rows)

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False


class _FakeConn:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.rows = rows or []
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False


def _est(axis: str, value: dict[str, Any], minute: int, *,
         confidence: float | None = 0.8, source: str = "L3.fusion.test") -> AxisEstimate:
    return AxisEstimate(
        axis=axis,
        value=value,
        timestamp=T0 + timedelta(minutes=minute),
        confidence=confidence,
        source=source,
    )


def _session() -> list[AxisEstimate]:
    return [
        _est("meta_context", {"category": "waking/focused"}, 0),
        _est("meta_context", {"category": "waking/focused"}, 10),
        _est("meta_context", {"category": "waking/focused"}, 20),
        _est("meta_context", {"category": "waking/browsing"}, 30),
        _est("meta_context", {"category": "waking/browsing"}, 40),
        _est("audio_social_context", {"category": "alone"}, 5),
        _est("audio_social_context", {"category": "with_other"}, 15),
        _est("audio_social_context", {"category": "with_other"}, 25),
        _est("visual_context", {"setting": "desk", "people_present": False}, 12),
        _est("visual_context", {"setting": "desk", "people_present": True}, 22),
        _est("arousal_inferred", {"arousal": 0.2, "band": "low"}, 8),
        _est("arousal_inferred", {"arousal": 0.5, "band": "medium"}, 18),
        _est("arousal_inferred", {"arousal": 0.7, "band": "high"}, 28),
    ]


EXPECTED_SQL = (
    "INSERT INTO regis_observations (user_id, observed_at, observation, context, weight, source, i_model_id) "
    "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s) RETURNING id"
)


def test_synthetic_session_produces_expected_inserts():
    conn = _FakeConn()
    ids = summarize_session(lambda _u, _w: _session(), USER, WINDOW, conn=conn)

    assert ids == ["obs-1", "obs-2", "obs-3"]
    assert conn.commits == 1
    assert len(conn.executed) == 3
    for sql, _params in conn.executed:
        assert sql == EXPECTED_SQL

    context_params = conn.executed[0][1]
    assert context_params[0] == USER
    assert context_params[1] == WINDOW.end
    assert context_params[2] == (
        "Session context: mostly waking/focused (60% of 5 reads; 1 shifts)."
    )
    ctx = json.loads(context_params[3])
    assert ctx["kind"] == "session_context"
    assert ctx["dominant"] == "waking/focused"
    assert ctx["reads"] == 5
    assert ctx["shifts"] == 1
    assert ctx["window"] == {"start": WINDOW.start.isoformat(), "end": WINDOW.end.isoformat()}
    assert context_params[4] == 0.25
    assert context_params[5] == SOURCE
    assert context_params[6] is None

    company_params = conn.executed[1][1]
    assert company_params[2] == (
        "Company: voices of others in 2 of 3 audio reads; "
        "people visible in 1 of 2 frames, mostly around 'desk'."
    )
    company_ctx = json.loads(company_params[3])
    assert company_ctx["kind"] == "session_company"
    assert company_ctx["with_other_reads"] == 2
    assert company_ctx["people_frames"] == 1
    assert company_ctx["top_setting"] == "desk"
    assert company_params[4] == 0.25
    assert company_params[6] is None

    ranges_params = conn.executed[2][1]
    assert ranges_params[2] == "Axis ranges: arousal_inferred 0.20-0.70 over 3 reads."
    ranges_ctx = json.loads(ranges_params[3])
    assert ranges_ctx["kind"] == "session_axis_ranges"
    assert ranges_ctx["ranges"]["arousal_inferred"] == {"min": 0.2, "max": 0.7, "reads": 3}
    assert ranges_params[4] == 0.15
    assert ranges_params[6] is None


def test_empty_session_writes_no_rows():
    conn = _FakeConn()
    assert summarize_session(lambda _u, _w: [], USER, WINDOW, conn=conn) == []
    assert conn.executed == []
    assert conn.commits == 0


def test_offline_estimates_are_ignored():
    offline = [
        _est("meta_context", {"category": "offline", "reason": "no fresh data"}, 0,
             confidence=None, source="L3.fusion.meta_context.offline"),
        _est("visual_context", {"category": "offline", "reason": "no fresh data"}, 5,
             confidence=None, source="L3.fusion.visual_context.offline"),
    ]
    conn = _FakeConn()
    assert summarize_session(lambda _u, _w: offline, USER, WINDOW, conn=conn) == []
    assert conn.executed == []


def test_weight_reflects_evidence_density():
    def dense(_u: str, _w: SessionWindow) -> list[AxisEstimate]:
        return [_est("meta_context", {"category": "waking/focused"}, m) for m in range(20)]

    def sparse(_u: str, _w: SessionWindow) -> list[AxisEstimate]:
        return [_est("meta_context", {"category": "waking/focused"}, m) for m in range(4)]

    dense_conn, sparse_conn = _FakeConn(), _FakeConn()
    summarize_session(dense, USER, WINDOW, conn=dense_conn)
    summarize_session(sparse, USER, WINDOW, conn=sparse_conn)
    dense_weight = dense_conn.executed[0][1][4]
    sparse_weight = sparse_conn.executed[0][1][4]
    assert dense_weight == 1.0
    assert sparse_weight == 0.2
    assert dense_weight > sparse_weight


def test_no_notable_company_skips_that_observation():
    session = [
        _est("meta_context", {"category": "waking/focused"}, 0),
        _est("audio_social_context", {"category": "alone"}, 5),
        _est("visual_context", {"setting": "unknown", "people_present": False}, 10),
    ]
    conn = _FakeConn()
    summarize_session(lambda _u, _w: session, USER, WINDOW, conn=conn)
    texts = [params[2] for _sql, params in conn.executed]
    assert len(texts) == 1
    assert texts[0].startswith("Session context:")


def test_reader_receives_user_and_window():
    seen: list[tuple[str, SessionWindow]] = []

    def reader(user_id: str, window: SessionWindow) -> list[AxisEstimate]:
        seen.append((user_id, window))
        return []

    summarize_session(reader, USER, WINDOW, conn=_FakeConn())
    assert seen == [(USER, WINDOW)]


def test_window_requires_tz_aware_ordered_bounds():
    with pytest.raises(ValueError):
        SessionWindow(start=datetime(2026, 6, 10), end=T0)
    with pytest.raises(ValueError):
        SessionWindow(start=WINDOW.end, end=WINDOW.start)


def test_read_session_estimates_maps_rows():
    rows = [
        ("meta_context", {"category": "waking/focused"}, 0.65,
         "L3.fusion.meta_context.v1_heuristic", T0.replace(tzinfo=None), "waking/focused", None),
        ("arousal_inferred", {"arousal": 0.4}, 0.5, "L3.fusion.arousal_inferred.v1", T0, None, None),
    ]
    conn = _FakeConn(rows=rows)
    ests = read_session_estimates(USER, WINDOW, conn=conn)
    assert [e.axis for e in ests] == ["meta_context", "arousal_inferred"]
    assert all(e.timestamp.tzinfo is not None for e in ests)
    assert ests[0].meta_context == "waking/focused"
    sql, params = conn.executed[0]
    assert "FROM user_state_estimate" in sql
    assert params == (USER, WINDOW.start, WINDOW.end)

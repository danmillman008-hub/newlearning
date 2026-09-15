"""Tests for gramophone_m2.adapt."""

from gramophone_m2 import adapt


def test_bkt_update_math():
    p = adapt.DEFAULT_BKT["p_init"]  # 0.0
    import pytest

    p1 = adapt.bkt_update(p, True)
    # p_lo=0.1; 0.1*0.9/(0.1*0.9+0.9*0.2) = 1/3
    assert p1 == pytest.approx(1 / 3)
    p2 = adapt.bkt_update(p1, True)
    # p_lo=0.4; 0.36/0.48 = 0.75
    assert p2 == pytest.approx(0.75)
    p3 = adapt.bkt_update(p2, False)
    # p_lo=0.775; 0.0775/(0.0775+0.225*0.8) = 0.0775/0.2575
    assert p3 == pytest.approx(0.0775 / 0.2575)
    assert adapt.is_mastered(0.95) is True
    assert adapt.is_mastered(0.949) is False


def _beat(bid, requires=(), teaches=(), difficulty=2):
    return {
        "id": bid,
        "requires": list(requires),
        "teaches": list(teaches),
        "difficulty": difficulty,
    }


def test_next_beat_ready_and_fringe_first():
    beats = [
        _beat("b1", teaches=["i1"]),
        _beat("b2", requires=["i1"], teaches=["i2"]),
        _beat("b3", requires=["i9"], teaches=["i3"]),
    ]
    nxt = adapt.next_beat(beats, set(), {}, {"i2"})
    assert nxt["id"] == "b1"  # only ready beat
    nxt = adapt.next_beat(beats, {"b1"}, {"i1": 0.99}, {"i2"})
    assert nxt["id"] == "b2"  # fringe + ready
    assert adapt.next_beat(beats, {"b1", "b2"}, {}, set()) is None  # b3 gated


def test_next_beat_deterministic_tiebreak():
    beats = [_beat("b2", teaches=["i2"]), _beat("b1", teaches=["i1"])]
    first = adapt.next_beat(beats, set(), {}, set())
    assert first["id"] == "b1"
    assert adapt.next_beat(beats, set(), {}, set())["id"] == "b1"


def test_next_beat_flow_steers_difficulty():
    beats = [_beat("easy", teaches=["i1"], difficulty=1), _beat("hard", teaches=["i2"], difficulty=4)]
    flow = adapt.FlowTracker()
    for _ in range(10):
        flow.update(True)  # rate 1.0 > band -> prefer harder
    assert adapt.next_beat(beats, set(), {}, set(), flow)["id"] == "hard"
    flow2 = adapt.FlowTracker()
    for r in [True] + [False] * 9:  # rate 0.1 < band -> prefer easier
        flow2.update(r)
    assert adapt.next_beat(beats, set(), {}, set(), flow2)["id"] == "easy"


def test_flow_tracker_ratio():
    flow = adapt.FlowTracker()
    assert flow.ratio() == 1.0
    for r in [True, True, True, False, True, True, True]:
        flow.update(r)
    import pytest

    # rates: 1,1,1,.75,.8,.833,.857 -> in-band 3 of 7
    assert flow.ratio() == pytest.approx(3 / 7)

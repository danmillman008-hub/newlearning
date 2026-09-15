"""Tests for gramophone_m2.srs."""

from gramophone_m2.srs import DSR


def test_new_item_due_and_review_grows():
    sched = DSR()
    assert sched.due("i", 0) is True
    s = sched.review("i", 1.0, 0)
    assert s == 2.0  # S *= (1 + grade)
    assert sched.due("i", 1) is False
    assert sched.due("i", 2) is True


def test_wrong_review_shrinks_with_floor():
    sched = DSR()
    sched.review("i", 1.0, 0)  # S = 2.0
    s = sched.review("i", 0.0, 2)  # wrong: max(1, 2*0)
    assert s == 1.0
    assert sched.interval("i") == 1


def test_partial_grades():
    sched = DSR()
    assert sched.review("i", 0.5, 0) == 1.0  # wrong (< 0.6): max(1, 0.5)
    assert sched.review("i", 0.8, 1) == 1.8  # correct: 1 * 1.8
    assert sched.interval("i") == 2


def test_logical_clock_deterministic():
    a, b = DSR(), DSR()
    for step, grade in enumerate([1.0, 0.0, 1.0]):
        a.review("i", grade, step)
        b.review("i", grade, step)
    assert a.stability == b.stability
    assert a.last_review == b.last_review

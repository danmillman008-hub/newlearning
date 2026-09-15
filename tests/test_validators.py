"""Tests for gramophone_m2.validators."""

import pytest

from gramophone_m2 import validators


def test_choice_exact():
    check = {
        "kind": "choice",
        "max_score": 1,
        "payload": {"options": ["a", "b"], "answer": "a"},
    }
    assert validators.grade(check, "a") == {"score": 1, "max_score": 1, "success": True}
    assert validators.grade(check, "b")["success"] is False
    assert validators.grade(check, "b")["score"] == 0


def test_ordering_perfect_and_partial():
    check = {
        "kind": "ordering",
        "max_score": 2,
        "payload": {"items": ["x", "y", "z"], "answer": ["x", "y", "z"]},
    }
    good = validators.grade(check, ["x", "y", "z"])
    assert good == {"score": 2.0, "max_score": 2, "success": True}
    # one inversion of three: frac = 1 - 2/6 = 2/3
    partial = validators.grade(check, ["x", "z", "y"])
    assert partial["success"] is False
    assert partial["score"] == pytest.approx(2 * 2 / 3, abs=1e-3)
    # wrong elements -> zero
    assert validators.grade(check, ["x", "y"])["score"] == 0.0


def test_numeric_tolerance():
    check = {
        "kind": "numeric",
        "max_score": 1,
        "payload": {"answer": 2.0, "tolerance": 0.1},
    }
    assert validators.grade(check, 2.05)["success"] is True
    assert validators.grade(check, 2.5)["success"] is False
    # default relative tolerance when None
    check2 = {"kind": "numeric", "max_score": 1, "payload": {"answer": 100.0}}
    assert validators.grade(check2, 100.0)["success"] is True


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        validators.grade({"kind": "essay", "payload": {}}, "x")

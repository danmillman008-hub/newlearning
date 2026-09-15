"""Unit tests: spacing enumeration, fringe, Hasse covers, validation, caps."""

from gramophone_m1.spacing import (
    enumerate_states,
    fringe,
    hasse_covers,
    partition_by_tag,
    validate_space,
)


def test_chain_enumerates_n_plus_one_states():
    pack = enumerate_states(["a", "b", "c"], [["a", "b"], ["b", "c"]])
    assert pack == {
        "states": [[], ["a"], ["a", "b"], ["a", "b", "c"]],
        "overflow": False,
    }


def test_antichain_enumerates_powerset():
    pack = enumerate_states(["a", "b", "c"], [])
    assert len(pack["states"]) == 8
    assert sorted(map(tuple, pack["states"])) == [
        (), ("a",), ("a", "b"), ("a", "b", "c"), ("a", "c"), ("b",), ("b", "c"), ("c",)
    ]


def test_diamond_enumerates_six_ideals_exactly():
    pack = enumerate_states(
        ["a", "b", "c", "d"],
        [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
    )
    assert sorted(map(tuple, pack["states"])) == [
        (),
        ("a",),
        ("a", "b"),
        ("a", "b", "c"),
        ("a", "b", "c", "d"),
        ("a", "c"),
    ]
    assert validate_space(pack["states"], [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]])[
        "valid"
    ]


def test_fringe_is_prereq_ready_outside_items():
    edges = [["a", "b"], ["b", "c"]]
    assert fringe([], ["a", "b", "c"], edges) == ["a"]
    assert fringe(["a"], ["a", "b", "c"], edges) == ["b"]
    assert fringe(["a", "b", "c"], ["a", "b", "c"], edges) == []


def test_hasse_covers_drop_transitive_edges():
    edges = [["a", "b"], ["b", "c"], ["a", "c"]]
    assert hasse_covers(["a", "b", "c"], edges) == [["a", "b"], ["b", "c"]]


def test_validate_space_flags_non_ideals():
    assert validate_space([[], ["a"], ["a", "b"]], [["a", "b"]])["valid"] is True
    bad = validate_space([["b"]], [["a", "b"]])
    assert bad["valid"] is False
    assert bad["problems"] and "a" in bad["problems"][0]


def test_cap_overflow_truncates_deterministically():
    items = [f"x{i}" for i in range(5)]
    first = enumerate_states(items, [], cap=10)
    second = enumerate_states(items, [], cap=10)
    assert first["overflow"] is True
    assert len(first["states"]) == 10
    assert first == second


def test_partition_by_tag_groups_and_keeps_internal_edges():
    items = [
        {"id": "a", "tags": ["t1"]},
        {"id": "b", "tags": ["t1"]},
        {"id": "c", "tags": ["t2"]},
        {"id": "d", "tags": []},
    ]
    edges = [["a", "b"], ["b", "c"]]
    assert partition_by_tag(items, edges) == {
        "_untagged": {"items": ["d"], "edges": []},
        "t1": {"items": ["a", "b"], "edges": [["a", "b"]]},
        "t2": {"items": ["c"], "edges": []},
    }

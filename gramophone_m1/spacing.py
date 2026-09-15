"""KST core (pure Python, no LLM): states, fringes, Hasse covers.

A knowledge space over a surmise DAG is the family of ideals (downward-closed
sets) of the prerequisite poset. States are sorted id lists; enumeration order
is deterministic (lexicographic candidate expansion), so caps truncate
deterministically too.
"""

from __future__ import annotations

DEFAULT_STATE_CAP = 50000


def _prereq_map(items: list[str], edges: list[list[str]]) -> dict[str, set[str]]:
    prereqs: dict[str, set[str]] = {i: set() for i in items}
    for edge in edges:
        pre, itm = edge[0], edge[1]
        if pre in prereqs and itm in prereqs:
            prereqs[itm].add(pre)
    return prereqs


def enumerate_states(
    items: list[str],
    edges: list[list[str]],
    cap: int = DEFAULT_STATE_CAP,
) -> dict:
    """Enumerate ideals of the surmise poset (frontier expansion).

    Returns {"states": [...], "overflow": bool}. On cap overflow enumeration
    stops early (deterministic prefix) and overflow=True; callers fall back to
    partition_by_tag().
    """
    prereqs = _prereq_map(items, edges)
    states: list[list[str]] = []
    overflow = False
    if cap <= 0:
        return {"states": states, "overflow": True}

    # Iterative deepening-free DFS with an explicit stack (no recursion limit).
    # Each frame is (state, ordered_avail, next_index, excluded); child states
    # are appended when created, so enumeration order is exactly the recursive
    # pre-order and caps truncate identically.
    minimals = {m for m, reqs in prereqs.items() if not reqs}
    states.append([])
    stack: list[tuple[frozenset, list[str], int, set[str]]] = [
        (frozenset(), sorted(minimals), 0, set())
    ]
    while stack:
        if len(states) >= cap:
            overflow = True
            break
        state, ordered, idx, excluded = stack[-1]
        if idx >= len(ordered):
            stack.pop()
            continue
        stack[-1] = (state, ordered, idx + 1, excluded)
        cand = ordered[idx]
        new_state = state | {cand}
        new_excluded = set(excluded) | set(ordered[:idx])
        new_avail = set(ordered) - {cand} - new_excluded
        for member, reqs in prereqs.items():
            if (
                member not in new_state
                and member not in new_excluded
                and reqs <= set(new_state)
            ):
                new_avail.add(member)
        if len(states) >= cap:
            overflow = True
            break
        states.append(sorted(new_state))
        stack.append((new_state, sorted(new_avail), 0, new_excluded))
    return {"states": states, "overflow": overflow}


def fringe(
    state: list[str] | set[str],
    items: list[str],
    edges: list[list[str]],
) -> list[str]:
    """Outer fringe: items outside the state whose prereqs are all inside."""
    known = set(state)
    prereqs = _prereq_map(items, edges)
    return sorted(i for i in items if i not in known and prereqs[i] <= known)


def hasse_covers(items: list[str], edges: list[list[str]]) -> list[list[str]]:
    """Transitive reduction: edges with no intermediate path (sorted)."""
    succ: dict[str, set[str]] = {i: set() for i in items}
    for edge in edges:
        if edge[0] in succ and edge[1] in succ:
            succ[edge[0]].add(edge[1])

    def reaches(src: str, dst: str, banned: tuple[str, str]) -> bool:
        seen = {src}
        stack = [src]
        while stack:
            node = stack.pop()
            for nxt in succ[node]:
                if (node, nxt) == banned or nxt in seen:
                    continue
                if nxt == dst:
                    return True
                seen.add(nxt)
                stack.append(nxt)
        return False

    covers = [
        [p, i]
        for p, i in edges
        if p in succ and i in succ and not reaches(p, i, (p, i))
    ]
    return sorted(covers)


def validate_space(states: list[list[str]], edges: list[list[str]]) -> dict:
    """Check every state is an ideal; report problems (deterministic order)."""
    prereqs: dict[str, set[str]] = {}
    for edge in edges:
        prereqs.setdefault(edge[1], set()).add(edge[0])
    problems: list[str] = []
    for state in states:
        known = set(state)
        for member in sorted(known):
            missing = sorted(prereqs.get(member, set()) - known)
            for req in missing:
                problems.append(f"state {sorted(state)} misses prereq {req} for {member}")
    problems.sort()
    return {"valid": not problems, "problems": problems}


def partition_by_tag(items: list[dict], edges: list[list[str]]) -> dict:
    """Overflow fallback: group items by first tag; keep intra-cluster edges.

    Returns {tag: {"items": [ids], "edges": [[p, i]]}}. Cross-cluster edges are
    dropped (documented degradation: partition states union, not the product).
    """
    clusters: dict[str, list[str]] = {}
    for item in items:
        tags = item.get("tags") or []
        tag = str(tags[0]) if tags else "_untagged"
        clusters.setdefault(tag, []).append(item["id"])
    owner = {iid: tag for tag, ids in clusters.items() for iid in ids}
    result: dict[str, dict] = {}
    for tag in sorted(clusters):
        ids = sorted(clusters[tag])
        own = set(ids)
        internal = sorted(
            [p, i] for p, i in edges if p in own and i in own and owner.get(p) == tag
        )
        result[tag] = {"items": ids, "edges": internal}
    return result

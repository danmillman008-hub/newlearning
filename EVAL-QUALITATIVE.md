# Gramophone — Qualitative Field Test + Final Evaluation

Date: 2026-09-16. Product under test: `main=a915b8a` (M1–M8).
Method: real open-source material through the live Flash path, then two
scripted learner personas + pedagogical analysis. No product code changed.

## 1. Setup

- Material: `rust-lang/book` (MIT/Apache): `ch04-01-what-is-ownership`
  (522 lines / 25 KB / 113 blocks) + `ch04-02-references-and-borrowing`
  (263 lines / 11 KB). Topic: Rust ownership — dense with true concept
  prerequisites (borrowing requires ownership), ideal for testing graphs.
- Live cost for the whole eval: 12 Flash requests, ≈34k tokens
  (25,486 metered: M1 15,493 + 8,095, author 1,898; +≈8.5k for one
  diagnostic re-run). Persona quests are fully offline (zero tokens).

## 2. Blood-flow trace (does blood reach every organ?)

| stage | in | out | verdict |
|---|---|---|---|
| M1 ch1 (Flash) | 113 blocks | 10 entities, 6 rel → 6 candidates → **2 items**, 1 edge, 3 states | flows, but thin |
| M1 ch2 (Flash) | 36 KB ch2 | 8–10 entities → **2 items**, 1 edge | flows, but thin |
| merge | 2 v1s | 4 items, 2 edges (both intra-chapter) | flows; no cross-chapter edges |
| author STORY (Flash) | 4 items / 4 clusters | 3 beats, **0 checks** (pruned: 5 unknown-item beats, 4 unknown-kind checks, 1 dangling, 1 bad ref); `validate()` clean | flows; payload eaten by pruner |
| quest Track A (story beats) | 3 beats, 0 checks | VISITED=3 ATTEMPTS=0 XP=0 `quest_complete` | degenerate but honest |
| author fallback (control) | same book, llm=None | 4 beats, 4 checks, 0 pruned, valid | healthy control |
| quest Track B ×2 personas | 4 beats, 4 checks | both complete; crisp differentiation (see §4) | healthy |

No crashes, no schema violations, no hallucinated content ever reached a
learner: the pruner + `validate()` + atomicity gate caught everything.
Circulation works; the organs are under-fed.

## 3. Quality findings (ranked)

**Q1 — Extraction recall collapse (critical).** 25 KB / ~12 real concepts
→ 2 items. Three compounding causes, all in prompts, none in the model:
(a) EXTRACT has no coverage instruction (10 entities from 113 blocks);
(b) itemize has no coverage/count instruction (4–6 candidates);
(c) the atomicity gate drops 30–66% on the verb heuristic — including
good items whose descriptions lack a whitelist verb ("understand" is not
even in `_VERBS`; survivors pass accidentally on copulas like "is").
Proven by a diagnostic re-run with the gate log printed.

**Q2 — Story authoring loses to its own pruner (critical).** The STORY
prompt never states the check-kind vocabulary (`choice|ordering|numeric`)
→ every invented kind is pruned (4× `unknown_kind`). One-item clusters
(one per item, a downstream effect of Q1) starve the model of context →
it cites off-cluster items → 5× `beats_unknown_item`. Net: 0 checks.
The fallback path (same book) yields 4/4 valid checks — the quest side is
innocent; the live authoring prompts are guilty.

**Q3 — Single-pass quest: failed beats are never revisited (major).**
One shot per beat (+retries), then the quest moves on forever; Mike's
failed item stays at mastery 0.016 and the quest still "completes".
No review loop; M3's SRS machinery is not wired into questing.

**Q4 — Mastery is mathematically unreachable (major).** BKT is
implemented correctly (verified by hand: 0.333 / 0.363 / 0.016 all match
canonical BKT with p_init=0, p_learn=0.1, p_slip=0.1, p_guess=0.2), but
with p_init=0 it takes **4 consecutive correct** to reach the 0.95
threshold, while a single-pass quest offers ≤2 attempts per item (max
observed: 0.363). The MASTERED event can never fire; `mastered` is always
empty, so fringe-based adaptivity is dead in practice.

**Q5 — Checks test recognition only (minor).** Fallback checks are
description→label MCQs: functional and answerable, but DOK-1 regardless
of the item's DOK; `ordering`/`numeric` kinds exist in the schema but no
author path emits them.

**Q6 — Per-chapter token reporting double-counts with shared clients
(minor).** ch2's report says 23,588 = cumulative client total, not the
8,095 delta. (Mock path is unaffected: fresh client per chapter.)

**Q7 — Live runs are not reproducible (observation, n=2).** temperature
0.0 yet two EXTRACT runs gave 10 vs 8 entities with different items.
Mock goldens stay the reproducibility story; live output will always vary.

Bright spots: provenance is honest (the ownership item's span points at
the actual 3-rules paragraph); edge precision is 2/2 with correct
prerequisite direction; within-chapter quest order respects the DAG;
xAPI is valid (`actor/verb/object/result/timestamp`, 14–16 statements per
single quest); item precision is 100% (4/4 real concepts, zero
hallucinations); coverage ≈24% (4 of ~17 manual concepts).

## 4. Persona experiment (Track B, fallback beats)

Beat order was identical for both (small graph, fixed fringe); behavior
diverged exactly as scripted via an interactive driver (responses chosen
per revealed check; retry-window aware):

| | Sara (careful beginner) | Mike (rushed, overconfident) |
|---|---|---|
| script | MISS then recover, then clean | OK, burn retry (fail), MISS then fix, OK |
| transcript | MISS→OK, OK, OK, OK | OK, MISS→MISS, MISS→OK, OK |
| attempts / passed | 5 / 4 | 6 / 3 |
| XP / streak_max | 40 / 4 | 30 / 2 |
| retries / flow ratio | 1 / 0.4 | 2 / 0.0 |
| mastery profile | .363/.333/.333/.333 | .333/.016/.363/.333 |
| completion | quest_complete | quest_complete |

The engine differentiates learners crisply: XP, streaks, flow, and
per-item mastery all separate. Lovely detail: Sara's retry-recovered item
scores highest (0.363) — recovery is rewarded. Gap: with only 4 items the
policy never reorders; adaptivity-at-scale is untested.

## 5. How close to the idea? (scorecard, /5)

| dimension | score | note |
|---|---|---|
| concept extraction recall | 2 | Q1: prompts under-specify coverage |
| grounding honesty | 5 | real spans, 100% item precision, pruner holds |
| validators / safety | 5 | nothing invalid reached a learner, ever |
| quest + adaptivity machinery | 3 | works, differentiates; single-pass, no reorder shown |
| mastery model (BKT) | 3 | math correct; threshold unreachable (Q4) |
| check depth | 2 | recognition-only (Q5) |
| cross-chapter prerequisites | 1 | merge is union-only; borrowing→ownership link missing |
| xAPI / observability | 4 | valid, sane counts; driver-inflated counts noted |
| persona differentiation | 4 | §4: crisp separation on all signals |
| live determinism | 2 | Q7: varies run to run |

Verdict: the skeleton and circulation are proven — stages compose, guards
hold, quests run, learners separate. The muscles are weak: live content
volume and check quality. The product today is a **correct adaptive quest
engine running on a starvation diet** — one prompt-hardening milestone
from being genuinely instructive.

## 6. Fix proposals (ordered, concrete; none applied)

- F1. EXTRACT: add coverage instruction ("extract ALL key concepts…,
  one entity per distinct concept") + per-section chunking.
- F2. Itemize: add coverage instruction + verb guidance ("descriptions
  must begin with an observable verb"); extend `_VERBS` (understand,
  apply, analyze…) or gate on `assessment_criteria` instead.
- F3. STORY prompt: state the kind vocabulary + payload shapes; pass the
  FULL item-id list with cluster items marked primary.
- F4. Attainable mastery: threshold per evidence count (e.g. 0.6 after
  one check), multi-check beats, or wire M3 SRS review loops into quests.
- F5. Cross-chapter surmise at merge (or chapter-context in M1).
- F6. Per-chapter token deltas for shared clients.
- F7. Failed-beat re-queue (or a review quest) instead of abandonment.
- F8. Emit ordering/numeric checks; raise fallback checks above label
  matching.

## Machine lines

EVAL_SUBJECT=a915b8a MATERIAL=rust-book-ch04-01+02 LIVE_REQUESTS=12 LIVE_TOKENS=~34000
M1_ITEMS_PER_CH=2 COVERAGE_RECALL=0.24 ITEM_PRECISION=1.0 EDGE_PRECISION=2/2
TRACK_A=degenerate(ATTEMPTS=0,complete) TRACK_B_SARA=40xp/5att/4pass TRACK_B_MIKE=30xp/6att/3pass
BKT_MATH=correct MASTERY_REACHABLE=no PROVENANCE=honest XAPI=valid
TOP_FIXES=extract-coverage+itemize-verbs+story-kinds+mastery-threshold

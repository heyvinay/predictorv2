"""Schemas for the knockout-fixture match-detail endpoint.

The /api/predictions/matches/{id}/ko-detail bundle answers four questions
about a single knockout fixture, in one round-trip:

1. **Pool split** — how did the pool advancement-vote between the two
   teams, broken out by Atlas / JMFA / Guests cohort.
2. **Implications** — per outcome, how many entries are still alive at
   each downstream stage (R16, QF, SF, Final, Champion).
3. **Most exposed entries** — the five entries with the highest cumulative
   points-at-stake on each side, summed across every knockout stage where
   the entry picked the corresponding team.
4. **Pool roll** — the full pool-pick list with rank, sortable by side.

Phase-1 filtered throughout (CLAUDE.md invariant — Phase 2 is dormant).
"""

import uuid

from pydantic import BaseModel


class KoCohortBreakdown(BaseModel):
    """Per-cohort entry counts. Sums to the side's total ``count``."""

    atlas: int
    jmfa: int
    guests: int


class KoPoolSplitSide(BaseModel):
    """One side of the advancement vote."""

    team: str
    count: int
    pct: int  # rounded percent of the eligible pool
    cohorts: KoCohortBreakdown


class KoPoolSplit(BaseModel):
    """Advancement vote across the eligible pool.

    ``home.count`` + ``away.count`` will exceed ``total`` whenever some
    entries picked BOTH teams in the same advancement list (impossible
    structurally — only one R32 winner advances — but the wizard doesn't
    block it, and the user might have meant the second pick for a sibling
    fixture). ``both_picked`` quantifies that overlap; ``neither_picked``
    is the dual residual.
    """

    total: int  # eligible entry count
    home: KoPoolSplitSide
    away: KoPoolSplitSide
    both_picked: int  # entries that have BOTH teams in the bank-stage pick list
    neither_picked: int  # entries with NEITHER team picked at the bank stage


class KoImplicationSide(BaseModel):
    """How many entries stay alive at each later stage if this side wins.

    ``r32_outcome`` is the immediate payout — every entry whose R32 pick
    matches this side banks it. The later counts are independent: they
    don't condition on the entry having picked R32 correctly. The point
    is to show how many entries have this team threaded through their
    bracket at later stages — a "ripple" reading, not a strict reachability
    one.
    """

    team: str
    r32_outcome: int
    alive_r16: int
    alive_qf: int
    alive_sf: int
    alive_final: int
    alive_winner: int


class KoImplications(BaseModel):
    """Per-side downstream-stage exposure."""

    home: KoImplicationSide
    away: KoImplicationSide


class KoExposedEntry(BaseModel):
    """One entry in the most-exposed list.

    ``points_at_stake`` is the sum of advancement-point values for every
    knockout stage where this entry has this team picked, including
    round_of_32 itself. So an entry that took Canada at R32 + QF + SF
    has points_at_stake = 20 + 40 + 50 = 110 (using the WC2026 YAML
    values).
    """

    entry_id: uuid.UUID
    user_name: str
    entry_reference: str | None
    entry_name: str
    rank: int | None
    points_at_stake: int
    stages_at_stake: list[str]


class KoMostExposed(BaseModel):
    """Top entries on each side by cumulative points-at-stake."""

    home: list[KoExposedEntry]
    away: list[KoExposedEntry]


class KoPoolRollEntry(BaseModel):
    """One entry in the full pool-roll list."""

    entry_id: uuid.UUID
    user_name: str
    entry_reference: str | None
    entry_name: str
    pick: str  # the team the entry picked to advance from this fixture
    rank: int | None


class KoMatchDetailResponse(BaseModel):
    """Bundled knockout-fixture match-detail payload."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    stage: str
    pool_split: KoPoolSplit
    implications: KoImplications
    most_exposed: KoMostExposed
    pool_roll: list[KoPoolRollEntry]

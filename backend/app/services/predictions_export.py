"""All-entries predictions CSV export (transparency control).

One wide-matrix CSV showing every eligible (scoring) entry's complete
predictions side-by-side: four label columns, then one column per entry.
Published to the whole pool post-release so anyone can download the same
sheet and verify nobody's picks changed after the deadline.

Spec: docs/superpowers/specs/2026-06-11-all-entries-csv-export-design.md
Mockup: mockups/AllEntriesExport/AllEntries.xlsx

Layout invariants:
- Knockout rows list each entry's predicted advancing teams ALPHABETICALLY
  — TeamPrediction stores an unordered set per stage, not slots, so row
  position carries no meaning (a preamble note says so).
- Missing picks render as blank cells; rows are never dropped (a knockout
  section grows past its quota if any entry somehow holds extra picks).
- Stage keys are the canonical SINGULAR values (v2.161.0 invariant);
  `third_place` is not a bracket stage and never appears.
"""

import csv
import io
import uuid
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

# Sheet timestamps are rendered in Malta time per the pool owner's
# preference. Storage stays UTC (per the datetime invariant in CLAUDE.md);
# this is purely a display layer. ZoneInfo handles CET ↔ CEST DST
# transitions automatically — World Cup 2026 sits entirely in CEST.
_DISPLAY_TZ = ZoneInfo("Europe/Malta")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.fixture import MatchStatus
from app.models.score import Score
from app.models.bonus import BonusAnswer
from app.services.bonus import answer_in, get_questions as get_bonus_questions
from app.services.scoring import (
    compute_match_points,
    eligible_entry_ids_select,
    get_actual_advancement,
    get_all_outcome_counts,
    get_scoring_config,
)

# Display order + per-stage quotas (32+16+8+4+2+1 = 63 bracket picks).
KNOCKOUT_SECTIONS: list[tuple[str, str, str, int]] = [
    ("round_of_32", "ROUND OF 32 — predicted to reach", "R32 pick", 32),
    ("round_of_16", "ROUND OF 16 — predicted to reach", "R16 pick", 16),
    ("quarter_final", "QUARTER-FINALS — predicted to reach", "QF pick", 8),
    ("semi_final", "SEMI-FINALS — predicted to reach", "SF pick", 4),
    ("final", "FINAL — predicted finalists", "Finalist", 2),
    ("winner", "CHAMPION", "Champion", 1),
]

_FORMULA_LEADERS = ("=", "+", "-", "@")

# Number of fixed label columns before the per-entry columns start.
LABEL_COLS = 4


def _safe(value: str | None) -> str:
    """Excel formula-injection guard for user-supplied strings.

    Person names, entry names and bonus answers are user-typed; a value
    like `=HYPERLINK(...)` must not execute when the CSV is opened in a
    spreadsheet. Leading apostrophe forces text interpretation.
    """
    if not value:
        return ""
    return f"'{value}" if value.startswith(_FORMULA_LEADERS) else value


def _fmt_dt(dt: datetime | None) -> str:
    """Compact Malta-time timestamp for humans; blank when missing.

    Storage stays UTC (per the datetime invariant); this only changes
    the rendered string. ``astimezone`` handles DST transitions.
    """
    if dt is None:
        return ""
    return aware_utc(dt).astimezone(_DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


def _person_name(entry: PredictionEntry) -> str:
    """Owner display name — user.name, else the email local part."""
    u = entry.user
    if u is None:
        return ""
    return u.name or u.email.split("@", 1)[0]


async def build_all_entries_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Build the full export as a list of rows (one cell per element).

    This is the single source of truth for the all-entries picks layout.
    ``build_all_entries_export`` serializes these rows to CSV; the Google
    Sheets sync (``app.services.sheets_sync``) writes the same rows into a
    worksheet — so the downloadable CSV and the published sheet can never
    drift apart.

    Eligible entries only — SUBMITTED, not disabled, not withdrawn — the
    same predicate scoring pays (``eligible_entry_ids_select``). All
    loads are bulk; nothing here is per-entry round-trips.
    """
    entries_result = await session.execute(
        select(PredictionEntry)
        .options(
            selectinload(PredictionEntry.user),
            selectinload(PredictionEntry.phases),
        )
        .where(
            PredictionEntry.competition_id == competition.id,
            PredictionEntry.id.in_(eligible_entry_ids_select()),
        )
        .order_by(PredictionEntry.entry_number)
    )
    entries = list(entries_result.scalars().all())
    entry_ids = [e.id for e in entries]

    fixtures_result = await session.execute(
        select(Fixture)
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage == "group",
        )
        # match_number is NULL in prod (CLAUDE.md) — kickoff is the
        # stable primary order; group + id break same-slot ties.
        .order_by(Fixture.kickoff, Fixture.group, Fixture.id)
    )
    group_fixtures = list(fixtures_result.scalars().all())

    # (entry_id, fixture_id) -> "h-a"
    scores: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
    if entry_ids:
        mp_rows = await session.execute(
            select(
                MatchPrediction.entry_id,
                MatchPrediction.fixture_id,
                MatchPrediction.home_score,
                MatchPrediction.away_score,
            ).where(
                MatchPrediction.entry_id.in_(entry_ids),
                MatchPrediction.phase == PredictionPhase.PHASE_1,
            )
        )
        for eid, fid, h, a in mp_rows:
            scores[(eid, fid)] = f"{h}-{a}"

    # entry_id -> stage -> alphabetical team list
    bracket: dict[uuid.UUID, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    if entry_ids:
        tp_rows = await session.execute(
            select(
                TeamPrediction.entry_id,
                TeamPrediction.stage,
                TeamPrediction.team,
            ).where(
                TeamPrediction.entry_id.in_(entry_ids),
                TeamPrediction.phase == PredictionPhase.PHASE_1,
            )
        )
        for eid, stage, team in tp_rows:
            bracket[eid][stage].append(team)
        for stages in bracket.values():
            for teams in stages.values():
                teams.sort()

    questions = get_bonus_questions()
    # (entry_id, question_id) -> answer
    bonus: dict[tuple[uuid.UUID, str], str] = {}
    if entry_ids and questions:
        bp_rows = await session.execute(
            select(
                BonusPrediction.entry_id,
                BonusPrediction.question_id,
                BonusPrediction.answer,
            ).where(
                BonusPrediction.entry_id.in_(entry_ids),
                BonusPrediction.question_id.in_([q.id for q in questions]),
            )
        )
        for eid, qid, answer in bp_rows:
            bonus[(eid, qid)] = answer or ""

    def submitted_at(entry: PredictionEntry) -> datetime | None:
        for phase_row in entry.phases:
            if phase_row.phase == PredictionPhase.PHASE_1:
                return phase_row.submitted_at
        return None

    pad = [""] * LABEL_COLS

    rows: list[list[str]] = []

    # ── preamble — a printed/forwarded copy stays self-describing ──
    rows.append([f"{competition.name} — all entries & predictions"])
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(["Deadline (Malta)", _fmt_dt(competition.phase1_deadline)])
    rows.append(["Entries", str(len(entries))])
    rows.append(
        [
            "Knockout rows list each entry's predicted advancing teams "
            "alphabetically — row position carries no meaning."
        ]
    )
    # v2.174.0 — name the provisional status of any standings/points that
    # might be derived from this sheet. The export itself carries picks,
    # not points, but the leaderboard derives from it and people may
    # forward this around as a printed receipt.
    rows.append(
        [
            "Standings derived from this sheet are PROVISIONAL — finalized "
            "by manual review after the tournament concludes."
        ]
    )
    rows.append([])

    # ── per-entry identity block ──
    rows.append(pad[:-1] + ["Ref"] + [e.reference for e in entries])
    rows.append(pad[:-1] + ["Name"] + [_safe(_person_name(e)) for e in entries])
    rows.append(pad[:-1] + ["Entry"] + [_safe(e.display_name or "") for e in entries])
    rows.append(
        pad[:-1] + ["Submitted (Malta)"] + [_fmt_dt(submitted_at(e)) for e in entries]
    )
    rows.append([])

    # ── group stage ──
    rows.append(["GROUP STAGE — predicted scores"])
    rows.append(["Date (Malta)", "Group", "Home", "Away"])
    for f in group_fixtures:
        rows.append(
            [
                _fmt_dt(f.kickoff),
                f.group or "",
                f.home_team,
                f.away_team,
            ]
            + [scores.get((e.id, f.id), "") for e in entries]
        )

    # ── knockout stages ──
    for stage_key, banner, row_label, quota in KNOCKOUT_SECTIONS:
        rows.append([])
        rows.append([banner])
        per_entry = [bracket[e.id].get(stage_key, []) for e in entries]
        # Never drop data: grow past the quota if an entry holds extras.
        n_rows = max([quota] + [len(p) for p in per_entry])
        for i in range(n_rows):
            label = row_label if quota == 1 else f"{row_label} {i + 1}"
            rows.append(
                ["", "", label, ""]
                + [p[i] if i < len(p) else "" for p in per_entry]
            )

    # ── bonus questions ──
    if questions:
        rows.append([])
        rows.append(["BONUS QUESTIONS"])
        for q in questions:
            rows.append(
                ["", "", q.label, ""]
                + [_safe(bonus.get((e.id, q.id), "")) for e in entries]
            )

    return rows


# Knockout banners for the combined picks+points view. Mirrors KNOCKOUT_SECTIONS
# but uses "picks & points" wording since each row's cells carry both.
_KO_COMBINED_BANNERS: dict[str, str] = {
    "round_of_32": "ROUND OF 32 — picks & points",
    "round_of_16": "ROUND OF 16 — picks & points",
    "quarter_final": "QUARTER-FINALS — picks & points",
    "semi_final": "SEMI-FINALS — picks & points",
    "final": "FINAL — picks & points",
    "winner": "CHAMPION — picks & points",
}

# Stage ordering for advancement comparison (mirrors
# scoring.calculate_advancement_points). A team in stage X earns points only
# if its actual highest stage ≥ X.
_STAGE_ORDER: list[str] = [
    "group",
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
]
_STAGE_RANK: dict[str, int] = {s: i for i, s in enumerate(_STAGE_ORDER)}

# Label columns in the combined sheet: Date | Group | Home | Away | Actual.
COMBINED_LABEL_COLS = 5


async def build_combined_picks_points_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """One wide matrix combining every entry's picks AND their points.

    Layout: five label columns — Date / Group / Home / Away / Actual — then
    TWO columns per eligible entry: ``Pick`` (the prediction text) and
    ``Pts`` (the points scoring currently pays for that pick). The Actual
    column holds the real result of the fixture (group), the qualified
    team(s) listed alphabetically per row (knockout), or the recorded
    correct answer(s) (bonus).

    Group-stage Pts cells use ``base+rarity`` when scoring mode is
    logarithmic and the rarity bonus is non-zero (e.g. ``5+2``, ``15+2``).
    Otherwise just the integer (``5``, ``15``, ``0``). Blank cells = the
    underlying result hasn't been recorded yet — visually distinct from
    a scored zero.

    Eligible entries only — SUBMITTED, not withdrawn, not disabled — via
    ``eligible_entry_ids_select`` (same predicate scoring pays).
    """
    entries_result = await session.execute(
        select(PredictionEntry)
        .options(
            selectinload(PredictionEntry.user),
            selectinload(PredictionEntry.phases),
        )
        .where(
            PredictionEntry.competition_id == competition.id,
            PredictionEntry.id.in_(eligible_entry_ids_select()),
        )
    )
    entries = list(entries_result.scalars().all())
    # Order column pairs by user name (case-insensitive) so a person with
    # multiple entries sees them adjacent in the sheet. entry_number is the
    # secondary key — keeps each person's entries in their own creation
    # order. Bracket / predictions / bonus dicts are entry_id-keyed, so the
    # rest of this function is order-agnostic.
    entries.sort(key=lambda e: (_person_name(e).lower(), e.entry_number))
    entry_ids = [e.id for e in entries]

    fixtures_result = await session.execute(
        select(Fixture)
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage == "group",
        )
        .order_by(Fixture.kickoff, Fixture.group, Fixture.id)
    )
    group_fixtures = list(fixtures_result.scalars().all())

    predictions: dict[tuple[uuid.UUID, uuid.UUID], tuple[int, int]] = {}
    if entry_ids:
        mp_rows = await session.execute(
            select(
                MatchPrediction.entry_id,
                MatchPrediction.fixture_id,
                MatchPrediction.home_score,
                MatchPrediction.away_score,
            ).where(
                MatchPrediction.entry_id.in_(entry_ids),
                MatchPrediction.phase == PredictionPhase.PHASE_1,
            )
        )
        for eid, fid, h, a in mp_rows:
            predictions[(eid, fid)] = (h, a)

    bracket: dict[uuid.UUID, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    if entry_ids:
        tp_rows = await session.execute(
            select(
                TeamPrediction.entry_id,
                TeamPrediction.stage,
                TeamPrediction.team,
            ).where(
                TeamPrediction.entry_id.in_(entry_ids),
                TeamPrediction.phase == PredictionPhase.PHASE_1,
            )
        )
        for eid, stage, team in tp_rows:
            bracket[eid][stage].append(team)
        for stages in bracket.values():
            for teams in stages.values():
                teams.sort()

    questions = get_bonus_questions()
    bonus: dict[tuple[uuid.UUID, str], str] = {}
    if entry_ids and questions:
        bp_rows = await session.execute(
            select(
                BonusPrediction.entry_id,
                BonusPrediction.question_id,
                BonusPrediction.answer,
            ).where(
                BonusPrediction.entry_id.in_(entry_ids),
                BonusPrediction.question_id.in_([q.id for q in questions]),
            )
        )
        for eid, qid, answer in bp_rows:
            bonus[(eid, qid)] = answer or ""

    # ── results to score against ──
    actual_scores: dict[uuid.UUID, tuple[int, int]] = {}
    sc_rows = await session.execute(
        select(Score.fixture_id, Score.home_score, Score.away_score)
        .join(Fixture, Score.fixture_id == Fixture.id)
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    for fid, h, a in sc_rows.all():
        actual_scores[fid] = (h, a)

    actual_advancement = await get_actual_advancement(session)
    outcome_counts_by_fixture = await get_all_outcome_counts(session)

    ans_rows = (
        await session.execute(
            select(BonusAnswer).where(BonusAnswer.competition_id == competition.id)
        )
    ).scalars().all()
    correct_by_qid: dict[str, list[str]] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)

    scoring_config = get_scoring_config()
    mode = scoring_config.get("mode", "logarithmic")
    match_config = scoring_config.get("match", {})
    outcome_points = match_config.get("correct_outcome", 5)
    exact_points = match_config.get("exact_score", 10)
    rarity_cap = match_config.get("rarity_cap", match_config.get("hybrid_cap", 10))
    adv_config = scoring_config.get("advancement", {})

    # Per-stage alphabetical lists of teams that actually reached that stage.
    # The known set of real team names comes from the group-stage fixtures
    # (each of the 48 teams appears at least once as home or away). Filtering
    # out anything not in this set drops the placeholder strings that
    # `get_actual_advancement` carries for unplayed KO fixtures (e.g.
    # "Winner Group A", "Runner-up Match 49"). Without this filter the R32
    # "Actual" column would balloon to 32+16+8+4+2 = 62 rows because R16,
    # QF, SF, Final placeholders all sit at a rank ≥ R32.
    real_team_names = {f.home_team for f in group_fixtures} | {
        f.away_team for f in group_fixtures
    }
    actual_teams_at_stage: dict[str, list[str]] = {}
    for stage_key, *_ in KNOCKOUT_SECTIONS:
        stage_idx = _STAGE_RANK.get(stage_key, -1)
        actual_teams_at_stage[stage_key] = sorted(
            t
            for t, top in actual_advancement.items()
            if _STAGE_RANK.get(top, -1) >= stage_idx and t in real_team_names
        )

    def _group_pick(eid: uuid.UUID, fid: uuid.UUID) -> str:
        pred = predictions.get((eid, fid))
        return f"{pred[0]}-{pred[1]}" if pred else ""

    def _group_pts(eid: uuid.UUID, fid: uuid.UUID) -> str:
        actual = actual_scores.get(fid)
        if actual is None:
            return ""
        pred = predictions.get((eid, fid))
        if pred is None:
            return ""
        counts = outcome_counts_by_fixture.get(fid, {"1": 0, "X": 0, "2": 0})
        total_predictors = sum(counts.values())
        if actual[0] > actual[1]:
            actual_outcome = "1"
        elif actual[0] < actual[1]:
            actual_outcome = "2"
        else:
            actual_outcome = "X"
        correct_predictors = counts.get(actual_outcome, 0)
        total, _correct_o, _exact = compute_match_points(
            mode=mode,
            predicted_home=pred[0],
            predicted_away=pred[1],
            actual_home=actual[0],
            actual_away=actual[1],
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=outcome_points,
            exact_points=exact_points,
            cap=rarity_cap,
        )
        # Integer total — rarity bonus is folded into the figure. Inline
        # "5+2" notation was dropped so conditional formatting on the Pts
        # columns can bucket cells into numeric bands (0/1-9/10-19/20+).
        return str(int(total))

    def _adv_pts(team: str, predicted_stage: str) -> str:
        if not team:
            return ""
        actual_stage = actual_advancement.get(team)
        if not actual_stage:
            return ""
        pred_idx = _STAGE_RANK.get(predicted_stage, -1)
        actual_idx = _STAGE_RANK.get(actual_stage, -1)
        if actual_idx >= pred_idx >= 0:
            return str(int(adv_config.get(predicted_stage, 0)))
        return "0"

    def _bonus_pts(eid: uuid.UUID, qid: str, question_points: int) -> str:
        corrects = correct_by_qid.get(qid)
        if not corrects:
            return ""
        answer = bonus.get((eid, qid))
        if not answer:
            return "0"
        return str(int(question_points)) if answer_in(answer, corrects) else "0"

    def submitted_at(entry: PredictionEntry) -> datetime | None:
        for phase_row in entry.phases:
            if phase_row.phase == PredictionPhase.PHASE_1:
                return phase_row.submitted_at
        return None

    label_pad = [""] * COMBINED_LABEL_COLS
    rows: list[list[str]] = []

    # ── preamble ──
    rows.append([f"{competition.name} — all entries: picks & points"])
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(["Deadline (Malta)", _fmt_dt(competition.phase1_deadline)])
    rows.append(["Entries", str(len(entries))])
    rows.append(
        [
            "Each entry has two columns: PICK (the prediction) and PTS "
            "(total points scoring currently pays, rarity bonus folded "
            "in). Pts cells are colour-coded: red = 0, yellow = 1–9, "
            "green = 10–19, blue = 20+. Blank cells = the underlying "
            "result hasn't been recorded yet."
        ]
    )
    rows.append(
        [
            "Provisional — finalized by manual review after the tournament "
            "concludes. Eligible entries only (SUBMITTED, not withdrawn or "
            "disabled)."
        ]
    )
    rows.append([])

    # ── per-entry identity block ──
    def _identity_row(label: str, value_fn) -> list[str]:
        out = label_pad[:-1] + [label]
        for e in entries:
            out.append(value_fn(e))
            out.append("")
        return out

    rows.append(_identity_row("Ref", lambda e: e.reference))
    rows.append(_identity_row("Name", lambda e: _safe(_person_name(e))))
    rows.append(_identity_row("Entry", lambda e: _safe(e.display_name or "")))
    rows.append(_identity_row("Submitted (Malta)", lambda e: _fmt_dt(submitted_at(e))))
    rows.append([])

    # ── entry-name super-header (first cell of each pair carries the name) ──
    # The column header row (Date | Group | Home | Away | Actual | Pick |
    # Pts | …) used to live here at row 13 but was removed per pool-owner
    # feedback — the data rows are self-describing and the super-header
    # above + the GROUP STAGE banner below carry enough structure on
    # their own. If you re-add it, bump _PREDICTIONS_FROZEN_ROWS in
    # sheets_sync.py from 13 back to 14.
    super_header = label_pad[:]
    for e in entries:
        super_header.append(_safe(e.display_name or e.reference))
        super_header.append("")
    rows.append(super_header)

    # ── group stage ──
    rows.append(["GROUP STAGE — picks & points"])
    for f in group_fixtures:
        actual = actual_scores.get(f.id)
        actual_cell = f"{actual[0]}-{actual[1]}" if actual is not None else ""
        cells = [
            _fmt_dt(f.kickoff),
            f.group or "",
            f.home_team,
            f.away_team,
            actual_cell,
        ]
        for e in entries:
            cells.append(_group_pick(e.id, f.id))
            cells.append(_group_pts(e.id, f.id))
        rows.append(cells)

    # ── knockout stages ──
    for stage_key, _banner, row_label, quota in KNOCKOUT_SECTIONS:
        rows.append([])
        rows.append([_KO_COMBINED_BANNERS[stage_key]])
        per_entry = [bracket[e.id].get(stage_key, []) for e in entries]
        actual_at_stage = actual_teams_at_stage.get(stage_key, [])
        n_rows = max(
            [quota, len(actual_at_stage)] + [len(p) for p in per_entry]
        )
        for i in range(n_rows):
            label = row_label if quota == 1 else f"{row_label} {i + 1}"
            actual_cell = actual_at_stage[i] if i < len(actual_at_stage) else ""
            cells = ["", "", label, "", actual_cell]
            for idx in range(len(entries)):
                team = per_entry[idx][i] if i < len(per_entry[idx]) else ""
                cells.append(team)
                cells.append(_adv_pts(team, stage_key))
            rows.append(cells)

    # ── bonus questions ──
    if questions:
        rows.append([])
        rows.append(["BONUS QUESTIONS — picks & points"])
        for q in questions:
            corrects = correct_by_qid.get(q.id, [])
            actual_cell = " / ".join(_safe(c) for c in corrects) if corrects else ""
            cells = ["", "", q.label, "", actual_cell]
            for e in entries:
                ans = bonus.get((e.id, q.id), "")
                cells.append(_safe(ans))
                cells.append(_bonus_pts(e.id, q.id, q.points))
            rows.append(cells)

    return rows


async def build_tournament_summary_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Compact dashboard of tournament-wide stats for the published sheet.

    Sections: pool composition (by employer), tournament progress (fixtures
    played by stage + next-up match), pool scoring snapshot (avg / median /
    range / totals), and category leaders (most exact scores, most rarity
    bonus earned, most popular champion pick). All data is derived from
    the leaderboard cache + a single fixtures query — no per-entry round-
    trips, so this is cheap to refresh on every sync tick.
    """
    from collections import Counter  # noqa: PLC0415
    from app.services.leaderboard import calculate_leaderboard  # noqa: PLC0415

    board = await calculate_leaderboard(session, phase="phase_1")

    fixtures_result = await session.execute(
        select(Fixture)
        .where(Fixture.competition_id == competition.id)
        .order_by(Fixture.kickoff)
    )
    fixtures = list(fixtures_result.scalars().all())

    finished_count = sum(1 for f in fixtures if f.status == MatchStatus.FINISHED)
    group_total = sum(1 for f in fixtures if f.stage == "group")
    group_finished = sum(
        1 for f in fixtures
        if f.stage == "group" and f.status == MatchStatus.FINISHED
    )
    ko_stages = {
        "round_of_32", "round_of_16", "quarter_final",
        "semi_final", "final",
    }
    ko_total = sum(1 for f in fixtures if f.stage in ko_stages)
    ko_finished = sum(
        1 for f in fixtures
        if f.stage in ko_stages and f.status == MatchStatus.FINISHED
    )

    next_match = next(
        (f for f in fixtures if f.status != MatchStatus.FINISHED),
        None,
    )

    employer_counts: Counter = Counter()
    for e in board.entries:
        emp_raw = (e.employer or "guests").lower()
        emp = {"atlas": "Atlas", "jmfa": "JMFA"}.get(emp_raw, "Guests")
        employer_counts[emp] += 1

    points_sorted = sorted([e.total_points for e in board.entries], reverse=True)
    if points_sorted:
        avg_pts = sum(points_sorted) / len(points_sorted)
        median_pts = points_sorted[len(points_sorted) // 2]
        max_pts = points_sorted[0]
        min_pts = points_sorted[-1]
        total_pts_pool = sum(points_sorted)
    else:
        avg_pts = median_pts = max_pts = min_pts = total_pts_pool = 0

    total_exacts = sum(e.exact_scores for e in board.entries)
    total_rarity = sum(
        e.breakdown.phase1.hybrid_bonus_points for e in board.entries
    )

    champion_counter: Counter = Counter()
    for e in board.entries:
        if e.champion_pick:
            champion_counter[e.champion_pick] += 1

    top_exact = (
        max(board.entries, key=lambda e: e.exact_scores)
        if board.entries
        else None
    )
    top_rarity = (
        max(board.entries, key=lambda e: e.breakdown.phase1.hybrid_bonus_points)
        if board.entries
        else None
    )
    top_champion = champion_counter.most_common(1)

    def _entry_display(e) -> str:
        return f"{_person_name(e) if False else e.user_name} ({e.entry_name})"

    rows: list[list[str]] = []
    rows.append([f"{competition.name} — Tournament Summary"])
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(
        [
            "A snapshot of where the tournament + the pool stands right now. "
            "Refreshed every score tick alongside the other tabs."
        ]
    )
    rows.append([])

    rows.append(["POOL COMPOSITION"])
    rows.append(["Eligible entries", str(len(board.entries))])
    for emp, count in sorted(employer_counts.items(), key=lambda x: -x[1]):
        pct = (count / len(board.entries) * 100) if board.entries else 0
        rows.append([f"  {emp}", f"{count} ({pct:.0f}%)"])
    rows.append([])

    rows.append(["TOURNAMENT PROGRESS"])
    rows.append(
        ["Total fixtures played", f"{finished_count} of {len(fixtures)}"]
    )
    rows.append(
        ["  Group stage", f"{group_finished} of {group_total} matches"]
    )
    rows.append(["  Knockout", f"{ko_finished} of {ko_total} matches"])
    if next_match:
        stage_label = (
            "Group" if next_match.stage == "group"
            else next_match.stage.replace("_", " ").title()
        )
        rows.append(
            [
                "Next match",
                f"{_fmt_dt(next_match.kickoff)} · {stage_label}"
                f"{' ' + (next_match.group or '') if next_match.group else ''}"
                f" — {next_match.home_team} vs {next_match.away_team}",
            ]
        )
    rows.append([])

    if board.entries:
        rows.append(["POOL SCORING"])
        leader = board.entries[0]
        rows.append(
            ["Highest score", f"{max_pts} — {leader.user_name} ({leader.entry_name})"]
        )
        rows.append(["Lowest score", str(min_pts)])
        rows.append(["Average score", f"{avg_pts:.1f}"])
        rows.append(["Median score", str(median_pts)])
        rows.append(["Total points in pool", f"{total_pts_pool:,}"])
        rows.append(["Total exact scores", str(total_exacts)])
        rows.append(["Total rarity points earned", str(total_rarity)])
        rows.append([])

        rows.append(["LEADERS"])
        if top_exact and top_exact.exact_scores > 0:
            rows.append(
                [
                    "Most exact scores",
                    f"{top_exact.exact_scores} — {top_exact.user_name} "
                    f"({top_exact.entry_name})",
                ]
            )
        if top_rarity and top_rarity.breakdown.phase1.hybrid_bonus_points > 0:
            rows.append(
                [
                    "Most rarity points",
                    f"{top_rarity.breakdown.phase1.hybrid_bonus_points} — "
                    f"{top_rarity.user_name} ({top_rarity.entry_name})",
                ]
            )
        if top_champion:
            team, count = top_champion[0]
            pct = (count / len(board.entries) * 100) if board.entries else 0
            rows.append(
                [
                    "Most popular Champion pick",
                    f"{team} — {count} entries ({pct:.0f}%)",
                ]
            )
        rows.append([])

    return rows


async def build_rules_rows(
    session: AsyncSession, competition: Competition  # noqa: ARG001 — session kept for parity
) -> list[list[str]]:
    """Static scoring-rules reference rendered from config + bonus questions.

    Pure read of `get_scoring_config()` and `get_bonus_questions()` — same
    sources the scoring engine uses, so this tab can never drift from
    what's actually awarded.
    """
    config = get_scoring_config()
    mode = config.get("mode", "logarithmic")
    match_cfg = config.get("match", {})
    adv_cfg = config.get("advancement", {})
    questions = get_bonus_questions()

    rows: list[list[str]] = []
    rows.append([f"{competition.name} — Scoring Rules"])
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(
        [
            "Scoring values mirrored from config/worldcup2026.yml — same "
            "source the scoring engine reads, so this tab can never drift "
            "from what's actually awarded."
        ]
    )
    rows.append([])

    rows.append(["MATCH PREDICTIONS  (group stage only)"])
    # NOTE: leading "+" needs the formula-guard apostrophe via _safe() — with
    # USER_ENTERED mode Sheets otherwise tries to parse "+5 pts" as an
    # arithmetic expression and renders #ERROR!.
    rows.append(
        ["Correct outcome (1 / X / 2)", _safe(f"+{match_cfg.get('correct_outcome', 5)} pts")]
    )
    rows.append(
        ["Exact score (in addition to outcome)", _safe(f"+{match_cfg.get('exact_score', 10)} pts")]
    )
    if mode == "logarithmic":
        cap = match_cfg.get("rarity_cap", match_cfg.get("hybrid_cap", 10))
        rows.append(
            ["Rarity bonus (logarithmic, on a correct outcome)", f"up to +{cap} pts"]
        )
        rows.append(
            [
                "  How the rarity bonus works",
                "Larger bonus when fewer entries got the outcome right. "
                f"Cap reached at ~3.3% (≈1/30 of eligible entries). "
                "Consensus picks (>50%) earn no rarity bonus. See the "
                "Rarity tab for the per-fixture breakdown.",
            ]
        )
    rows.append([])

    rows.append(["KNOCKOUT ADVANCEMENT  (per team predicted to reach)"])
    stage_labels = [
        ("round_of_32", "Round of 32"),
        ("round_of_16", "Round of 16"),
        ("quarter_final", "Quarter Finals"),
        ("semi_final", "Semi Finals"),
        ("final", "Final"),
        ("winner", "Champion"),
    ]
    for key, label in stage_labels:
        pts = adv_cfg.get(key, 0)
        rows.append([label, _safe(f"+{int(pts)} pts")])
    rows.append(
        [
            "  Timing",
            "Knockout points pay the moment a team is seeded into a "
            "stage-X fixture (lineup-based — no need to wait for the "
            "match to be played). Champion credit fires once the final "
            "is FINISHED and scored.",
        ]
    )
    rows.append([])

    rows.append(["BONUS QUESTIONS"])
    if questions:
        for q in questions:
            rows.append([q.label, _safe(f"+{int(q.points)} pts")])
        rows.append(
            [
                "  How bonuses settle",
                "Full points if the entry's answer matches any of the "
                "recorded correct answers (ties allowed). Group-stage "
                "questions settle after all group matches play; "
                "knockout-stage questions settle after the tournament.",
            ]
        )
    rows.append([])

    rows.append(["ELIGIBILITY"])
    rows.append(
        [
            "Who counts",
            "Eligible entries are those that were SUBMITTED before the "
            "deadline and are neither withdrawn nor disabled. The same "
            "filter is used by the leaderboard and by the rarity-bonus "
            "denominator.",
        ]
    )
    rows.append(
        [
            "Provisional",
            "All standings shown anywhere in this sheet are provisional "
            "and finalised by manual review after the tournament concludes.",
        ]
    )

    return rows


async def build_rarity_explainer_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Per-fixture rarity-bonus breakdown for the published sheet.

    One row per FINISHED group-stage fixture, sorted by rarity bonus
    descending (most surprising results at the top, ties broken by most-
    recent date). Each row carries the raw counts + a plain-English
    explanation so a reader can see why a specific fixture paid +6 vs +0
    rarity without doing the Shannon math themselves.

    Knockout fixtures and bonus questions don't use rarity (advancement
    pays flat per the YAML, bonus answers are question-specific), so
    they're excluded.
    """
    scoring_config = get_scoring_config()
    mode = scoring_config.get("mode", "logarithmic")
    match_config = scoring_config.get("match", {})
    outcome_points = match_config.get("correct_outcome", 5)
    exact_points = match_config.get("exact_score", 10)
    rarity_cap = match_config.get("rarity_cap", match_config.get("hybrid_cap", 10))

    # Load FINISHED group fixtures + scores.
    finished_result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    finished = list(finished_result.all())

    outcome_counts_by_fixture = await get_all_outcome_counts(session)

    # Build (fixture, score, total, correct, rarity, actual_outcome) tuples.
    explained: list[tuple] = []
    for fixture, score in finished:
        actual_home = score.final_home_score
        actual_away = score.final_away_score
        if actual_home > actual_away:
            actual_outcome = "1"
            outcome_label = f"{fixture.home_team} win"
        elif actual_home < actual_away:
            actual_outcome = "2"
            outcome_label = f"{fixture.away_team} win"
        else:
            actual_outcome = "X"
            outcome_label = "Draw"

        counts = outcome_counts_by_fixture.get(
            fixture.id, {"1": 0, "X": 0, "2": 0}
        )
        total_predictors = sum(counts.values())
        correct_predictors = counts.get(actual_outcome, 0)

        # Compute rarity by asking the scoring engine for points on a
        # perfect prediction (outcome+exact match) and subtracting the
        # base — gives the pure rarity component the engine would award.
        total_pts, _, _ = compute_match_points(
            mode=mode,
            predicted_home=actual_home,
            predicted_away=actual_away,
            actual_home=actual_home,
            actual_away=actual_away,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=outcome_points,
            exact_points=exact_points,
            cap=rarity_cap,
        )
        rarity = int(total_pts) - outcome_points - exact_points
        rarity = max(0, rarity)  # defensive — fixed-mode returns 0 here anyway

        explained.append(
            (fixture, score, total_predictors, correct_predictors, rarity, outcome_label, actual_outcome, actual_home, actual_away)
        )

    # Sort: kickoff ascending (matches the Predictions tab's group-stage
    # row order — `Fixture.kickoff, Fixture.group, Fixture.id`), so a
    # reader scanning both tabs sees the same fixture sequence.
    explained.sort(
        key=lambda t: (t[0].kickoff, t[0].group or "", str(t[0].id))
    )

    rows: list[list[str]] = []
    rows.append([f"{competition.name} — rarity bonus breakdown"])
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(
        [
            f"Rarity rewards predicting an outcome few others did. Added on top "
            f"of the {outcome_points}-point base for a correct outcome. Caps at "
            f"+{rarity_cap} when ~3.3% (≈1/30) of eligible entries pick it. "
            "Consensus picks (>50%) earn no rarity bonus."
        ]
    )
    rows.append(
        [
            "Listed in kickoff order — same sequence as the Predictions tab. "
            "Rarity Bonus column is colour-banded: red = 0, yellow = 1-3, "
            "green = 4-6, blue = 7+."
        ]
    )
    rows.append([])

    rows.append(
        [
            "Date (Malta)",
            "Group",
            "Home",
            "Away",
            "Result",
            "Outcome",
            "Correct / Total",
            "Pool %",
            "Rarity Bonus",
            "Why",
        ]
    )

    if not explained:
        rows.append(
            [
                "",
                "",
                "",
                "",
                "No FINISHED group-stage fixtures yet — rarity is calculated "
                "after each match completes.",
            ]
        )
        return rows

    for (
        fixture,
        _score,
        total,
        correct,
        rarity,
        outcome_label,
        _outcome_key,
        home_score,
        away_score,
    ) in explained:
        f_pct = (correct / total * 100) if total else 0
        if total == 0:
            why = "No eligible entries predicted this fixture."
        elif rarity == 0:
            why = (
                f"Consensus pick — {correct} of {total} entries ({f_pct:.0f}%) "
                "had the correct outcome → no rarity bonus."
            )
        else:
            why = (
                f"{correct} of {total} entries ({f_pct:.1f}%) picked correctly "
                f"→ +{rarity} rarity bonus on top of the {outcome_points} base."
            )
        rows.append(
            [
                _fmt_dt(fixture.kickoff),
                fixture.group or "",
                fixture.home_team,
                fixture.away_team,
                f"{home_score}-{away_score}",
                outcome_label,
                f"{correct} / {total}",
                f"{f_pct:.1f}%" if total else "—",
                str(rarity),  # integer; Sheets number format adds the "+" prefix
                why,
            ]
        )

    return rows


async def build_snapshot_history_rows(
    session: AsyncSession, competition: Competition, days: int = 60
) -> list[list[str]]:
    """Wide-matrix rank-over-time history for the published Google sheet.

    Layout: three label columns (Rank, Entry, Name) followed by one column
    per calendar day on which AT LEAST ONE eligible entry has a recorded
    snapshot. Cells hold the entry's position on that day (1 = leader),
    or "—" when the daily snapshot for that entry didn't run / didn't exist
    yet.

    Eligible-entry filter comes from the live leaderboard (which already
    excludes withdrawn / disabled / drafts) so the row set matches the
    Standings tab exactly. Rows ordered by *current* rank so the leader is
    at row 1 and the bottom of the pool at row N.

    ``days`` defaults to 60 — comfortably covers the World Cup 2026 window
    (June 11 → mid-July).
    """
    # Lazy imports — keep this module's hot path lean. snapshots.py is
    # only needed here and pulling it in at module-load adds a few extra
    # SQLModel reflection steps the CSV-export path doesn't need.
    from app.services.leaderboard import calculate_leaderboard  # noqa: PLC0415
    from app.services.sheets_sync import _name_entry_label  # noqa: PLC0415
    from app.services.snapshots import get_all_snapshots  # noqa: PLC0415

    board = await calculate_leaderboard(session, phase="phase_1")
    entry_ids = [e.entry_id for e in board.entries]

    snapshots_by_entry = await get_all_snapshots(session, entry_ids, days=days)

    # Union of every snapshot date across entries, sorted DESCENDING —
    # today on the left, oldest on the right, so readers see "what just
    # happened" first when scanning across.
    # Filter out pre-deadline dates: the rank trajectory only becomes
    # meaningful once the pool is locked and matches start scoring;
    # earlier snapshots are all tied/seeded and just add clutter (former
    # cols K-S in the history tab).
    earliest_date = (
        aware_utc(competition.phase1_deadline).date()
        if competition.phase1_deadline
        else None
    )
    all_dates: set = set()
    for snaps in snapshots_by_entry.values():
        for s in snaps:
            if earliest_date is None or s.captured_date >= earliest_date:
                all_dates.add(s.captured_date)
    dates_sorted = sorted(all_dates, reverse=True)

    # (entry_id, date) -> position
    pos_by_entry_date: dict = {}
    for entry_id, snaps in snapshots_by_entry.items():
        for s in snaps:
            pos_by_entry_date[(entry_id, s.captured_date)] = s.position

    rows: list[list[str]] = []
    rows.append(
        [
            f"{competition.name} — rank history "
            f"({len(dates_sorted)} day{'s' if len(dates_sorted) != 1 else ''})"
        ]
    )
    rows.append(["Generated (Malta)", _fmt_dt(utc_now())])
    rows.append(
        [
            "Cells = each entry's rank on that day. Lower is better. "
            "'—' means no snapshot was recorded for that (entry, day) — "
            "either the entry didn't exist yet or the daily snapshot didn't run."
        ]
    )
    rows.append([])

    # Column header row (frozen). Mirrors the Standings tab's "Name - Entry"
    # combined column — default auto-generated entry names ("Entry N") are
    # suppressed so single-entry owners show as just their name.
    header = ["Rank", "Name - Entry"] + [d.strftime("%Y-%m-%d") for d in dates_sorted]
    rows.append(header)

    for e in board.entries:
        row: list[str] = [
            str(e.position),
            _safe(_name_entry_label(e.user_name, e.entry_name)),
        ]
        for d in dates_sorted:
            pos = pos_by_entry_date.get((e.entry_id, d))
            row.append(str(pos) if pos is not None else "—")
        rows.append(row)

    return rows


async def build_all_entries_export(
    session: AsyncSession, competition: Competition
) -> str:
    """Build the full CSV text (BOM-prefixed) for the active competition.

    Thin serializer over ``build_all_entries_rows`` — see that function
    for the data-loading contract and layout invariants.
    """
    rows = await build_all_entries_rows(session, competition)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(rows)

    # BOM so Excel-on-Windows decodes UTF-8 on double-click (Türkiye,
    # Côte d'Ivoire). Harmless everywhere else.
    return "﻿" + buf.getvalue()

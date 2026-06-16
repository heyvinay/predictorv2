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
    """Compact UTC timestamp for humans; blank when missing."""
    if dt is None:
        return ""
    return aware_utc(dt).strftime("%Y-%m-%d %H:%M")


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
    rows.append(["Generated (UTC)", _fmt_dt(utc_now())])
    rows.append(["Deadline (UTC)", _fmt_dt(competition.phase1_deadline)])
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
        pad[:-1] + ["Submitted (UTC)"] + [_fmt_dt(submitted_at(e)) for e in entries]
    )
    rows.append([])

    # ── group stage ──
    rows.append(["GROUP STAGE — predicted scores"])
    rows.append(["Date (UTC)", "Group", "Home", "Away"])
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


# Knockout banners for the points (Results) view — mirrors KNOCKOUT_SECTIONS
# row-for-row so the Results worksheet aligns with Predictions cell-for-cell.
_KO_POINTS_BANNERS: dict[str, str] = {
    "round_of_32": "ROUND OF 32 — points awarded",
    "round_of_16": "ROUND OF 16 — points awarded",
    "quarter_final": "QUARTER-FINALS — points awarded",
    "semi_final": "SEMI-FINALS — points awarded",
    "final": "FINAL — points awarded",
    "winner": "CHAMPION — points awarded",
}

# Stage ordering for advancement comparison (mirrors scoring.calculate_
# advancement_points). A team in stage X earns points only if its actual
# highest stage ≥ X.
_STAGE_ORDER: list[str] = [
    "group",
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
]


async def build_all_entries_points_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Per-cell **points awarded** for every (entry, pick) — mirror of the
    Predictions matrix.

    Same row labels, same column order (one per eligible entry, sorted by
    entry_number), same knockout/bonus layout as ``build_all_entries_rows``
    so the Predictions and Results worksheets read side-by-side cell-for-cell.

    Cells hold:
    - **Group fixture** → points (incl. rarity bonus for mode=logarithmic)
      that scoring currently pays for that pick, via ``compute_match_points``.
    - **Knockout row** → ``advancement[stage]`` if the entry's predicted team
      reached at least that stage; ``"0"`` if the team reached an earlier stage;
      blank if the team hasn't been seeded into any stage yet (the row's
      predicted team is empty for that entry).
    - **Bonus question** → ``question.points`` if the entry's answer matches
      any recorded correct answer; ``"0"`` on miss; blank when the correct
      answer hasn't been recorded yet (question is unsettled).
    - **Blank** anywhere a pick wasn't made, a fixture isn't FINISHED, or
      an answer wasn't recorded.

    Reuses the same pure scoring helpers the leaderboard uses
    (``compute_match_points``, ``get_actual_advancement``, ``answer_in``) so
    per-cell sums reconcile with leaderboard totals.
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
        .order_by(Fixture.kickoff, Fixture.group, Fixture.id)
    )
    group_fixtures = list(fixtures_result.scalars().all())

    # (entry_id, fixture_id) -> (home, away) prediction
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

    # ── extra loads: the actual results to score against ──
    # Group-stage fixtures only — match-result points are only paid on
    # group fixtures in this competition. `final_*` are @property aliases
    # (ET-aware), not Columns, so select the raw home/away_score and trust
    # there's no extra time in group play.
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

    def _match_pts(eid: uuid.UUID, fid: uuid.UUID) -> str:
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
        points, _, _ = compute_match_points(
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
        return str(int(points))

    def _adv_pts(team: str, predicted_stage: str) -> str:
        # Blank row-cell — entry didn't predict a team for this alphabetical slot.
        if not team:
            return ""
        actual_stage = actual_advancement.get(team)
        if not actual_stage:
            # Team hasn't been seeded into ANY knockout stage yet — points
            # for this row are still unresolved (return blank, not 0, to
            # keep "unresolved" visually distinct from "wrong pick").
            return ""
        pred_idx = (
            _STAGE_ORDER.index(predicted_stage)
            if predicted_stage in _STAGE_ORDER
            else -1
        )
        actual_idx = (
            _STAGE_ORDER.index(actual_stage) if actual_stage in _STAGE_ORDER else -1
        )
        if actual_idx >= pred_idx >= 0:
            return str(int(adv_config.get(predicted_stage, 0)))
        return "0"

    def _bonus_pts(eid: uuid.UUID, qid: str, question_points: int) -> str:
        corrects = correct_by_qid.get(qid)
        if not corrects:
            return ""  # unsettled
        answer = bonus.get((eid, qid))
        if not answer:
            return "0"
        return str(int(question_points)) if answer_in(answer, corrects) else "0"

    def submitted_at(entry: PredictionEntry) -> datetime | None:
        for phase_row in entry.phases:
            if phase_row.phase == PredictionPhase.PHASE_1:
                return phase_row.submitted_at
        return None

    pad = [""] * LABEL_COLS

    rows: list[list[str]] = []

    # ── preamble ──
    rows.append([f"{competition.name} — all entries & points awarded"])
    rows.append(["Generated (UTC)", _fmt_dt(utc_now())])
    rows.append(["Deadline (UTC)", _fmt_dt(competition.phase1_deadline)])
    rows.append(["Entries", str(len(entries))])
    rows.append(
        [
            "Each cell holds the points scoring currently pays for that "
            "entry's pick. Blank = the underlying result hasn't been "
            "recorded yet (fixture unplayed, knockout team unseeded, or "
            "bonus question unsettled)."
        ]
    )
    rows.append(
        [
            "Cell-for-cell mirror of the Predictions tab — open both side "
            "by side to compare picks against points."
        ]
    )
    rows.append(
        [
            "Provisional — finalized by manual review after the tournament "
            "concludes."
        ]
    )
    rows.append([])

    # ── per-entry identity block (identical to predictions sheet) ──
    rows.append(pad[:-1] + ["Ref"] + [e.reference for e in entries])
    rows.append(pad[:-1] + ["Name"] + [_safe(_person_name(e)) for e in entries])
    rows.append(pad[:-1] + ["Entry"] + [_safe(e.display_name or "") for e in entries])
    rows.append(
        pad[:-1] + ["Submitted (UTC)"] + [_fmt_dt(submitted_at(e)) for e in entries]
    )
    rows.append([])

    # ── group stage ──
    rows.append(["GROUP STAGE — points awarded"])
    rows.append(["Date (UTC)", "Group", "Home", "Away"])
    for f in group_fixtures:
        rows.append(
            [
                _fmt_dt(f.kickoff),
                f.group or "",
                f.home_team,
                f.away_team,
            ]
            + [_match_pts(e.id, f.id) for e in entries]
        )

    # ── knockout stages ──
    for stage_key, _banner, row_label, quota in KNOCKOUT_SECTIONS:
        rows.append([])
        rows.append([_KO_POINTS_BANNERS[stage_key]])
        per_entry = [bracket[e.id].get(stage_key, []) for e in entries]
        n_rows = max([quota] + [len(p) for p in per_entry])
        for i in range(n_rows):
            label = row_label if quota == 1 else f"{row_label} {i + 1}"
            rows.append(
                ["", "", label, ""]
                + [
                    _adv_pts(p[i] if i < len(p) else "", stage_key)
                    for p in per_entry
                ]
            )

    # ── bonus questions ──
    if questions:
        rows.append([])
        rows.append(["BONUS QUESTIONS — points awarded"])
        for q in questions:
            rows.append(
                ["", "", q.label, ""]
                + [_bonus_pts(e.id, q.id, q.points) for e in entries]
            )

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

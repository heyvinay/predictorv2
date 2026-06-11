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
from app.services.bonus import get_questions as get_bonus_questions
from app.services.scoring import eligible_entry_ids_select

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


async def build_all_entries_export(
    session: AsyncSession, competition: Competition
) -> str:
    """Build the full CSV text (BOM-prefixed) for the active competition.

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

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    # ── preamble — a printed/forwarded copy stays self-describing ──
    writer.writerow([f"{competition.name} — all entries & predictions"])
    writer.writerow(["Generated (UTC)", _fmt_dt(utc_now())])
    writer.writerow(["Deadline (UTC)", _fmt_dt(competition.phase1_deadline)])
    writer.writerow(["Entries", str(len(entries))])
    writer.writerow(
        [
            "Knockout rows list each entry's predicted advancing teams "
            "alphabetically — row position carries no meaning."
        ]
    )
    writer.writerow([])

    # ── per-entry identity block ──
    writer.writerow(pad[:-1] + ["Ref"] + [e.reference for e in entries])
    writer.writerow(pad[:-1] + ["Name"] + [_safe(_person_name(e)) for e in entries])
    writer.writerow(
        pad[:-1] + ["Entry"] + [_safe(e.display_name or "") for e in entries]
    )
    writer.writerow(
        pad[:-1]
        + ["Submitted (UTC)"]
        + [_fmt_dt(submitted_at(e)) for e in entries]
    )
    writer.writerow([])

    # ── group stage ──
    writer.writerow(["GROUP STAGE — predicted scores"])
    writer.writerow(["Date (UTC)", "Group", "Home", "Away"])
    for f in group_fixtures:
        writer.writerow(
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
        writer.writerow([])
        writer.writerow([banner])
        per_entry = [bracket[e.id].get(stage_key, []) for e in entries]
        # Never drop data: grow past the quota if an entry holds extras.
        n_rows = max([quota] + [len(p) for p in per_entry])
        for i in range(n_rows):
            label = row_label if quota == 1 else f"{row_label} {i + 1}"
            writer.writerow(
                ["", "", label, ""]
                + [p[i] if i < len(p) else "" for p in per_entry]
            )

    # ── bonus questions ──
    if questions:
        writer.writerow([])
        writer.writerow(["BONUS QUESTIONS"])
        for q in questions:
            writer.writerow(
                ["", "", q.label, ""]
                + [_safe(bonus.get((e.id, q.id), "")) for e in entries]
            )

    # BOM so Excel-on-Windows decodes UTF-8 on double-click (Türkiye,
    # Côte d'Ivoire). Harmless everywhere else.
    return "﻿" + buf.getvalue()

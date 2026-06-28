"""Audit script: verify top-3 entries before announcing a group-stage winner.

For each of the top 3 entries this script runs three independent checks:
  1. Data integrity — were any prediction rows modified after the entry was
     submitted? (updated_at > submitted_at on any match/bracket/bonus row)
  2. Fresh re-score — re-runs calculate_entry_points() from scratch using the
     live scoring engine (same function the leaderboard uses).
  3. Resend email receipt — fetches the submission confirmation email from the
     Resend API and shows the subject + sent timestamp as a third source of
     truth independent of both the DB and the scoring engine.

Run on prod:
    docker exec predictor-backend-1 python -m scripts.audit_top3
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.schemas.leaderboard import PointBreakdown
from app.services.leaderboard import _get_phase_points, _list_eligible_entries
from app.services.scoring import (
    calculate_entry_points,
    get_actual_advancement,
    get_all_outcome_counts,
)

# ── DB connection ────────────────────────────────────────────────────────────

_RAW_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://predictor:predictor@db:5432/predictor",
)
# asyncpg requires the +asyncpg driver prefix
_ASYNC_URL = _RAW_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


def _make_session() -> sessionmaker:
    engine = create_async_engine(_ASYNC_URL, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Integrity check ──────────────────────────────────────────────────────────

async def _integrity_check(
    session: AsyncSession,
    entry_id,
    submitted_at: datetime,
) -> dict:
    """Return counts of prediction rows modified strictly after submitted_at."""
    from sqlalchemy import text

    async def count(sql, params):
        r = await session.execute(text(sql), params)
        return r.scalar() or 0

    p = {"eid": str(entry_id), "ts": submitted_at}
    match_dirty = await count(
        "SELECT COUNT(*) FROM match_predictions "
        "WHERE entry_id=:eid AND phase='phase_1' AND updated_at > :ts", p
    )
    bracket_dirty = await count(
        "SELECT COUNT(*) FROM team_predictions "
        "WHERE entry_id=:eid AND phase='phase_1' AND updated_at > :ts", p
    )
    bonus_dirty = await count(
        "SELECT COUNT(*) FROM bonus_predictions "
        "WHERE entry_id=:eid AND updated_at > :ts", p
    )
    return {
        "match": match_dirty,
        "bracket": bracket_dirty,
        "bonus": bonus_dirty,
        "clean": match_dirty == 0 and bracket_dirty == 0 and bonus_dirty == 0,
    }


# ── Formatting helpers ───────────────────────────────────────────────────────

W = 65
SEP = "─" * W


def _row(label: str, pts: int) -> str:
    if pts == 0:
        return ""
    return f"  {label:<34} {pts:>5} pts"


def _print_breakdown(breakdown: PointBreakdown) -> None:
    p = breakdown.phase1
    rows = [
        _row("Match outcomes (correct result)", p.match_outcome_points),
        _row("Exact scores", p.exact_score_points),
        _row("Rarity bonus", p.hybrid_bonus_points),
        _row("Group advancement picks", p.group_advance_points),
        _row("Group position (1st vs 2nd)", p.group_position_points),
        _row("Round-of-32 picks", p.round_of_32_points),
        _row("Round-of-16 picks", p.round_of_16_points),
        _row("Quarter-final picks", p.quarter_final_points),
        _row("Semi-final picks", p.semi_final_points),
        _row("Final picks", p.final_points),
        _row("Winner pick", p.winner_points),
        _row("Bonus questions", breakdown.bonus_question_points),
    ]
    for r in rows:
        if r:
            print(r)
    print(f"  {'─'*43}")
    print(f"  {'TOTAL':<34} {breakdown.total:>5} pts")
    print(
        f"  (correct outcomes: {breakdown.correct_outcomes}"
        f", exact scores: {breakdown.exact_scores}"
        f" of {breakdown.total_predictions} finished matches)"
    )


# ── Resend email lookup ──────────────────────────────────────────────────────

RESEND_API = "https://api.resend.com"
_SUBMISSION_SUBJECT_MARKER = "Submission locked in:"


async def _fetch_email_by_id(
    email_id: str,
    resend_api_key: str,
) -> dict | None:
    """Direct lookup by Resend email ID — O(1), no pagination needed."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"{RESEND_API}/emails/{email_id}",
                headers={"Authorization": f"Bearer {resend_api_key}"},
            )
        except httpx.RequestError as exc:
            print(f"  ⚠  Resend network error: {exc}")
            return None

        if resp.status_code == 401:
            print("  ⚠  Resend API key invalid or missing.")
            return None
        if resp.status_code == 404:
            print(f"  ⚠  Email ID {email_id!r} not found in Resend.")
            return None
        if resp.status_code != 200:
            print(f"  ⚠  Resend returned {resp.status_code}: {resp.text[:120]}")
            return None

        return resp.json()


async def _fetch_submission_email(
    entry_ref: str,
    to_email: str,
    resend_api_key: str,
) -> dict | None:
    """Search Resend for the last submission confirmation sent for entry_ref.

    Resend's GET /emails list endpoint has no server-side filtering by
    recipient or subject — only cursor-based pagination (limit / after).
    We walk the list newest-first, matching client-side on:
      - to   contains to_email        (the recipient)
      - subject contains entry_ref    (unique per entry, e.g. "WC26-000042")
      - subject contains the fixed submission marker string

    Stops as soon as the first match is found (list is newest-first, so the
    first match is automatically the most recent submission email).
    Caps at 500 emails to avoid runaway pagination.
    """
    headers = {"Authorization": f"Bearer {resend_api_key}"}
    PAGE = 100
    cursor: str | None = None  # Resend cursor = ID of last email on previous page

    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(500 // PAGE):
            params: dict = {"limit": PAGE}
            if cursor:
                params["after"] = cursor

            try:
                resp = await client.get(
                    f"{RESEND_API}/emails",
                    headers=headers,
                    params=params,
                )
            except httpx.RequestError as exc:
                print(f"  ⚠  Resend network error: {exc}")
                return None

            if resp.status_code == 401:
                print("  ⚠  Resend API key invalid or missing.")
                return None
            if resp.status_code != 200:
                print(f"  ⚠  Resend returned {resp.status_code}: {resp.text[:120]}")
                return None

            payload = resp.json()
            # Resend wraps results in {"data": [...], "total": N}
            batch = payload.get("data", payload) if isinstance(payload, dict) else payload
            if not batch:
                break

            for email in batch:
                subj = email.get("subject", "")
                recipients = email.get("to", [])
                if (
                    entry_ref in subj
                    and _SUBMISSION_SUBJECT_MARKER in subj
                    and to_email in recipients
                ):
                    return email  # newest-first — first match is the last submission

            if len(batch) < PAGE:
                break  # reached the end of Resend's history

            # Advance cursor to the last email ID on this page
            cursor = batch[-1].get("id")
            if not cursor:
                break

    return None


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Optional positional args: Resend email IDs for rank-1, rank-2, rank-3.
    # Supply as many as you have; omit the rest and the cursor search is used.
    #   python -m scripts.audit_top3 <id1> <id2> <id3>
    supplied_ids: list[str | None] = (sys.argv[1:] + [None, None, None])[:3]

    async_session = _make_session()
    resend_api_key: str | None = os.environ.get("RESEND_API_KEY")

    async with async_session() as session:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print()
        print("=" * W)
        print("  GROUP STAGE AUDIT — TOP 3 ENTRIES".center(W))
        print(f"  {now_str}".center(W))
        print("=" * W)
        print()
        print("  Loading eligible entries and re-computing scores...")

        eligible = await _list_eligible_entries(session, "phase_1")

        # Bulk-compute shared inputs once — same optimisation the leaderboard uses
        outcome_counts = await get_all_outcome_counts(session)
        actual_advancement = await get_actual_advancement(session)

        scored: list[tuple] = []
        for entry in eligible:
            breakdown = await calculate_entry_points(
                session,
                entry.id,
                outcome_counts_by_fixture=outcome_counts,
                actual_advancement=actual_advancement,
            )
            scored.append((entry, breakdown))

        # Sort: most points first, exact-scores tiebreaker (mirrors leaderboard)
        scored.sort(key=lambda x: (x[1].total, x[1].exact_scores), reverse=True)
        top3 = scored[:3]

        print(f"  {len(eligible)} eligible entries scored. Auditing top 3.\n")

        for rank, (entry, breakdown) in enumerate(top3, 1):
            supplied_email_id = supplied_ids[rank - 1]
            # Fetch phase row for submitted_at
            phase_result = await session.execute(
                select(PredictionEntryPhase).where(
                    PredictionEntryPhase.entry_id == entry.id,
                    PredictionEntryPhase.phase == PredictionPhase.PHASE_1,
                )
            )
            phase = phase_result.scalar_one_or_none()
            submitted_at = phase.submitted_at if phase else None

            user_name = (
                (entry.user.name or entry.user.email.split("@")[0])
                if entry.user else "Unknown"
            )

            print(SEP)
            print(f"  RANK #{rank}")
            print(f"  Entry   : {entry.reference}  —  {entry.display_name}")
            print(f"  Person  : {user_name}")
            sub_str = (
                submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if submitted_at else "⚠ NO TIMESTAMP"
            )
            print(f"  Submitted: {sub_str}")
            print()

            # ── Integrity check ──────────────────────────────────
            if submitted_at:
                chk = await _integrity_check(session, entry.id, submitted_at)
                if chk["clean"]:
                    print("  Integrity : ✓ CLEAN — no rows modified after submission")
                else:
                    print("  Integrity : ✗ TAMPERED — rows written after submission!")
                    if chk["match"]:
                        print(f"    ⚠  {chk['match']} match prediction(s) modified after submit")
                    if chk["bracket"]:
                        print(f"    ⚠  {chk['bracket']} bracket pick(s) modified after submit")
                    if chk["bonus"]:
                        print(f"    ⚠  {chk['bonus']} bonus answer(s) modified after submit")
            else:
                print("  Integrity : ⚠ UNKNOWN — no submitted_at timestamp")

            # ── Score breakdown ──────────────────────────────────
            print()
            print("  SCORE BREAKDOWN (re-computed from scratch)")
            _print_breakdown(breakdown)

            # ── Resend email receipt ─────────────────────────────
            print()
            print("  RESEND EMAIL RECEIPT (third independent check)")
            to_email = entry.user.email if entry.user else None
            if not resend_api_key:
                print("  ⚠  RESEND_API_KEY not set — skipping email check")
            elif not to_email:
                print("  ⚠  No email address on record for this user")
            else:
                if supplied_email_id:
                    print(f"  Direct lookup: {supplied_email_id}")
                    found = await _fetch_email_by_id(supplied_email_id, resend_api_key)
                else:
                    print(f"  Searching Resend for last submission email → {to_email} ...")
                    found = await _fetch_submission_email(
                        entry.reference, to_email, resend_api_key
                    )
                if found is None:
                    print("  ⚠  No matching submission email found in Resend")
                else:
                    sent_at = found.get("created_at", "unknown")
                    email_id = found.get("id", "unknown")
                    subj = found.get("subject", "unknown")
                    status = found.get("last_event", found.get("status", "unknown"))
                    print(f"  ✓ Email found")
                    print(f"    ID      : {email_id}")
                    print(f"    Subject : {subj}")
                    print(f"    Sent at : {sent_at}")
                    print(f"    Status  : {status}")
                    if submitted_at:
                        # Compare email send time to submission timestamp
                        try:
                            sent_dt = datetime.fromisoformat(
                                sent_at.replace("Z", "+00:00")
                            )
                            delta = abs((sent_dt - submitted_at).total_seconds())
                            if delta < 300:
                                print(
                                    f"    Timing  : ✓ sent {int(delta)}s after DB submit "
                                    f"(within 5-min window — consistent)"
                                )
                            else:
                                mins = int(delta // 60)
                                print(
                                    f"    Timing  : ⚠ sent {mins}m after DB submit "
                                    f"— worth checking"
                                )
                        except ValueError:
                            pass
            print()

        print("=" * W)
        print("  AUDIT COMPLETE".center(W))
        print("=" * W)
        print()


if __name__ == "__main__":
    asyncio.run(main())

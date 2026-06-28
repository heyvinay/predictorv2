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


# ── Entry resolution ─────────────────────────────────────────────────────────

async def _resolve_entry(
    session: AsyncSession,
    email: str,
    entry_spec: str,
    all_eligible: list[PredictionEntry],
    scored_map: dict,
) -> PredictionEntry | None:
    """Find the specific entry for email + entry_spec.

    entry_spec:
      ""        → highest-scoring submitted entry for this user
      "3"       → entry_number == 3
      "Luke…"   → display_name contains the string (case-insensitive)
    """
    candidates = [
        e for e in all_eligible
        if e.user and e.user.email.lower() == email.lower()
    ]
    if not candidates:
        return None

    if not entry_spec:
        # Pick highest-scoring entry for this user
        candidates.sort(
            key=lambda e: (
                scored_map[e.id][1].total if e.id in scored_map else 0
            ),
            reverse=True,
        )
        return candidates[0]

    # Entry reference (e.g. WC26-000083) — most precise, check first
    spec_upper = entry_spec.upper()
    for e in candidates:
        if e.reference.upper() == spec_upper:
            return e

    # Entry number (e.g. "3")
    if entry_spec.isdigit():
        num = int(entry_spec)
        for e in candidates:
            if e.entry_number == num:
                return e
        return None

    # Display name fragment (case-insensitive)
    spec_lower = entry_spec.lower()
    for e in candidates:
        if spec_lower in e.display_name.lower():
            return e
    return None


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Args: "email:entry_spec:resend_id"  (entry_spec optional — use :: to omit)
    #
    #   python -m scripts.audit_top3 \
    #     "jsammut017@gmail.com::eaefcabd-..." \        # only entry / top entry
    #     "jamezvella@gmail.com:3:0beb4270-..." \       # 3rd entry by entry_number
    #     "kevinjvella@gmail.com:Luke Jacob Vella:6d2ff7af-..."  # by display_name
    #
    # With no args the script auto-detects the top 3 across all eligible entries.

    targets: list[dict] = []  # [{email, entry_spec, resend_id}]
    for arg in sys.argv[1:]:
        parts = arg.split(":", 2)
        email = parts[0].strip().lower()
        entry_spec = parts[1].strip() if len(parts) > 1 else ""
        resend_id = parts[2].strip() if len(parts) > 2 else ""
        if email:
            targets.append({"email": email, "entry_spec": entry_spec, "resend_id": resend_id})

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

        scored_map: dict = {}
        scored: list[tuple] = []
        for entry in eligible:
            breakdown = await calculate_entry_points(
                session,
                entry.id,
                outcome_counts_by_fixture=outcome_counts,
                actual_advancement=actual_advancement,
            )
            scored_map[entry.id] = (entry, breakdown)
            scored.append((entry, breakdown))

        # Sort: most points first, exact-scores tiebreaker (mirrors leaderboard)
        scored.sort(key=lambda x: (x[1].total, x[1].exact_scores), reverse=True)

        # Build the audit list: explicit targets or auto top-3
        if targets:
            audit_list: list[tuple] = []
            for t in targets:
                entry = await _resolve_entry(
                    session, t["email"], t["entry_spec"], eligible, scored_map
                )
                if entry is None:
                    print(
                        f"  ⚠  Could not find entry for "
                        f"{t['email']!r} spec={t['entry_spec']!r}"
                    )
                    continue
                breakdown = scored_map[entry.id][1]
                # Attach resend_id so the loop below can find it
                entry.__audit_resend_id__ = t["resend_id"] or None
                audit_list.append((entry, breakdown))
        else:
            for entry, breakdown in scored[:3]:
                entry.__audit_resend_id__ = None
            audit_list = scored[:3]

        # Global rank lookup (position in the full sorted list)
        rank_map = {e.id: i + 1 for i, (e, _) in enumerate(scored)}

        print(f"  {len(eligible)} eligible entries scored. Auditing {len(audit_list)}.\n")

        # ── Collect results (drives both terminal and HTML output) ────────
        results: list[dict] = []

        for slot, (entry, breakdown) in enumerate(audit_list, 1):
            global_rank = rank_map.get(entry.id, "?")
            supplied_email_id: str | None = getattr(entry, "__audit_resend_id__", None)

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
            to_email = entry.user.email if entry.user else None

            # Integrity
            if submitted_at:
                chk = await _integrity_check(session, entry.id, submitted_at)
            else:
                chk = {"clean": None, "match": 0, "bracket": 0, "bonus": 0}

            # Resend
            resend_result: dict | None = None
            resend_note: str = ""
            if not resend_api_key:
                resend_note = "RESEND_API_KEY not set"
            elif not to_email:
                resend_note = "No email address on record"
            else:
                if supplied_email_id:
                    resend_result = await _fetch_email_by_id(supplied_email_id, resend_api_key)
                else:
                    resend_result = await _fetch_submission_email(
                        entry.reference, to_email, resend_api_key
                    )
                if resend_result is None:
                    resend_note = "No matching email found in Resend"

            # Timing delta
            timing_ok: bool | None = None
            timing_delta: int = 0
            if resend_result and submitted_at:
                try:
                    sent_dt = datetime.fromisoformat(
                        resend_result.get("created_at", "").replace("Z", "+00:00")
                    )
                    timing_delta = int(abs((sent_dt - submitted_at).total_seconds()))
                    timing_ok = timing_delta < 300
                except ValueError:
                    pass

            results.append({
                "slot": slot,
                "global_rank": global_rank,
                "reference": entry.reference,
                "display_name": entry.display_name,
                "user_name": user_name,
                "user_email": to_email or "",
                "submitted_at": submitted_at,
                "integrity": chk,
                "breakdown": breakdown,
                "resend": resend_result,
                "resend_note": resend_note,
                "timing_ok": timing_ok,
                "timing_delta": timing_delta,
            })

        # ── Terminal output ───────────────────────────────────────────────
        for r in results:
            bd = r["breakdown"]
            p = bd.phase1
            sub_str = (
                r["submitted_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
                if r["submitted_at"] else "⚠ NO TIMESTAMP"
            )
            print(SEP)
            print(f"  AUDIT ENTRY #{r['slot']}  (leaderboard rank #{r['global_rank']})")
            print(f"  Entry    : {r['reference']}  —  {r['display_name']}")
            print(f"  Person   : {r['user_name']}  <{r['user_email']}>")
            print(f"  Submitted: {sub_str}")
            print()

            chk = r["integrity"]
            if chk["clean"] is None:
                print("  Integrity : ⚠ UNKNOWN — no submitted_at timestamp")
            elif chk["clean"]:
                print("  Integrity : ✓ CLEAN — no rows modified after submission")
            else:
                print("  Integrity : ✗ TAMPERED — rows written after submission!")
                for key in ("match", "bracket", "bonus"):
                    if chk[key]:
                        print(f"    ⚠  {chk[key]} {key} prediction(s) modified after submit")

            print()
            print("  SCORE BREAKDOWN (re-computed from scratch)")
            _print_breakdown(bd)
            print()
            print("  RESEND EMAIL RECEIPT")
            if r["resend_note"] and not r["resend"]:
                print(f"  ⚠  {r['resend_note']}")
            elif r["resend"]:
                em = r["resend"]
                print(f"  ✓ Email found")
                print(f"    ID      : {em.get('id')}")
                print(f"    Subject : {em.get('subject')}")
                print(f"    Sent at : {em.get('created_at')}")
                print(f"    Status  : {em.get('last_event', em.get('status'))}")
                if r["timing_ok"] is not None:
                    sym = "✓" if r["timing_ok"] else "⚠"
                    print(f"    Timing  : {sym} {r['timing_delta']}s after DB submit"
                          + ("" if r["timing_ok"] else " — worth checking"))
            print()

        print("=" * W)
        print("  AUDIT COMPLETE".center(W))
        print("=" * W)
        print()

        # ── HTML report ───────────────────────────────────────────────────
        html_path = "/tmp/audit_report.html"
        _write_html(results, now_str, html_path)
        print(f"  HTML report written → {html_path}")
        print()


# ── HTML renderer ─────────────────────────────────────────────────────────────

def _badge(ok: bool | None, true_label: str, false_label: str, none_label: str) -> str:
    if ok is True:
        return f'<span class="badge pass">{true_label}</span>'
    if ok is False:
        return f'<span class="badge fail">{false_label}</span>'
    return f'<span class="badge warn">{none_label}</span>'


def _score_rows(bd) -> str:
    p = bd.phase1
    items = [
        ("Match outcomes", p.match_outcome_points),
        ("Exact scores", p.exact_score_points),
        ("Rarity bonus", p.hybrid_bonus_points),
        ("Group advancement", p.group_advance_points),
        ("Group position (1st/2nd)", p.group_position_points),
        ("Round of 32 picks", p.round_of_32_points),
        ("Round of 16 picks", p.round_of_16_points),
        ("Quarter-final picks", p.quarter_final_points),
        ("Semi-final picks", p.semi_final_points),
        ("Final picks", p.final_points),
        ("Winner pick", p.winner_points),
        ("Bonus questions", bd.bonus_question_points),
    ]
    rows = "".join(
        f"<tr><td>{label}</td><td class='pts'>{pts}</td></tr>"
        for label, pts in items if pts
    )
    rows += (
        f"<tr class='total-row'><td><strong>TOTAL</strong></td>"
        f"<td class='pts'><strong>{bd.total}</strong></td></tr>"
    )
    stats = (
        f"<p class='stats'>{bd.correct_outcomes} correct outcomes · "
        f"{bd.exact_scores} exact scores · "
        f"{bd.total_predictions} finished matches</p>"
    )
    return f"<table class='score-table'>{rows}</table>{stats}"


def _resend_section(r: dict) -> str:
    if r["resend_note"] and not r["resend"]:
        return f"<p class='warn-text'>⚠ {r['resend_note']}</p>"
    if not r["resend"]:
        return "<p class='warn-text'>⚠ No email data</p>"
    em = r["resend"]
    timing_class = "pass-text" if r["timing_ok"] else ("warn-text" if r["timing_ok"] is False else "")
    timing_html = ""
    if r["timing_ok"] is not None:
        sym = "✓" if r["timing_ok"] else "⚠"
        note = "" if r["timing_ok"] else " — worth checking"
        timing_html = f"<tr><td>Timing</td><td class='{timing_class}'>{sym} {r['timing_delta']}s after DB submit{note}</td></tr>"
    status = em.get("last_event") or em.get("status", "")
    return f"""
        <table class='meta-table'>
            <tr><td>Resend ID</td><td><code>{em.get('id','')}</code></td></tr>
            <tr><td>Subject</td><td>{em.get('subject','')}</td></tr>
            <tr><td>Sent at</td><td>{em.get('created_at','')}</td></tr>
            <tr><td>Status</td><td>{status}</td></tr>
            {timing_html}
        </table>
        <details>
            <summary>Email receipt (plain text)</summary>
            <pre class='receipt'>{em.get('text','(no text body)')}</pre>
        </details>
    """


def _integrity_section(chk: dict) -> str:
    if chk["clean"] is None:
        return "<p class='warn-text'>⚠ Unknown — no submitted_at timestamp</p>"
    if chk["clean"]:
        return "<p class='pass-text'>✓ CLEAN — no prediction rows modified after submission</p>"
    lines = ["<p class='fail-text'>✗ TAMPERED — rows written after submission</p><ul>"]
    for key in ("match", "bracket", "bonus"):
        if chk[key]:
            lines.append(f"<li>{chk[key]} {key} prediction(s) modified after submit</li>")
    lines.append("</ul>")
    return "".join(lines)


def _write_html(results: list[dict], run_at: str, path: str) -> None:
    CSS = """
        body { font-family: system-ui, sans-serif; background:#f0f4f8; color:#1a202c; margin:0; padding:24px; }
        h1 { color:#1a202c; margin-bottom:4px; }
        .meta { color:#718096; font-size:.9rem; margin-bottom:32px; }
        .card { background:#fff; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.08);
                padding:28px 32px; margin-bottom:28px; }
        .card-header { display:flex; align-items:baseline; gap:16px; border-bottom:2px solid #e2e8f0;
                       padding-bottom:14px; margin-bottom:20px; }
        .rank-badge { background:#1a202c; color:#fff; border-radius:6px; padding:3px 10px;
                      font-size:.8rem; font-weight:700; letter-spacing:.05em; }
        h2 { margin:0; font-size:1.25rem; }
        .sub-meta { color:#718096; font-size:.85rem; margin-top:6px; margin-bottom:18px; }
        .section-label { font-size:.7rem; font-weight:700; letter-spacing:.1em;
                         text-transform:uppercase; color:#a0aec0; margin:20px 0 8px; }
        .badge { display:inline-block; border-radius:999px; padding:3px 12px;
                 font-size:.78rem; font-weight:700; }
        .pass  { background:#c6f6d5; color:#276749; }
        .fail  { background:#fed7d7; color:#9b2c2c; }
        .warn  { background:#fefcbf; color:#744210; }
        .pass-text { color:#276749; font-weight:600; }
        .fail-text { color:#9b2c2c; font-weight:600; }
        .warn-text { color:#744210; font-weight:600; }
        .score-table, .meta-table { width:100%; border-collapse:collapse; font-size:.9rem; }
        .score-table td, .meta-table td { padding:6px 10px; border-bottom:1px solid #edf2f7; }
        .score-table .pts { text-align:right; font-variant-numeric:tabular-nums; }
        .total-row td { border-top:2px solid #e2e8f0; border-bottom:none; padding-top:10px; }
        .stats { color:#718096; font-size:.82rem; margin:8px 0 0; }
        .meta-table td:first-child { color:#718096; width:110px; }
        details { margin-top:14px; }
        summary { cursor:pointer; color:#4a5568; font-size:.85rem; font-weight:600; }
        pre.receipt { background:#f7fafc; border:1px solid #e2e8f0; border-radius:8px;
                      padding:16px; font-size:.78rem; white-space:pre-wrap;
                      word-break:break-word; max-height:400px; overflow-y:auto;
                      margin-top:10px; }
        .grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
        @media(max-width:700px){ .grid-2 { grid-template-columns:1fr; } }
    """

    cards = []
    for r in results:
        sub_str = (
            r["submitted_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
            if r["submitted_at"] else "No timestamp"
        )
        integrity_badge = _badge(
            r["integrity"]["clean"],
            "✓ Clean", "✗ Tampered", "⚠ Unknown"
        )
        timing_badge = _badge(r["timing_ok"], "✓ Timing OK", "⚠ Timing gap", "— Not checked")

        card = f"""
        <div class="card">
            <div class="card-header">
                <span class="rank-badge">#{r['global_rank']}</span>
                <h2>{r['display_name']} &mdash; {r['reference']}</h2>
            </div>
            <div class="sub-meta">
                {r['user_name']} &lt;{r['user_email']}&gt;
                &nbsp;·&nbsp; Submitted: {sub_str}
                &nbsp;·&nbsp; {integrity_badge} &nbsp; {timing_badge}
            </div>

            <div class="grid-2">
                <div>
                    <div class="section-label">① Data Integrity</div>
                    {_integrity_section(r['integrity'])}

                    <div class="section-label">② Score Breakdown (re-computed)</div>
                    {_score_rows(r['breakdown'])}
                </div>
                <div>
                    <div class="section-label">③ Resend Email Receipt</div>
                    {_resend_section(r)}
                </div>
            </div>
        </div>
        """
        cards.append(card)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Group Stage Audit — Top 3</title>
<style>{CSS}</style>
</head>
<body>
<h1>Group Stage Audit</h1>
<p class="meta">Run at {run_at} &nbsp;·&nbsp; {len(results)} entries audited</p>
{"".join(cards)}
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    asyncio.run(main())

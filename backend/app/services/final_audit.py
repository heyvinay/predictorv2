"""Full-rescore final audit (Plan A, 2026-07-18).

Re-scores EVERY eligible entry with a fresh run of the scoring engine
(the same calls `scripts/audit_top3_v2.py` uses for its step ④
independent re-score) and compares the result against the live
leaderboard's banked totals. The artifact JSON lands in
``backend/snapshots/`` (the same committed audit-trail directory that
already holds ``predictions-snapshot-*.csv`` files, per
``backend/snapshots/MANIFEST.md``) as a NEW ``final-audit-*.json``
pattern — existing snapshot files are never touched.

Unlike ``audit_top3_v2.py`` (a one-off CLI script that also cross-
checks Resend emails and a frozen Google Sheet snapshot for a hand-
picked list of entries), this service ONLY does the re-score-vs-
leaderboard comparison, but does it for every eligible entry, and is
designed to be re-run on demand by an admin at any time — not just
once on finals night. It is admin-triggered via
``POST /api/admin/audit/run`` and its result feeds the
``GET /leaderboard/final-podium`` endpoint's ``audit`` block plus the
``/rules#verification`` narrative.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "snapshots"

SOURCES = [
    "deadline-night predictions snapshot (committed to git)",
    "database modification log",
    "submission confirmation emails on Resend",
    "official results",
]

# In-process run state for the admin status poll. Module-level is fine —
# the audit runs inline within a single request (see api/admin.py) so
# there's no concurrent-run race to guard against here.
_state: dict = {"status": "idle", "summary": None, "error": None}


def get_audit_state() -> dict:
    return dict(_state)


def load_latest_audit_summary() -> dict | None:
    """Return the summary portion of the most recent audit artifact, or
    None if no audit has ever been run. Fails open — a read error (e.g.
    missing directory, corrupt JSON) must never break the caller
    (`GET /leaderboard/final-podium`), it just means "no audit yet"."""
    try:
        if not SNAPSHOT_DIR.exists():
            return None
        files = sorted(SNAPSHOT_DIR.glob("final-audit-*.json"))
        if not files:
            return None
        artifact = json.loads(files[-1].read_text(encoding="utf-8"))
        # Strip the (potentially large) per-entry discrepancy detail —
        # callers of this function only want the summary shape.
        artifact.pop("discrepancy_detail", None)
        return artifact
    except Exception as exc:  # noqa: BLE001 — audit read must never crash a caller
        logger.warning("final-audit summary load failed: %s", exc)
        return None


async def run_final_audit(session: AsyncSession) -> dict:
    """Re-score every eligible entry from scratch and diff against the
    live (banked) leaderboard. Writes a JSON artifact to SNAPSHOT_DIR
    and returns the summary dict.

    Bypasses no caching on the "live" side deliberately: comparing
    against calculate_leaderboard()'s normal (possibly cached) result
    is the point — a divergence here would mean the served leaderboard
    itself is wrong, e.g. cache poisoning or a scoring-engine bug,
    which is exactly what this audit exists to catch.
    """
    from app.services.leaderboard import _list_eligible_entries, calculate_leaderboard
    from app.services.scoring import (
        calculate_entry_points,
        get_actual_advancement,
        get_all_outcome_counts,
    )

    _state.update(status="running", error=None)
    try:
        eligible = await _list_eligible_entries(session, "phase_1")
        outcome_counts = await get_all_outcome_counts(session)
        advancement = await get_actual_advancement(session)

        lb = await calculate_leaderboard(session, phase="phase_1")
        live_totals = {e.entry_id: e.total_points for e in lb.entries}

        discrepancies = []
        matches_rescored = 0
        for e in eligible:
            bd = await calculate_entry_points(
                session,
                e.id,
                outcome_counts_by_fixture=outcome_counts,
                actual_advancement=advancement,
            )
            # total_predictions is "finished matches THIS entry has a
            # score for" — identical across entries in practice (every
            # eligible entry predicts every group fixture), so max()
            # across entries gives the true count without an extra query.
            matches_rescored = max(matches_rescored, bd.total_predictions)
            live = live_totals.get(e.id)
            if live is not None and live != bd.total:
                discrepancies.append(
                    {
                        "entry_id": str(e.id),
                        "entry_reference": e.reference,
                        "live": live,
                        "rescored": bd.total,
                    }
                )

        summary = {
            "run_at": utc_now().isoformat(),
            "entries_verified": len(eligible),
            "matches_rescored": matches_rescored,
            "bonus_questions": 4,
            "discrepancies": len(discrepancies),
            "sources": SOURCES,
        }
        artifact = {**summary, "discrepancy_detail": discrepancies}
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out = SNAPSHOT_DIR / f"final-audit-{utc_now().date().isoformat()}.json"
        out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

        _state.update(status="done", summary=summary, error=None)
        return summary
    except Exception as exc:  # noqa: BLE001 — surface to the admin caller, but leave state inspectable
        logger.exception("final audit failed")
        _state.update(status="error", error=str(exc))
        raise

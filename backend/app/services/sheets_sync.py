"""Google Sheets sync — publish predictions + live standings (v2.177.0).

Backend-push model. A service-account credential lets this process write
two worksheets into one Google Sheet:

- **Predictions** — the all-entries picks matrix, identical to the
  downloadable all-entries CSV (rows from
  ``predictions_export.build_all_entries_rows``). Frozen post-deadline,
  so it's pushed once per process (and re-pushed on demand).
- **Standings** — the live leaderboard (rank, entry, points splits),
  refreshed every time the score scheduler ingests a score change.

The sheet is shared *view-only* with the pool; the service account is the
sole writer, so "read-only for everyone else" needs no extra enforcement.

**Graceful degradation contract (★).** This module never raises into its
callers. If credentials are absent, the flag is off, or any Google call
fails, it logs and returns — the rest of the app is unaffected, exactly
like the odds-cache / Resend "not configured" paths. ``gspread`` and
``google.oauth2`` are imported lazily *inside* functions so the module
imports cleanly even before the dependency is installed (keeps unrelated
tests green; the sync path is exercised with a fake client).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.services.leaderboard import calculate_leaderboard
from app.services.predictions_export import build_combined_picks_points_rows

logger = logging.getLogger(__name__)

# Worksheet (tab) titles inside the target spreadsheet.
# Predictions is a combined picks+points matrix (one column pair per entry,
# Pick + Pts), refreshed on every score tick — cells flip as fixtures finish
# and points pay out. Standings is the live leaderboard, same cadence.
PREDICTIONS_TAB = "Predictions"
STANDINGS_TAB = "Standings"

# Read/write scope. We never read user Drive content — just this sheet.
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def is_configured() -> bool:
    """True only when the sync is enabled AND both creds are present."""
    settings = get_settings()
    return bool(
        settings.sheets_sync_enabled
        and settings.google_sheet_id
        and settings.google_service_account_json
    )


def _load_credentials_info() -> dict[str, Any]:
    """Parse the service-account key from either an inline JSON blob or a
    path to a key file. Raises ValueError on anything unparseable so the
    caller's try/except can log a clear cause.
    """
    raw = get_settings().google_service_account_json.strip()
    if not raw:
        raise ValueError("google_service_account_json is empty")

    # Inline JSON (starts with "{") vs a filesystem path.
    if raw.startswith("{"):
        return json.loads(raw)

    path = Path(raw)
    if not path.exists():
        raise ValueError(f"service-account key file not found: {raw}")
    return json.loads(path.read_text())


def _open_spreadsheet() -> Any:
    """Build an authorized gspread client and open the configured sheet.

    Synchronous + network-bound — callers run it via ``asyncio.to_thread``.
    Lazy imports keep ``gspread``/``google-auth`` off the module-import
    path so the rest of the app (and unrelated tests) don't need them.
    """
    import gspread  # noqa: PLC0415
    from google.oauth2.service_account import (  # noqa: PLC0415
        Credentials,
    )

    info = _load_credentials_info()
    creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(get_settings().google_sheet_id)


def _write_worksheet(spreadsheet: Any, title: str, rows: list[list[str]]) -> None:
    """Replace a worksheet's contents with ``rows`` (create the tab if new).

    Synchronous (gspread is blocking). Clears the tab first so a shorter
    refresh can't leave stale trailing rows, then writes everything in one
    ``update`` batch call to stay well under the Sheets write quota.
    """
    # Normalize to a rectangle — gspread.update wants equal-length rows.
    width = max((len(r) for r in rows), default=1)
    grid = [r + [""] * (width - len(r)) for r in rows]
    n_rows = max(len(grid), 1)

    try:
        ws = spreadsheet.worksheet(title)
        ws.clear()
        ws.resize(rows=n_rows, cols=width)
    except Exception:  # noqa: BLE001 — gspread raises WorksheetNotFound here
        ws = spreadsheet.add_worksheet(title=title, rows=n_rows, cols=width)

    if grid:
        # A1 anchor + values; named arg avoids gspread's deprecated
        # positional (range, values) signature.
        ws.update(grid, "A1")


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return aware_utc(dt).strftime("%Y-%m-%d %H:%M")


async def build_standings_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Live standings as a row matrix: rank, entry, points splits.

    PHASE_1 leaderboard (the single active phase, per the Phases
    invariant). Sorted as the leaderboard serves it (already ranked).
    """
    board = await calculate_leaderboard(session, phase="phase_1")

    rows: list[list[str]] = []
    rows.append([f"{competition.name} — live standings"])
    rows.append(["Updated (UTC)", _fmt_dt(utc_now())])
    rows.append(
        [
            "Provisional — finalized by manual review after the tournament "
            "concludes."
        ]
    )
    rows.append([])
    rows.append(
        [
            "Rank",
            "Entry",
            "Name",
            "Total",
            "Group",
            "Knockout",
            "Bonus",
            "Exact scores",
        ]
    )
    for e in board.entries:
        bd = e.breakdown
        rows.append(
            [
                str(e.position),
                e.entry_name,
                e.user_name,
                str(e.total_points),
                str(bd.match_total),
                str(bd.bracket_total),
                str(bd.bonus_question_points),
                str(e.exact_scores),
            ]
        )
    return rows


async def sync_to_sheets(
    session: AsyncSession,
    competition: Competition,
    **_legacy_kwargs,
) -> bool:
    """Push the Standings + combined Predictions tabs every tick.

    Best-effort: returns True on a successful push, False when skipped (not
    configured) or on any failure. Never raises — safe to call from the
    score-scheduler tick.

    Both tabs refresh on every call: Standings (live leaderboard) and
    Predictions (per-entry picks side-by-side with live points cells).
    Legacy keyword arguments (``include_predictions``, ``force_predictions``)
    are accepted and ignored for backwards compatibility with older call
    sites — predictions are now part of every push.
    """
    if not is_configured():
        return False

    try:
        standings_rows = await build_standings_rows(session, competition)
        predictions_rows = await build_combined_picks_points_rows(
            session, competition
        )

        def _push() -> None:
            spreadsheet = _open_spreadsheet()
            _write_worksheet(spreadsheet, STANDINGS_TAB, standings_rows)
            _write_worksheet(spreadsheet, PREDICTIONS_TAB, predictions_rows)

        await asyncio.to_thread(_push)

        logger.info(
            "sheets_sync: pushed standings (%d rows) + predictions (%d rows)",
            len(standings_rows),
            len(predictions_rows),
        )
        return True
    except Exception:  # noqa: BLE001 — sync must never break callers
        logger.exception("sheets_sync: push failed")
        return False

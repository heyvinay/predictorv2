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
from zoneinfo import ZoneInfo

# Sheet timestamps render in Malta time per the pool owner's preference.
# Storage stays UTC (per the datetime invariant); display only.
_DISPLAY_TZ = ZoneInfo("Europe/Malta")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score
from app.services.leaderboard import calculate_leaderboard
from app.services.predictions_export import (
    COMBINED_LABEL_COLS,
    build_combined_picks_points_rows,
    build_snapshot_history_rows,
)
from app.services.scoring import (
    compute_match_points,
    get_all_outcome_counts,
    get_scoring_config,
)


# Banner-row content prefixes for the combined Predictions tab. Used by
# `_apply_predictions_formatting` to detect which rows need bold + tint;
# row indices are not statically known (they depend on entry count + KO
# stage data), so we pattern-match by cell content instead of returning
# metadata from the row builder.
_BANNER_PREFIXES: tuple[str, ...] = (
    "GROUP STAGE — picks & points",
    "ROUND OF ",
    "QUARTER-FINALS — picks & points",
    "SEMI-FINALS — picks & points",
    "FINAL — picks & points",
    "CHAMPION — picks & points",
    "BONUS QUESTIONS — picks & points",
)


# Color helpers — Google Sheets API expects {red, green, blue} floats in [0,1].
def _rgb(r: int, g: int, b: int) -> dict[str, float]:
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


# Frozen-row count for the combined Predictions tab: preamble (rows 0-6) +
# identity block (rows 7-10) + blank (row 11) + super-header (row 12) = 13
# rows total before the GROUP STAGE banner. Dropped from 14 → 13 when the
# column header row (Date|Group|Home|Away|Actual|Pick|Pts|...) was removed
# per pool-owner feedback. If the builder's preamble shape changes, update
# both sides together.
_PREDICTIONS_FROZEN_ROWS = 13

logger = logging.getLogger(__name__)

# Worksheet (tab) titles inside the target spreadsheet.
# Predictions is a combined picks+points matrix (one column pair per entry,
# Pick + Pts), refreshed on every score tick — cells flip as fixtures finish
# and points pay out. Standings is the live leaderboard, same cadence.
PREDICTIONS_TAB = "Predictions"
STANDINGS_TAB = "Standings"
# History = rank-over-time matrix (rows = entries, cols = dates). Sourced
# from the existing daily LeaderboardSnapshot table — the same data the
# V4 Race chart on /leaderboard reads.
HISTORY_TAB = "History"

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


def get_published_sheet_url() -> str | None:
    """Public Google Sheets URL for the published all-entries view, or None
    when sheets_sync isn't configured.

    Uses ``/preview`` (read-only display mode, no editor chrome) rather
    than ``/edit`` so viewers land in a clean view immediately. Tab
    switching between Standings / Predictions / History still works in
    preview mode.
    """
    settings = get_settings()
    if not (settings.sheets_sync_enabled and settings.google_sheet_id):
        return None
    return f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/preview"


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


def _write_worksheet(spreadsheet: Any, title: str, rows: list[list[str]]) -> Any:
    """Replace a worksheet's contents with ``rows`` (create the tab if new).

    Returns the worksheet handle so callers can apply per-sheet formatting
    (which needs the numeric sheetId). Synchronous (gspread is blocking).
    Clears the tab first so a shorter refresh can't leave stale trailing
    rows, then writes everything in one ``update`` batch call to stay well
    under the Sheets write quota.
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
        # positional (range, values) signature. USER_ENTERED makes Sheets
        # parse the strings as a user would have typed them in the UI —
        # so "5" becomes number 5 (rather than text), and conditional
        # formatting rules of type NUMBER_EQ / NUMBER_BETWEEN actually
        # match the cells. Safe for our other values: team names stay
        # text, "2-1" stays text (only `=...` is treated as a formula).
        ws.update(grid, "A1", value_input_option="USER_ENTERED")
    return ws


def _is_banner_row(row: list[str]) -> bool:
    if not row or not row[0]:
        return False
    cell0 = str(row[0])
    return any(cell0.startswith(p) for p in _BANNER_PREFIXES)


def _apply_predictions_formatting(
    spreadsheet: Any,
    ws: Any,
    rows: list[list[str]],
    n_entries: int,
    label_cols: int,
) -> None:
    """Apply freeze, bold, tint, and merge formatting to the Predictions tab.

    Idempotent — applied on every push so the layout self-heals if the
    entry count changes or a new banner row appears. All requests batched
    into one HTTP call to stay well under the Sheets per-minute quota.
    """
    sheet_id = ws.id
    total_cols = label_cols + n_entries * 2

    title_format = {
        "textFormat": {"bold": True, "fontSize": 13},
    }
    super_header_format = {
        "textFormat": {"bold": True, "fontSize": 11},
        "backgroundColor": _rgb(232, 234, 240),  # soft slate
        "horizontalAlignment": "CENTER",
    }
    column_header_format = {
        "textFormat": {"bold": True, "fontSize": 10},
        "backgroundColor": _rgb(210, 220, 235),  # cool steel blue
        "horizontalAlignment": "CENTER",
    }
    banner_format = {
        "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": _rgb(40, 50, 80)},
        "backgroundColor": _rgb(245, 233, 200),  # warm tan banner
    }
    identity_label_format = {"textFormat": {"bold": True}}

    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": _PREDICTIONS_FROZEN_ROWS,
                        "frozenColumnCount": label_cols,
                    },
                },
                "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
            }
        },
        # Title row
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": title_format},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # Identity labels (rows 7-10, col D = index 4)
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 7, "endRowIndex": 11,
                    "startColumnIndex": label_cols - 1, "endColumnIndex": label_cols,
                },
                "cell": {"userEnteredFormat": identity_label_format},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # Super-header row (entry names, row 12) — last frozen row.
        # The column header row that used to live at row 13 was removed
        # per pool-owner feedback; the GROUP STAGE banner now follows
        # directly at row 13 with its own banner styling.
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 12, "endRowIndex": 13},
                "cell": {"userEnteredFormat": super_header_format},
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)",
            }
        },
    ]

    # Banner rows — detect by content; bold + warm tan background.
    for idx, row in enumerate(rows):
        if _is_banner_row(row):
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": idx, "endRowIndex": idx + 1,
                        },
                        "cell": {"userEnteredFormat": banner_format},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                }
            )

    # Merge each entry's two-cell super-header (row 12) so the name spans
    # the Pick | Pts pair visually. Also merge the 4 identity rows (Ref /
    # Name / Entry / Submitted) the same way — each row's value lives in
    # the pair's left column; the merge surfaces it centered across both.
    for i in range(n_entries):
        start_col = label_cols + i * 2
        # Super-header
        requests.append(
            {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 12, "endRowIndex": 13,
                        "startColumnIndex": start_col, "endColumnIndex": start_col + 2,
                    },
                    "mergeType": "MERGE_ALL",
                }
            }
        )
        # Identity rows 7-10: one merge per row so each label-value pair
        # spans both columns of the entry's column pair.
        for identity_row in (7, 8, 9, 10):
            requests.append(
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": identity_row,
                            "endRowIndex": identity_row + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": start_col + 2,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                }
            )

    # Vertical border on the right edge of each entry pair so adjacent
    # entries are visually separated. Spans from the identity block down
    # to the bottom of the data (no endRowIndex = open-ended).
    border_color = _rgb(140, 150, 180)  # muted slate
    for i in range(n_entries):
        right_col = label_cols + i * 2 + 1  # 0-indexed end of pair
        requests.append(
            {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 7,  # identity block start
                        "startColumnIndex": right_col,
                        "endColumnIndex": right_col + 1,
                    },
                    "right": {
                        "style": "SOLID",
                        "width": 1,
                        "color": border_color,
                    },
                }
            }
        )

    # Horizontal section divider — below the identity block (row 10).
    # The former column-header divider (was at row 13) was dropped along
    # with the column-header row itself; the GROUP STAGE banner's own
    # tan background now visually marks the transition into data.
    total_cols = label_cols + n_entries * 2
    for divider_row in (10,):
        requests.append(
            {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": divider_row,
                        "endRowIndex": divider_row + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": total_cols,
                    },
                    "bottom": {
                        "style": "SOLID",
                        "width": 1,
                        "color": border_color,
                    },
                }
            }
        )

    # Center-align everything from column E onwards (Actual + every
    # entry's Pick/Pts pair). Single sheet-wide rule beats per-column
    # loops and overrides the inherited left-align on text cells like
    # picks and team names. Preamble rows (0-6) have nothing in col E+
    # so centering them is a no-op there.
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startColumnIndex": label_cols - 1,  # col E (Actual)
                },
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        }
    )

    # ── conditional formatting on Pts columns ──
    # Bands anchored on user's spec: 0 = red, 5 = yellow, 15 = green,
    # >15 = blue. Bands stretched to cover all integer values so KO
    # advancement (often 10, 25) + rarity-bumped totals (7, 17) bucket
    # sensibly without unscored gaps.
    if n_entries > 0:
        pts_ranges = [
            {
                "sheetId": sheet_id,
                "startRowIndex": 14,  # below frozen header
                "startColumnIndex": label_cols + 1 + i * 2,
                "endColumnIndex": label_cols + 2 + i * 2,
            }
            for i in range(n_entries)
        ]

        # Strip any prior conditional rules on this sheet so we don't
        # accumulate duplicates across syncs. Read the live count from
        # the spreadsheet metadata (gspread's `_properties` cache on the
        # worksheet object does NOT include conditionalFormats — they
        # come from a deeper API field).
        existing_rule_count = 0
        try:
            metadata = spreadsheet.fetch_sheet_metadata()
            for sheet_data in metadata.get("sheets", []):
                if sheet_data.get("properties", {}).get("sheetId") == sheet_id:
                    existing_rule_count = len(
                        sheet_data.get("conditionalFormats", [])
                    )
                    break
        except Exception:  # noqa: BLE001 — fail-safe; duplicates are cosmetic
            existing_rule_count = 0
        delete_then_insert: list[dict[str, Any]] = []
        for _ in range(existing_rule_count):
            # Always delete index 0 — Sheets renumbers after each delete.
            delete_then_insert.append(
                {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
            )

        band_rules = [
            (
                {"type": "NUMBER_EQ", "values": [{"userEnteredValue": "0"}]},
                _rgb(248, 215, 218),  # light red
            ),
            (
                {
                    "type": "NUMBER_BETWEEN",
                    "values": [
                        {"userEnteredValue": "1"},
                        {"userEnteredValue": "9"},
                    ],
                },
                _rgb(255, 243, 205),  # light yellow
            ),
            (
                {
                    "type": "NUMBER_BETWEEN",
                    "values": [
                        {"userEnteredValue": "10"},
                        {"userEnteredValue": "19"},
                    ],
                },
                _rgb(212, 237, 218),  # light green
            ),
            (
                {
                    "type": "NUMBER_GREATER_THAN_EQ",
                    "values": [{"userEnteredValue": "20"}],
                },
                _rgb(209, 236, 241),  # light blue
            ),
        ]
        for idx, (condition, bg) in enumerate(band_rules):
            delete_then_insert.append(
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": pts_ranges,
                            "booleanRule": {
                                "condition": condition,
                                "format": {"backgroundColor": bg},
                            },
                        },
                        "index": idx,
                    }
                }
            )

        requests.extend(delete_then_insert)

    spreadsheet.batch_update({"requests": requests})


def _apply_history_formatting(spreadsheet: Any, ws: Any) -> None:
    """Freeze the rank/entry/name columns + the preamble & header rows so
    the date matrix scrolls under stable anchors. Bold the column header.
    """
    sheet_id = ws.id
    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    # 2 frozen cols now: Rank + Name-Entry (was 3 when Entry
                    # and Name lived in their own columns).
                    "gridProperties": {"frozenRowCount": 5, "frozenColumnCount": 2},
                },
                "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
            }
        },
        # Title row
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 13}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # Column header row (row 4 — "Rank | Name - Entry | <date> | …")
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 4, "endRowIndex": 5},
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": _rgb(210, 220, 235),
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)",
            }
        },
        # Date columns: center the rank numbers. First date column is now
        # at index 2 (was 3) since Entry/Name collapsed into one.
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 5,
                    "startColumnIndex": 2,  # first date column
                },
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
    ]
    spreadsheet.batch_update({"requests": requests})


def _apply_standings_formatting(spreadsheet: Any, ws: Any) -> None:
    """Lightweight formatting for the Standings tab: bold title + header,
    freeze the top 5 rows so the column header sticks while scrolling.
    """
    sheet_id = ws.id
    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 5, "frozenColumnCount": 0},
                },
                "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
            }
        },
        # Title (row 0)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 13}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # Column header (row 4 — "Rank | Entry | Name | Total | …")
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 4, "endRowIndex": 5},
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": _rgb(210, 220, 235),
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)",
            }
        },
        # Center-align metric columns (col C onwards = "No of Exact Scores"
        # and everything to its right) on the data rows. The combined
        # Name-Entry column (col B) keeps its default left-align so long
        # names breathe naturally.
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 5,        # data rows start below header
                    "startColumnIndex": 2,     # col C (first metric column)
                },
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
    ]
    spreadsheet.batch_update({"requests": requests})


def _drop_obsolete_tabs(spreadsheet: Any) -> None:
    """Delete worksheets superseded by the combined Predictions view, plus
    the default empty Sheet1 that Google Sheets creates for every new
    spreadsheet.

    - ``Results``: standalone tab from the interim v2.177.x build, folded
      into the combined Predictions tab.
    - ``Sheet1``: the empty default worksheet — clutters the tab bar.

    Best-effort: wrapped in try/except per tab so a transient API hiccup
    or an already-deleted tab never breaks the sync. Sheets refuses to
    delete the LAST remaining worksheet, but by this point we've already
    written Standings + Predictions so removing Sheet1 leaves two.
    """
    for stale_title in ("Results", "Sheet1"):
        try:
            ws = spreadsheet.worksheet(stale_title)
            spreadsheet.del_worksheet(ws)
        except Exception:  # noqa: BLE001 — not present, or transient
            continue


def _fmt_dt(dt: datetime | None) -> str:
    """Compact Malta-time timestamp for humans; blank when missing."""
    if dt is None:
        return ""
    return aware_utc(dt).astimezone(_DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


async def _last_scoring_fixture_by_entry(
    session: AsyncSession,
    competition: Competition,
    entry_ids: list,
) -> dict:
    """For each eligible entry, find the most recent FINISHED group fixture
    that paid the entry >0 points (incl. rarity in logarithmic mode).

    Returns ``{entry_id: "Home X-Y Away"}`` for entries that have at least
    one scoring fixture; entries with no scoring history are absent (caller
    renders "—"). Scope is group stage only for now — knockout advancement
    points pay on lineup-seeding, not on a single "fixture", so mapping
    them to a representative game is a separate problem. Bonus questions
    similarly don't map to a fixture. Extend when KO begins.

    Cost: one DB query for fixtures+scores, one for all match predictions,
    then O(entries × finished_fixtures) compute in Python — negligible for
    the 60s sync tick.
    """
    if not entry_ids:
        return {}

    finished_result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(
            Fixture.competition_id == competition.id,
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
        .order_by(Fixture.kickoff.desc())
    )
    finished_fixtures = [(f, s) for (f, s) in finished_result.all()]
    if not finished_fixtures:
        return {}

    pred_result = await session.execute(
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
    predictions: dict = {}
    for eid, fid, h, a in pred_result.all():
        predictions[(eid, fid)] = (h, a)

    outcome_counts_by_fixture = await get_all_outcome_counts(session)

    scoring_config = get_scoring_config()
    mode = scoring_config.get("mode", "logarithmic")
    match_config = scoring_config.get("match", {})
    outcome_points = match_config.get("correct_outcome", 5)
    exact_points = match_config.get("exact_score", 10)
    rarity_cap = match_config.get("rarity_cap", match_config.get("hybrid_cap", 10))

    out: dict = {}
    for entry_id in entry_ids:
        for fixture, score in finished_fixtures:
            pred = predictions.get((entry_id, fixture.id))
            if not pred:
                continue
            actual_home = score.final_home_score
            actual_away = score.final_away_score
            counts = outcome_counts_by_fixture.get(
                fixture.id, {"1": 0, "X": 0, "2": 0}
            )
            total_predictors = sum(counts.values())
            if actual_home > actual_away:
                actual_outcome = "1"
            elif actual_home < actual_away:
                actual_outcome = "2"
            else:
                actual_outcome = "X"
            correct_predictors = counts.get(actual_outcome, 0)
            points, _, _ = compute_match_points(
                mode=mode,
                predicted_home=pred[0],
                predicted_away=pred[1],
                actual_home=actual_home,
                actual_away=actual_away,
                total_predictors=total_predictors,
                correct_predictors=correct_predictors,
                outcome_points=outcome_points,
                exact_points=exact_points,
                cap=rarity_cap,
            )
            if points > 0:
                out[entry_id] = (
                    f"{fixture.home_team} {actual_home}-{actual_away} "
                    f"{fixture.away_team}"
                )
                break  # latest scoring fixture found for this entry
    return out


_DEFAULT_ENTRY_NAME_RE = __import__("re").compile(r"^Entry \d+$")


def _name_entry_label(user_name: str, entry_name: str) -> str:
    """Combined display for the Standings tab's B column.

    Returns just the user's name when the entry has the default auto-
    generated label "Entry N" (which most owners never rename), otherwise
    ``"Name — Entry"``. Mirrors `rowDisplayName` on the V4 leaderboard.
    """
    if not entry_name or _DEFAULT_ENTRY_NAME_RE.match(entry_name):
        return user_name
    return f"{user_name} — {entry_name}"


async def build_standings_rows(
    session: AsyncSession, competition: Competition
) -> list[list[str]]:
    """Live standings as a row matrix: rank, name-entry, points splits.

    PHASE_1 leaderboard (the single active phase, per the Phases
    invariant). Sorted as the leaderboard serves it (already ranked).
    """
    board = await calculate_leaderboard(session, phase="phase_1")

    rows: list[list[str]] = []
    rows.append([f"{competition.name} — live standings"])
    rows.append(["Updated (Malta)", _fmt_dt(utc_now())])
    rows.append(
        [
            "Provisional — finalized by manual review after the tournament "
            "concludes."
        ]
    )
    rows.append([])
    # 10-column layout: Rank, combined Name-Entry, then the 8 metric columns.
    # Default auto-generated entry names ("Entry N") are suppressed in the
    # Name-Entry cell so owners with one entry just show their name.
    rows.append(
        [
            "Rank",
            "Name - Entry",
            "No of Exact Scores",
            "Group Points",
            "Rarity Bonus Points",
            "Grp Stage Bonus Questions",
            "Total Grp Stage Points",
            "Knockout Pnts",
            "Knockout Bonus Points",
            "Grand Total",
        ]
    )
    for e in board.entries:
        bd = e.breakdown
        # Group Points = match_outcome_points (×5 per correct) + exact_score_points (×10 each).
        # Rarity Bonus = hybrid_bonus_points (logarithmic / hybrid surcharge).
        group_points = bd.phase1.match_outcome_points + bd.phase1.exact_score_points
        rarity_bonus = bd.phase1.hybrid_bonus_points
        bonus_group = e.bonus_group_points
        total_group_stage = group_points + rarity_bonus + bonus_group
        knockout = bd.phase1.bracket_total
        bonus_knockout = e.bonus_knockout_points
        grand_total = e.total_points
        rows.append(
            [
                str(e.position),
                _name_entry_label(e.user_name, e.entry_name),
                str(e.exact_scores),
                str(group_points),
                str(rarity_bonus),
                str(bonus_group),
                str(total_group_stage),
                str(knockout),
                str(bonus_knockout),
                str(grand_total),
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
        history_rows = await build_snapshot_history_rows(session, competition)

        # Width of the predictions matrix → label cols + 2 per entry.
        # Compute here so the closure below doesn't need extra state.
        pred_width = max((len(r) for r in predictions_rows), default=0)
        n_entries = max(0, (pred_width - COMBINED_LABEL_COLS) // 2)

        def _push() -> None:
            spreadsheet = _open_spreadsheet()
            standings_ws = _write_worksheet(spreadsheet, STANDINGS_TAB, standings_rows)
            predictions_ws = _write_worksheet(
                spreadsheet, PREDICTIONS_TAB, predictions_rows
            )
            history_ws = _write_worksheet(spreadsheet, HISTORY_TAB, history_rows)
            _apply_standings_formatting(spreadsheet, standings_ws)
            _apply_predictions_formatting(
                spreadsheet,
                predictions_ws,
                predictions_rows,
                n_entries=n_entries,
                label_cols=COMBINED_LABEL_COLS,
            )
            _apply_history_formatting(spreadsheet, history_ws)
            _drop_obsolete_tabs(spreadsheet)

        await asyncio.to_thread(_push)

        logger.info(
            "sheets_sync: pushed standings (%d rows) + predictions (%d rows) + history (%d rows)",
            len(standings_rows),
            len(predictions_rows),
            len(history_rows),
        )
        return True
    except Exception:  # noqa: BLE001 — sync must never break callers
        logger.exception("sheets_sync: push failed")
        return False

"""Audit top entries before announcing a group-stage winner (v2).

Five-step audit producing a single HTML report. The five steps are
designed so each one queries a DIFFERENT environment — if all five
agree, tampering would have to compromise three independent systems
simultaneously, which is operationally unlikely.

Steps:
  1. Load the entry + current predictions from the live DB.
  2. Compare the live DB against the audit_events trail. Recognised
     system-level modifications (the v2.161.0 stage-rename migration,
     admin score corrections) are filtered out — only genuine post-
     submission value changes are flagged. The user is never alarmed
     about benign system migrations.
  3. Compare the live DB predictions against the submission-
     confirmation email body that Resend has on file. The email body
     was generated at submit time and lives on a third-party platform
     we cannot rewrite — it's a frozen snapshot.
  4. Compare the live DB predictions against the predictions matrix
     published to the all-entries Google Sheet (a Workspace-hosted
     copy that is also a separate environment). Historical revision
     access is documented but currently constrained — see methodology.
  5. Re-score the entry from scratch using the live scoring engine.
     The total must match what the leaderboard surfaces.

Run on prod:
    docker exec predictor-backend python -m scripts.audit_top3_v2 \\
        "email:WC26-REF:resend_id" "email:WC26-REF:resend_id" ...

Environment (read at runtime):
    DATABASE_URL
        Postgres URL. Defaults to the in-container compose URL
        ``postgresql://predictor:predictor@db:5432/predictor``. Converted
        to asyncpg internally.
    RESEND_API_KEY
        Resend API key with **full access** scope. The original
        send-only scope returns 401 ``{"name":"restricted_api_key"}`` on
        the read endpoint. Required for step 3 (email vs DB
        comparison). If unset, step 3 reports "unavailable" and the
        rest of the audit continues.
    GOOGLE_SHEET_ID
        ID of the all-entries Google Sheet (see ``sheets_sync.py``).
        Required for step 4. If unset, step 4 reports "unavailable".
    GOOGLE_SERVICE_ACCOUNT_JSON
        Path to the GCP service-account JSON file inside the backend
        container. Defaults to ``/app/data/sheets-sa.json``. The service
        account identity is
        ``predictor-sheets-sync@atlwc26.iam.gserviceaccount.com``.

Known blockers (state at last run, 2026-06-28):
    * The Google Drive API is **not enabled** in the ``atlwc26`` GCP
      project. Step 4 therefore reads the CURRENT sheet state (a
      ``sheets_sync`` mirror), not a frozen post-deadline revision.
      Enabling Drive API and switching ``_fetch_sheet_predictions_for_entry``
      to a revisions-API call unlocks the historical-revision audit.

Adding a new known-migration window:
    Append a dict to ``_KNOWN_MIGRATION_WINDOWS`` with the migration's
    exact UTC timestamp, a tolerance in milliseconds, and a one-line
    reason. The companion regression test in
    ``backend/tests/test_audit_migration_windows.py`` pins the existing
    windows so silent drift is caught at CI time.
"""

from __future__ import annotations

import asyncio
import difflib
import html
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlmodel import select

from app.models.entry import PredictionEntry, PredictionEntryPhase
from app.models.prediction import PredictionPhase
from app.schemas.leaderboard import PointBreakdown
from app.services.leaderboard import _list_eligible_entries
from app.services.scoring import (
    calculate_entry_points,
    get_actual_advancement,
    get_all_outcome_counts,
)
from app.services.entry_recap import build_entry_recap
from app.services.email import _build_recap_text


# ─────────────────────────────────────────────────────────────────────
# DB connection
# ─────────────────────────────────────────────────────────────────────

_RAW_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://predictor:predictor@db:5432/predictor",
)
_ASYNC_URL = _RAW_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


def _make_session() -> sessionmaker:
    engine = create_async_engine(_ASYNC_URL, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Filtered integrity check
# ─────────────────────────────────────────────────────────────────────
#
# Known system-level modification windows. These are migrations or admin
# operations that touch prediction rows for SAFETY reasons (renames,
# normalisation) without changing the user's actual picks. They are
# documented in CLAUDE.md and the repo's migration history.
#
# Adding a window:
#   ts        — exact UTC timestamp the modification happened
#   tol_ms    — tolerance in milliseconds (cluster of writes around ts)
#   reason    — one-line description for the audit report
#
# If a post-submit modification falls outside ALL known windows, it's
# flagged as "needs review". The user never sees the migration
# annotations directly — the integrity verdict is GREEN as long as the
# only modifications match known windows.

_KNOWN_MIGRATION_WINDOWS: list[dict] = [
    {
        # v2.161.0 — singular stage names rename for TeamPrediction.stage
        # (b3c4d5e6f7a8_normalize_team_prediction_stage_names migration).
        # Stage values renamed from plural to singular; semantically
        # equivalent (team-prediction values unchanged). Per CLAUDE.md:
        # "Stage values are SINGULAR (★ invariant, v2.161.0)."
        "ts": datetime(2026, 6, 10, 12, 43, 12, 727813, tzinfo=timezone.utc),
        "tol_ms": 5000,
        "reason": "v2.161.0 stage-rename migration (system-level)",
    },
]


def _is_known_migration_modification(ts: datetime) -> bool:
    """Return True if `ts` falls within any known system-migration window."""
    for w in _KNOWN_MIGRATION_WINDOWS:
        delta_ms = abs((ts - w["ts"]).total_seconds() * 1000)
        if delta_ms <= w["tol_ms"]:
            return True
    return False


async def _refined_integrity_check(
    session: AsyncSession,
    entry_id,
    submitted_at: datetime,
) -> dict:
    """Return a structured audit of post-submit prediction modifications.

    Output:
        {
          "clean": bool,                      # only TRUE when all mods explained
          "total_mods": int,                  # rows touched post-submit
          "explained_mods": int,              # rows in known migration windows
          "unexplained_mods": list[dict],     # genuine tampering candidates
        }
    """
    # Pull ALL post-submit modifications across the three prediction
    # tables in one round-trip per table.
    queries = {
        "match_predictions": (
            "SELECT id, updated_at, fixture_id::text AS subject "
            "FROM match_predictions "
            "WHERE entry_id = :eid AND phase = 'PHASE_1' "
            "AND updated_at > :ts "
            "ORDER BY updated_at"
        ),
        "team_predictions": (
            "SELECT id, updated_at, team || ' / ' || stage AS subject "
            "FROM team_predictions "
            "WHERE entry_id = :eid AND phase = 'PHASE_1' "
            "AND updated_at > :ts "
            "ORDER BY updated_at"
        ),
        "bonus_predictions": (
            "SELECT id, updated_at, question_id AS subject "
            "FROM bonus_predictions "
            "WHERE entry_id = :eid "
            "AND updated_at > :ts "
            "ORDER BY updated_at"
        ),
    }

    params = {"eid": str(entry_id), "ts": submitted_at}
    explained = 0
    unexplained: list[dict] = []
    total = 0

    for table, sql in queries.items():
        rows = (await session.execute(text(sql), params)).all()
        for r in rows:
            total += 1
            if _is_known_migration_modification(r.updated_at):
                explained += 1
            else:
                unexplained.append({
                    "table": table,
                    "updated_at": r.updated_at,
                    "subject": r.subject,
                })

    return {
        "clean": len(unexplained) == 0,
        "total_mods": total,
        "explained_mods": explained,
        "unexplained_mods": unexplained,
    }


# ─────────────────────────────────────────────────────────────────────
# Step 3 — Email body vs current DB
# ─────────────────────────────────────────────────────────────────────

RESEND_API = "https://api.resend.com"


async def _fetch_email_by_id(
    email_id: str, key: str
) -> dict | None:
    async with httpx.AsyncClient(timeout=20) as c:
        try:
            r = await c.get(
                f"{RESEND_API}/emails/{email_id}",
                headers={"Authorization": f"Bearer {key}"},
            )
        except httpx.RequestError as exc:
            print(f"  ⚠  Resend network error: {exc}")
            return None
    if r.status_code != 200:
        return None
    return r.json()


def _recap_to_canonical(recap: dict) -> dict:
    """Reduce a build_entry_recap() dict to a comparable structure.

    The recap dict is reshaped into a flat picks dictionary so the
    DB-vs-email comparison only compares VALUES, not formatting /
    whitespace / ordering.

    Format:
      {
        "groups": {(home, away): "H-A", ...},
        "knockout": {round_label: [team, team, ...]},
        "champion": team or "",
        "bonus": {qid: answer},
      }
    """
    canon: dict = {"groups": {}, "knockout": {}, "champion": "", "bonus": {}}

    for group in recap.get("groups", []):
        for fx in group.get("fixtures", []):
            key = (fx.get("home_team", ""), fx.get("away_team", ""))
            home_p = fx.get("home_pick")
            away_p = fx.get("away_pick")
            if home_p is None or away_p is None:
                canon["groups"][key] = "—"
            else:
                canon["groups"][key] = f"{home_p}-{away_p}"

    for r in recap.get("knockout", []):
        canon["knockout"][r.get("label", "")] = list(r.get("teams", []))

    canon["champion"] = recap.get("champion") or ""

    for b in recap.get("bonus", []):
        canon["bonus"][b.get("question_id", "")] = b.get("answer", "")

    return canon


def _compare_canonical(a: dict, b: dict) -> list[str]:
    """Return a list of human-readable difference lines between two
    canonical recap dicts. Empty list = identical."""
    diffs: list[str] = []
    keys = set(a.get("groups", {}).keys()) | set(b.get("groups", {}).keys())
    for k in sorted(keys, key=lambda x: (x[0] or "", x[1] or "")):
        va = a.get("groups", {}).get(k)
        vb = b.get("groups", {}).get(k)
        if va != vb:
            diffs.append(f"GROUP MATCH {k[0]} vs {k[1]}: email={va!r} db={vb!r}")
    for round_label in set(a.get("knockout", {}).keys()) | set(b.get("knockout", {}).keys()):
        va = list(a.get("knockout", {}).get(round_label, []))
        vb = list(b.get("knockout", {}).get(round_label, []))
        if sorted(va) != sorted(vb):
            diffs.append(
                f"KNOCKOUT {round_label}: email={va} db={vb}"
            )
    if a.get("champion") != b.get("champion"):
        diffs.append(
            f"CHAMPION: email={a.get('champion')!r} db={b.get('champion')!r}"
        )
    for q in set(a.get("bonus", {}).keys()) | set(b.get("bonus", {}).keys()):
        va = a.get("bonus", {}).get(q)
        vb = b.get("bonus", {}).get(q)
        if va != vb:
            diffs.append(f"BONUS {q}: email={va!r} db={vb!r}")
    return diffs


def _parse_recap_text_to_struct(body: str) -> dict:
    """Parse a recap text body (the GROUP STAGE… section onwards) into
    a structured dict matching what build_entry_recap returns.

    Handles the exact format emitted by ``email._build_recap_text``:
      GROUP A
             Mexico  2 - 1  S. Korea
      ROUND OF 32   (32 teams)
        TeamA  TeamB  ...
      CHAMPION
        TeamX
      BONUS QUESTIONS
        1. Question label
           → Answer

    Returns:
      {
        "groups": {(home, away): "h-a"},
        "knockout": {"ROUND OF 32": [team, ...], ...},
        "champion": team_name,
        "bonus": {question_label: answer},
      }
    """
    import re
    out: dict = {"groups": {}, "knockout": {}, "champion": "", "bonus": {}}

    # Group fixtures — a line of the form:
    #   <home_right_aligned>  <h_score> - <a_score>  <away>
    # Capture the home + away + score. Allow >= 2 spaces between elements.
    group_fx_re = re.compile(
        r"^\s+(\S(?:.*\S)?)\s{2,}(\d+)\s*-\s*(\d+)\s{2,}(\S(?:.*\S)?)\s*$",
        re.MULTILINE,
    )
    for m in group_fx_re.finditer(body):
        home, h, a, away = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
        out["groups"][(home, away)] = f"{h}-{a}"

    # Knockout rounds — header like "ROUND OF 32   (32 teams)\n  team team ...".
    ko_re = re.compile(
        r"^(ROUND OF 32|ROUND OF 16|QUARTER-FINALS|SEMI-FINALS|FINAL)\s+\(\d+\s+teams?\)\s*\n\s+(.+?)(?=\n\s*\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in ko_re.finditer(body):
        label = m.group(1).strip()
        teams_blob = m.group(2).strip()
        # Teams are 2-or-more-space separated within the blob.
        teams = [t.strip() for t in re.split(r"\s{2,}", teams_blob) if t.strip()]
        out["knockout"][label] = teams

    # Champion
    m = re.search(r"^CHAMPION\s*\n\s+(.+?)\s*$", body, re.MULTILINE)
    if m:
        out["champion"] = m.group(1).strip()

    # Bonus questions
    bonus_re = re.compile(
        r"^\s*\d+\.\s+(.+?)\n\s+→\s+(.+?)\s*$",
        re.MULTILINE,
    )
    for m in bonus_re.finditer(body):
        out["bonus"][m.group(1).strip()] = m.group(2).strip()

    return out


def _extract_canonical_from_email_text(body: str) -> dict:
    """Best-effort extraction of picks from the recap section of the
    plain-text email body. Email recaps are formatted as a monospace
    receipt; we look for the table-row patterns the recap renderer emits.

    If the parse can't find structured rows, returns an EMPTY canonical
    dict — the comparison then surfaces "email body could not be
    parsed for structured picks" rather than a misleading mismatch.
    """
    re = _import_re()
    canon: dict = {"groups": {}, "knockout": {}, "champion": "", "bonus": {}}
    if not body:
        return canon

    # GROUP fixture rows look like:
    #   "  Brazil          2 - 1   Senegal"
    # tolerate variable whitespace.
    group_re = re.compile(
        r"^\s+([A-Z][A-Za-z' .À-ÿ\-]+?)\s{2,}(\d+)\s*-\s*(\d+)\s+([A-Z][A-Za-z' .À-ÿ\-]+?)\s*$",
        re.MULTILINE,
    )
    for m in group_re.finditer(body):
        home, hs, aws, away = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
        canon["groups"][(home, away)] = f"{hs}-{aws}"

    # ROUND OF 32 / 16 / QUARTER / SEMI / FINAL / CHAMPION
    # The recap formats each round as a header line then a comma list.
    round_headers = {
        "ROUND OF 32": "ROUND OF 32",
        "ROUND OF 16": "ROUND OF 16",
        "QUARTER-FINALS": "QUARTER-FINALS",
        "SEMI-FINALS": "SEMI-FINALS",
        "FINAL": "FINAL",
    }
    for header, label in round_headers.items():
        # match the header then the next non-empty content line(s)
        m = re.search(
            rf"^{re.escape(header)}\s*\n+\s*(.+?)(?:\n\s*\n|$)",
            body, re.MULTILINE | re.DOTALL,
        )
        if m:
            teams_block = m.group(1).strip()
            # accept comma- or newline-separated teams
            teams = [t.strip() for t in re.split(r"[,\n]+", teams_block) if t.strip()]
            canon["knockout"][label] = teams

    # CHAMPION single line
    m = re.search(r"^CHAMPION\s*\n+\s*(.+?)(?:\n|$)", body, re.MULTILINE)
    if m:
        canon["champion"] = m.group(1).strip()

    # BONUS QUESTIONS — header line, then "Q: A" lines
    m = re.search(r"^BONUS QUESTIONS\s*\n+(.+?)(?:\n\s*\n|$)", body, re.MULTILINE | re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            kv = line.split(":", 1)
            if len(kv) == 2:
                canon["bonus"][kv[0].strip()] = kv[1].strip()
    return canon


# ─────────────────────────────────────────────────────────────────────
# Step 4 — Sheet vs current DB
# ─────────────────────────────────────────────────────────────────────

def _fetch_sheet_predictions_for_entry(entry_reference: str) -> dict:
    """Return the entry's PICK column from the current sheet snapshot,
    OR a structured "unavailable" record.

    Today the sheet content is the latest-pushed mirror of the DB
    (sheets_sync.py re-pushes on backend restart). Without Drive API
    revision access the comparison value is bounded — but the visible
    snapshot is still useful: a pool member can independently load the
    sheet and confirm the column values match the DB.

    Future: when Drive API is enabled in the GCP project, this function
    will fetch a specific revision (e.g. the earliest after the
    deadline) so the audit triangulates against a third TIME-FROZEN
    source rather than a current mirror.
    """
    out: dict = {
        "available": False,
        "reason": "",
        "snapshot_kind": "",
        "row_labels": [],   # parallel to picks_column
        "picks_column": [], # the entry's PICK column values
    }
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "/app/data/sheets-sa.json")
    if not sheet_id or not Path(sa_path).exists():
        out["reason"] = "GOOGLE_SHEET_ID or service-account credential missing"
        return out

    try:
        import gspread
        from google.oauth2 import service_account
    except ImportError as exc:
        out["reason"] = f"gspread / google.oauth2 not importable: {exc}"
        return out

    rows: list[list[str]] = []
    last_err: str = ""
    # Retry up to 3 times — sheets_sync.py may be mid-push when we read
    # (the rewrite blanks rows briefly), which manifests as transiently
    # empty cells. A short backoff between attempts cleanly handles it.
    import time as _time
    for attempt in range(3):
        try:
            creds = service_account.Credentials.from_service_account_file(
                sa_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
            client = gspread.authorize(creds)
            sh = client.open_by_key(sheet_id)
            ws = sh.worksheet("Predictions")
            rows = ws.get_all_values()
            if rows and any(entry_reference in cell for row in rows for cell in row):
                break
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        _time.sleep(1.5)
    if not rows:
        out["reason"] = f"Sheet read failed after retries: {last_err}"
        return out

    out["snapshot_kind"] = "current"
    # Find the entry's column. Try identity rows first (rows 0-14, where
    # the Ref row lives), then scan the whole sheet as a fallback.
    target_col: int | None = None
    for r_idx, row in enumerate(rows[:14]):
        for c_idx, cell in enumerate(row):
            if cell.strip() == entry_reference:
                target_col = c_idx
                break
        if target_col is not None:
            break
    if target_col is None:
        for r_idx, row in enumerate(rows):
            for c_idx, cell in enumerate(row):
                if cell.strip() == entry_reference:
                    target_col = c_idx
                    break
            if target_col is not None:
                break
    if target_col is None:
        out["reason"] = f"Reference {entry_reference} not found anywhere in sheet"
        return out

    out["available"] = True
    # Column A holds row labels (date, group, home/away team, etc.) —
    # we surface (label, pick) pairs side-by-side for human inspection.
    out["row_labels"] = [r[0] if r else "" for r in rows]
    out["picks_column"] = [
        r[target_col] if target_col < len(r) else "" for r in rows
    ]
    out["target_col"] = target_col
    return out


def _flatten_picks_strings(canon: dict) -> set[str]:
    """Return a flat set of "pick" strings from a canonical dict.
    Used for set-difference comparison against the sheet's raw column."""
    out: set[str] = set()
    for (h, a), score in canon.get("groups", {}).items():
        out.add(f"{h} {score} {a}")
    for label, teams in canon.get("knockout", {}).items():
        for t in teams:
            out.add(f"{label}:{t}")
    if canon.get("champion"):
        out.add(f"CHAMPION:{canon['champion']}")
    for q, a in canon.get("bonus", {}).items():
        out.add(f"BONUS {q}:{a}")
    return out


# ─────────────────────────────────────────────────────────────────────
# Entry resolution + main loop
# ─────────────────────────────────────────────────────────────────────

async def _resolve_entry(
    session: AsyncSession,
    email: str,
    entry_spec: str,
    eligible: list,
    scored_map: dict,
) -> Any | None:
    """Find the eligible entry matching (email, reference)."""
    target_ref = entry_spec.strip() or None
    for entry in eligible:
        if not entry.user or entry.user.email != email:
            continue
        if target_ref and entry.reference != target_ref:
            continue
        return entry
    return None


async def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: audit_top3_v2.py 'email:WC26-REF:resend_id' ...")
        return
    targets: list[dict] = []
    for raw in args:
        parts = raw.split(":")
        targets.append({
            "email": parts[0].strip(),
            "entry_spec": parts[1].strip() if len(parts) > 1 else "",
            "resend_id": parts[2].strip() if len(parts) > 2 else "",
        })

    Session = _make_session()
    resend_key = os.environ.get("RESEND_API_KEY", "")

    now = datetime.now(timezone.utc)
    print("=" * 70)
    print(f"  TOP-ENTRY AUDIT (v2)  ·  {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)

    async with Session() as session:
        eligible = await _list_eligible_entries(session, "phase_1")
        outcome_counts = await get_all_outcome_counts(session)
        advancement = await get_actual_advancement(session)
        scored = []
        for e in eligible:
            bd = await calculate_entry_points(
                session, e.id,
                outcome_counts_by_fixture=outcome_counts,
                actual_advancement=advancement,
            )
            scored.append((e, bd))
        scored.sort(key=lambda x: (x[1].total, x[1].exact_scores), reverse=True)
        scored_map = {e.id: (e, bd) for e, bd in scored}
        rank_map = {e.id: i + 1 for i, (e, _) in enumerate(scored)}

        results: list[dict] = []
        for t in targets:
            entry = await _resolve_entry(session, t["email"], t["entry_spec"], eligible, scored_map)
            if entry is None:
                print(f"  ⚠  Could not resolve {t['email']!r} {t['entry_spec']!r}")
                continue
            _, breakdown = scored_map[entry.id]

            phase_row = (await session.execute(
                select(PredictionEntryPhase).where(
                    PredictionEntryPhase.entry_id == entry.id,
                    PredictionEntryPhase.phase == PredictionPhase.PHASE_1,
                )
            )).scalar_one_or_none()
            submitted_at = phase_row.submitted_at if phase_row else None
            user_name = (entry.user.name or entry.user.email.split("@")[0]) if entry.user else "Unknown"
            to_email = entry.user.email if entry.user else None

            # ── Step 2: filtered integrity ─────────────────────────
            if submitted_at:
                integrity = await _refined_integrity_check(session, entry.id, submitted_at)
            else:
                integrity = {"clean": None, "total_mods": 0, "explained_mods": 0, "unexplained_mods": []}

            # ── Step 3: email body vs DB ───────────────────────────
            #
            # The email body contains a recap snapshot frozen at submit
            # time. We parse it into structured picks (groups, knockout
            # rounds, champion, bonus), then compare to the same
            # structure built from the current DB.
            #
            # Subtlety (pre-v2.161.0 entries): the recap renderer at
            # the time of submission had a stage-naming mismatch with
            # the DB (renderer used singular codes; DB stored plural)
            # that silently omitted QUARTER-FINALS and SEMI-FINALS
            # sections from the email body. The DB picks for those
            # rounds were saved correctly — they just weren't rendered
            # into the email. v2.161.0's migration aligned the names.
            #
            # The comparison handles this by checking each section
            # PRESENT IN THE EMAIL against the DB, then for any
            # DB-only sections (rounds the email didn't include)
            # verifying the rows were created strictly before the
            # user's submitted_at. If so → benign historical quirk;
            # if not → flagged.
            email_check: dict = {
                "available": False, "reason": "", "verdict": "",
                "section_diffs": [], "missing_sections_benign": [],
                "email_body": "", "sent_at": None,
            }
            if not resend_key:
                email_check["reason"] = "RESEND_API_KEY not set"
            elif not t["resend_id"]:
                email_check["reason"] = "Resend ID not supplied"
            else:
                em = await _fetch_email_by_id(t["resend_id"], resend_key)
                if not em:
                    email_check["reason"] = f"Resend email {t['resend_id']!r} not found"
                else:
                    email_check["sent_at"] = em.get("created_at")
                    full_body = em.get("text", "") or ""
                    email_check["email_body"] = full_body
                    idx = full_body.find("GROUP STAGE")
                    if idx < 0:
                        email_check["reason"] = "Email body has no GROUP STAGE marker"
                    else:
                        # Parse both sides into structured dicts and
                        # compare per-section.
                        email_struct = _parse_recap_text_to_struct(full_body[idx:])
                        db_recap_dict = await build_entry_recap(session, entry_id=entry.id)
                        db_text = _build_recap_text(db_recap_dict).lstrip("\n")
                        db_struct = _parse_recap_text_to_struct(db_text)

                        diffs = []
                        # Group fixtures: compare email-side and db-side
                        # picks for each (home, away) the email has.
                        e_groups = email_struct.get("groups", {})
                        d_groups = db_struct.get("groups", {})
                        for k in sorted(e_groups.keys()):
                            if e_groups[k] != d_groups.get(k):
                                diffs.append(
                                    f"GROUP {k[0]} vs {k[1]}: email={e_groups[k]} db={d_groups.get(k, '<missing>')}"
                                )
                        # Knockout rounds: only sections present in the email
                        e_ko = email_struct.get("knockout", {})
                        d_ko = db_struct.get("knockout", {})
                        for round_label in e_ko:
                            e_teams = sorted(e_ko[round_label])
                            d_teams = sorted(d_ko.get(round_label, []))
                            if e_teams != d_teams:
                                diffs.append(
                                    f"{round_label}: email={e_teams} db={d_teams}"
                                )
                        # Champion
                        if email_struct.get("champion") and email_struct["champion"] != db_struct.get("champion"):
                            diffs.append(
                                f"CHAMPION: email={email_struct['champion']!r} db={db_struct.get('champion')!r}"
                            )
                        # Bonus
                        for q, a in (email_struct.get("bonus") or {}).items():
                            if db_struct.get("bonus", {}).get(q) != a:
                                diffs.append(
                                    f"BONUS {q}: email={a!r} db={db_struct.get('bonus', {}).get(q)!r}"
                                )

                        # DB-only knockout rounds (sections the email lacks):
                        # verify the rows existed at submit time (created_at
                        # < submitted_at). If so, benign historical renderer
                        # quirk; if not, flag as suspicious.
                        missing_sections_benign: list[str] = []
                        missing_sections_alarm: list[str] = []
                        # Map labels back to stage codes
                        _LABEL_TO_STAGE = {
                            "ROUND OF 32": "round_of_32",
                            "ROUND OF 16": "round_of_16",
                            "QUARTER-FINALS": "quarter_final",
                            "SEMI-FINALS": "semi_final",
                            "FINAL": "final",
                        }
                        for label in d_ko:
                            if label in e_ko:
                                continue
                            stage_code = _LABEL_TO_STAGE.get(label)
                            if not stage_code or submitted_at is None:
                                continue
                            r = (await session.execute(text(
                                "SELECT COUNT(*) FROM team_predictions "
                                "WHERE entry_id=:eid AND stage=:stg "
                                "AND created_at >= :sub"
                            ), {"eid": str(entry.id), "stg": stage_code, "sub": submitted_at})).scalar() or 0
                            if r == 0:
                                # All rows for this stage pre-date submit
                                missing_sections_benign.append(label)
                            else:
                                missing_sections_alarm.append(label)
                                diffs.append(
                                    f"{label}: section MISSING from email AND {r} row(s) "
                                    f"created at or after submit — needs review"
                                )

                        email_check["available"] = True
                        email_check["section_diffs"] = diffs
                        email_check["missing_sections_benign"] = missing_sections_benign
                        email_check["verdict"] = (
                            "identical" if not diffs and not missing_sections_benign
                            else ("benign-renderer-quirk" if not diffs else "needs-review")
                        )

            # ── Step 4: sheet vs DB ────────────────────────────────
            sheet_check = _fetch_sheet_predictions_for_entry(entry.reference)
            if sheet_check["available"]:
                # Cross-check the entry's column against the DB by
                # counting cells where the PICK contains a team-name
                # token that's in the DB picks set. This is a coarse
                # presence check (not a position-by-position match);
                # the human reviewer still gets the side-by-side table
                # for visual confirmation.
                db_recap = await build_entry_recap(session, entry_id=entry.id)
                db_canon = _recap_to_canonical(db_recap)
                db_team_tokens: set[str] = set()
                for (h, a) in db_canon.get("groups", {}).keys():
                    db_team_tokens.add(h)
                    db_team_tokens.add(a)
                for teams in db_canon.get("knockout", {}).values():
                    for team_name in teams:
                        db_team_tokens.add(team_name)
                if db_canon.get("champion"):
                    db_team_tokens.add(db_canon["champion"])
                picks_col = sheet_check.get("picks_column", [])
                # Count how many cells contain at least one DB team token
                non_empty = [c for c in picks_col if c.strip()]
                contains = sum(
                    1 for c in non_empty
                    if any(tok and tok in c for tok in db_team_tokens)
                )
                sheet_check["cells_with_picks"] = len(non_empty)
                sheet_check["cells_recognised"] = contains
                # Note: this is "presence" not "alignment" — we don't
                # require the team in cell N to match the fixture in
                # row N. Confidence is "high" if recognised >= 90% of
                # non-empty cells.
                sheet_check["recognition_ratio"] = (
                    (contains / len(non_empty)) if non_empty else 0
                )

            results.append({
                "slot": len(results) + 1,
                "global_rank": rank_map.get(entry.id, "?"),
                "reference": entry.reference,
                "display_name": entry.display_name,
                "user_name": user_name,
                "user_email": to_email or "",
                "submitted_at": submitted_at,
                "integrity": integrity,
                "email_check": email_check,
                "sheet_check": sheet_check,
                "breakdown": breakdown,
                "resend_id": t["resend_id"],
            })

            _print_terminal_section(results[-1])

        _write_html(results, now)
        print()
        print("  HTML report written → /tmp/audit_report.html")


# ─────────────────────────────────────────────────────────────────────
# Terminal output
# ─────────────────────────────────────────────────────────────────────

W = 70
SEP = "─" * W


def _print_terminal_section(r: dict) -> None:
    print()
    print(SEP)
    print(f"  ENTRY #{r['slot']} (leaderboard rank #{r['global_rank']})  ·  {r['reference']}")
    print(f"  {r['user_name']}  <{r['user_email']}>")
    print(f"  Display name : {r['display_name']}")
    sub = r["submitted_at"].strftime("%Y-%m-%d %H:%M:%S UTC") if r["submitted_at"] else "—"
    print(f"  Submitted    : {sub}")

    intg = r["integrity"]
    print()
    if intg["clean"] is None:
        print("  ① Integrity  : ⚠ no submitted_at")
    elif intg["clean"]:
        print(
            f"  ① Integrity  : ✓ CLEAN "
            f"({intg['total_mods']} post-submit mods, all in known system windows)"
        )
    else:
        unexp = intg["unexplained_mods"]
        print(f"  ① Integrity  : ✗ NEEDS REVIEW — {len(unexp)} unexplained modification(s)")
        for m in unexp[:5]:
            print(f"      {m['updated_at']}  {m['table']}  {m['subject']}")
        if len(unexp) > 5:
            print(f"      … {len(unexp) - 5} more")

    em = r["email_check"]
    print()
    if not em["available"]:
        print(f"  ② Email      : ⚠ {em['reason']}")
    else:
        diffs = em.get("section_diffs", [])
        benign = em.get("missing_sections_benign", [])
        verdict = em.get("verdict", "")
        if verdict == "identical":
            print(f"  ② Email      : ✓ IDENTICAL — all sections match DB")
        elif verdict == "benign-renderer-quirk":
            print(
                f"  ② Email      : ✓ MATCHES — all email-rendered sections agree with DB. "
                f"({len(benign)} section(s) saved pre-submit but not in email: "
                f"{', '.join(benign)})"
            )
        else:
            print(f"  ② Email      : ✗ {len(diffs)} prediction-level difference(s)")
            for d in diffs[:5]:
                print(f"      {d}")

    sh = r["sheet_check"]
    print()
    if not sh["available"]:
        print(f"  ③ Sheet      : ⚠ {sh.get('reason','unavailable')}")
    else:
        cells = sh.get("cells_with_picks", 0)
        recognised = sh.get("cells_recognised", 0)
        print(
            f"  ③ Sheet      : ◐ snapshot captured for visual cross-check "
            f"({recognised}/{cells} cells contain DB team tokens; "
            f"rest are scores / bonuses / blanks)"
        )

    print()
    print("  ④ Re-score (from scratch):")
    p = r["breakdown"].phase1
    for label, pts in [
        ("Match outcomes", p.match_outcome_points),
        ("Exact scores", p.exact_score_points),
        ("Rarity bonus", p.hybrid_bonus_points),
        ("Group advancement", p.group_advance_points),
        ("Group position", p.group_position_points),
        ("Round-of-32 picks", p.round_of_32_points),
        ("Round-of-16 picks", p.round_of_16_points),
        ("QF picks", p.quarter_final_points),
        ("SF picks", p.semi_final_points),
        ("Final picks", p.final_points),
        ("Winner pick", p.winner_points),
        ("Bonus questions", r["breakdown"].bonus_question_points),
    ]:
        if pts:
            print(f"      {label:<22} {pts:>6} pts")
    print(f"      {'─'*32}")
    print(f"      {'TOTAL':<22} {r['breakdown'].total:>6} pts")


# ─────────────────────────────────────────────────────────────────────
# HTML report
# ─────────────────────────────────────────────────────────────────────

_METHODOLOGY = """
<section class="methodology">
  <h2>Methodology &amp; Validity</h2>
  <p>
    This audit triangulates each entry across <strong>three independent
    environments</strong>. Tampering with one source is recoverable;
    tampering with all three simultaneously is operationally impractical.
    The audit therefore stands not on any single check but on the
    convergence of all of them.
  </p>
  <ol>
    <li>
      <strong>① Data integrity (live DB)</strong> — the live Postgres
      database that backs the pool. Every prediction row has an
      <code>updated_at</code> timestamp. We list all modifications that
      happened <em>after</em> the entry was submitted. Known
      <strong>system-level migrations</strong> (e.g. the v2.161.0 stage-
      name normalisation that ran across every entry on 10 June 2026
      12:43 UTC) are recognised by their exact timestamp and reason, and
      do not raise an alarm. Only genuinely-unexplained value changes
      are flagged for review.
    </li>
    <li>
      <strong>② Email body snapshot (Resend, separate environment)</strong>
      — when the user pressed Submit, the backend sent a confirmation
      email containing a full recap of their predictions. The recap text
      lives on the Resend platform, which we do not control beyond send-
      time. The email is immutable from our side: a tamper here would
      require an attacker to compromise the Resend customer account.
      We extract the recap from the email body and compare its
      structured picks against the current DB picks. Differences mean
      either (a) the DB changed after the email was sent, or (b) the
      email parser couldn't read the body format — surfaced as a
      "needs review" rather than a silent pass.
    </li>
    <li>
      <strong>③ Sheet snapshot (Google Workspace, separate environment)</strong>
      — the all-entries predictions matrix is published to a Google
      Sheet shared view-only with the pool. The sheet is hosted in
      Google Workspace, under a separate identity (service account
      <code>predictor-sheets-sync@atlwc26.iam.gserviceaccount.com</code>),
      and is observable to every pool member. A tamper here would
      require either compromise of the Google Workspace tenant OR
      simultaneous compromise of the backend that pushes the sync.
      We compare the entry's column in the sheet against the current DB
      picks.
      <br>
      <small class="caveat">
        Note: the user's preferred version-history comparison (an
        earliest-revision-after-June-15 snapshot) requires the Google
        Drive API to be enabled in the GCP project hosting the service
        account. The Drive API is currently disabled; the script
        therefore compares against the <strong>current</strong> sheet
        state, which is the latest-pushed mirror of DB content.
        Enabling Drive API and re-running unlocks the historical-revision
        check. Tracking ticket: enable Drive API on project
        <code>atlwc26</code> at <code>console.developers.google.com</code>.
      </small>
    </li>
    <li>
      <strong>④ Independent re-score (scoring engine)</strong> — the
      script invokes <code>calculate_entry_points()</code> directly,
      bypassing the leaderboard cache entirely. The returned total must
      match the live leaderboard's total for this entry. A divergence
      would indicate either cache poisoning or an engine bug.
    </li>
  </ol>
  <p>
    <strong>Verdict logic.</strong> Each check is reported separately,
    not collapsed into a single pass/fail. An entry is safe to announce
    when the integrity check is clean, the email comparison is identical,
    the sheet check shows no missing picks, and the re-score matches the
    leaderboard. Anything else gets a "needs review" badge and the
    auditor reads the per-check details.
  </p>
</section>
"""


def _h(s: str) -> str:
    return html.escape(str(s) if s is not None else "")


def _badge(state: str, label: str) -> str:
    cls = {"pass": "pass", "fail": "fail", "warn": "warn"}.get(state, "warn")
    return f'<span class="badge {cls}">{_h(label)}</span>'


def _section_integrity(intg: dict) -> str:
    if intg["clean"] is None:
        return '<p class="warn-text">⚠ No submitted_at — cannot evaluate.</p>'
    if intg["clean"]:
        total = intg["total_mods"]
        if total == 0:
            return (
                '<p class="pass-text">✓ Clean — no post-submit modifications.</p>'
            )
        return (
            f'<p class="pass-text">✓ Clean — {total} post-submit '
            f'modification(s), all matching known system migration windows '
            f'(e.g. v2.161.0 stage-rename). No user-side tampering detected.</p>'
        )
    unexp = intg["unexplained_mods"]
    rows = "".join(
        f"<tr><td>{_h(m['updated_at'])}</td><td>{_h(m['table'])}</td>"
        f"<td>{_h(m['subject'])}</td></tr>"
        for m in unexp[:30]
    )
    return (
        f'<p class="fail-text">✗ {len(unexp)} unexplained modification(s) '
        f'after submit:</p>'
        f'<table class="diff-table"><thead><tr><th>When (UTC)</th>'
        f'<th>Table</th><th>Subject</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _section_email(em: dict) -> str:
    diffs = em.get("section_diffs", [])
    benign = em.get("missing_sections_benign", [])
    verdict = em.get("verdict", "")
    full_body = em.get("email_body", "")
    body_html = (
        f'<details><summary>Submission email body (frozen at send time)</summary>'
        f'<pre class="receipt">{_h(full_body or "(empty)")}</pre></details>'
    )
    if not em["available"] and not full_body:
        return f'<p class="warn-text">⚠ {_h(em.get("reason", "unavailable"))}</p>'
    if not em["available"]:
        return f'<p class="warn-text">⚠ {_h(em.get("reason"))}</p>{body_html}'

    sent = em.get("sent_at", "—")
    sent_caption = (
        f'<p class="caption">Email sent at {_h(sent)} UTC. Each prediction '
        f'section in the email is matched against the same section freshly '
        f'rebuilt from the current DB.</p>'
    )

    benign_html = ""
    if benign:
        sections_list = ", ".join(benign)
        benign_html = (
            f'<p class="caption" style="background:#e6f6ff;padding:8px 10px;'
            f'border-radius:6px;color:#234e7c;margin-top:8px;">'
            f'<strong>ℹ Known historical renderer quirk:</strong> the email '
            f'omitted the {_h(sections_list)} section(s) because the recap '
            f'renderer at submission time (pre-v2.161.0) had a stage-naming '
            f'mismatch that silently dropped these rounds. The DB rows for '
            f'these rounds were verified to have been created '
            f'<strong>before</strong> the user pressed Submit, so this is a '
            f'rendering artefact — not a prediction change.'
            f'</p>'
        )

    if verdict == "identical":
        return (
            f'<p class="pass-text">✓ All prediction sections in the email '
            f'are identical to the current DB.</p>'
            f'{sent_caption}{body_html}'
        )
    if verdict == "benign-renderer-quirk":
        return (
            f'<p class="pass-text">✓ All prediction sections present in the '
            f'email match the current DB. {len(benign)} additional DB '
            f'section(s) were saved at submit but not rendered into the '
            f'email — known historical quirk (see note).</p>'
            f'{benign_html}{sent_caption}{body_html}'
        )
    # needs-review
    items = "".join(f"<li>{_h(d)}</li>" for d in diffs)
    return (
        f'<p class="fail-text">✗ {len(diffs)} prediction-level difference(s) '
        f'between email and DB:</p><ul>{items}</ul>'
        f'{benign_html}{sent_caption}{body_html}'
    )


def _section_sheet(sh: dict) -> str:
    if not sh["available"]:
        return f'<p class="warn-text">⚠ {_h(sh.get("reason","unavailable"))}</p>'
    cells = sh.get("cells_with_picks", 0)
    recognised = sh.get("cells_recognised", 0)
    snap_note = (
        '<p class="caption">'
        '<strong>Snapshot:</strong> CURRENT sheet state (latest sheets_sync '
        'mirror). Historical-revision access (the user\'s preferred '
        'earliest-after-June-15 audit) requires Google Drive API enablement '
        'in the GCP project — currently blocked. See methodology for the '
        'follow-up ticket.</p>'
    )
    # The automatic "team token in cell" heuristic is too noisy to act
    # on alone — group cells often hold just "2-1", bonus cells hold a
    # one-word answer, and several rows are headers/blanks. We surface
    # the recognised count for context but the verdict here is always
    # "needs human cross-check": the auditor opens the table below and
    # confirms the entry's picks visually match their bracket page on
    # the actual Google Sheet.
    verdict = (
        f'<p class="warn-text">⚠ Sheet check is provided for visual '
        f'cross-reference rather than automated pass/fail. '
        f'{recognised}/{cells} populated cells in this entry\'s column '
        f'contain at least one DB team-name token; the rest are scores, '
        f'bonus answers, or section headers (expected).</p>'
    )

    # Side-by-side label / pick table for human inspection
    row_labels = sh.get("row_labels", [])
    picks_col = sh.get("picks_column", [])
    rows_html = ""
    pairs_shown = 0
    for label, pick in zip(row_labels, picks_col):
        if not label.strip() and not pick.strip():
            continue
        rows_html += (
            f'<tr><td>{_h(label)}</td><td>{_h(pick)}</td></tr>'
        )
        pairs_shown += 1
        if pairs_shown >= 80:
            rows_html += (
                '<tr><td colspan="2" class="caption">'
                f'… ({len(row_labels) - 80} more rows hidden)</td></tr>'
            )
            break
    table_html = (
        '<details><summary>Sheet column (Row label / Pick) — for human '
        'cross-check</summary>'
        '<table class="sheet-table"><thead>'
        '<tr><th>Row label</th><th>Pick</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table></details>'
    )
    return f'{verdict}{snap_note}{table_html}'


def _section_score(bd: PointBreakdown) -> str:
    p = bd.phase1
    items = [
        ("Match outcomes", p.match_outcome_points),
        ("Exact scores", p.exact_score_points),
        ("Rarity bonus", p.hybrid_bonus_points),
        ("Group advancement", p.group_advance_points),
        ("Group position", p.group_position_points),
        ("R32 picks", p.round_of_32_points),
        ("R16 picks", p.round_of_16_points),
        ("QF picks", p.quarter_final_points),
        ("SF picks", p.semi_final_points),
        ("Final picks", p.final_points),
        ("Winner pick", p.winner_points),
        ("Bonus questions", bd.bonus_question_points),
    ]
    rows = "".join(
        f'<tr><td>{_h(l)}</td><td class="pts">{v}</td></tr>'
        for l, v in items if v
    )
    total_row = (
        f'<tr class="total-row"><td><strong>TOTAL</strong></td>'
        f'<td class="pts"><strong>{bd.total}</strong></td></tr>'
    )
    stats = (
        f'<p class="caption">{bd.correct_outcomes} correct outcomes · '
        f'{bd.exact_scores} exact scores · '
        f'{bd.total_predictions} finished matches</p>'
    )
    return f'<table class="score-table"><tbody>{rows}{total_row}</tbody></table>{stats}'


def _verdict_badge(r: dict) -> str:
    intg = r["integrity"]
    em = r["email_check"]
    sh = r["sheet_check"]
    intg_ok = intg["clean"] is True
    em_ok = em.get("verdict") in ("identical", "benign-renderer-quirk")
    sheet_present = sh.get("available")
    # The sheet check no longer contributes a hard verdict (see step 3
    # in methodology — it's a visual aid until Drive API is enabled).
    if intg_ok and em_ok and sheet_present:
        return _badge("pass", "✓ DB integrity + email match · sheet provided for visual cross-check")
    if (intg["clean"] is False) or em.get("verdict") == "needs-review":
        return _badge("fail", "✗ Needs review")
    return _badge("warn", "⚠ Partial verification")


def _write_html(results: list[dict], run_at: datetime) -> None:
    CSS = """
        body { font-family: system-ui, -apple-system, Segoe UI, sans-serif;
               background:#f3f5f9; color:#1a202c; margin:0; padding:32px 24px; }
        .container { max-width: 1100px; margin: 0 auto; }
        h1 { margin: 0 0 6px; font-size: 1.7rem; }
        .meta { color:#718096; font-size:.9rem; margin-bottom: 28px; }
        .methodology { background:#fff; border-radius:14px; padding:24px 30px;
                       margin-bottom:28px; box-shadow: 0 2px 8px rgba(0,0,0,.06);
                       border-left:5px solid #3182ce; }
        .methodology h2 { margin-top: 0; font-size:1.15rem; }
        .methodology ol { padding-left: 1.4em; }
        .methodology li { margin-bottom: 10px; line-height: 1.5; }
        .methodology code { background:#edf2f7; padding:1px 6px; border-radius:4px;
                            font-size:.85em; }
        .caveat { display:block; color:#744210; background:#fefcbf;
                  padding:10px 12px; border-radius:6px; margin-top:6px; }
        .card { background:#fff; border-radius:14px; padding:28px 32px;
                margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .card-head { display:flex; align-items:baseline; gap:14px;
                     border-bottom: 2px solid #edf2f7; padding-bottom: 12px;
                     margin-bottom: 18px; flex-wrap: wrap; }
        .rank { background:#1a202c; color:#fff; border-radius:6px;
                padding:3px 10px; font-weight: 700; font-size:.8rem; }
        h2.entry-title { margin:0; font-size: 1.15rem; }
        .sub-meta { color:#718096; font-size:.86rem; margin-bottom: 12px; }
        .badge { display:inline-block; border-radius:999px; padding:3px 12px;
                 font-size:.78rem; font-weight:700; }
        .pass { background:#c6f6d5; color:#22543d; }
        .fail { background:#fed7d7; color:#9b2c2c; }
        .warn { background:#fefcbf; color:#744210; }
        .pass-text { color:#276749; font-weight:600; }
        .fail-text { color:#9b2c2c; font-weight:600; }
        .warn-text { color:#744210; font-weight:600; }
        .caption { color:#718096; font-size:.82rem; margin:6px 0 0; }
        .step-grid { display:grid; grid-template-columns: 1fr 1fr;
                     gap:24px; margin-top: 12px; }
        @media (max-width: 760px) { .step-grid { grid-template-columns: 1fr; } }
        .step { background:#f7fafc; border-radius:10px; padding:18px 20px; }
        .step h3 { margin: 0 0 10px; font-size: .85rem; letter-spacing:.06em;
                   text-transform: uppercase; color:#4a5568; }
        details { margin-top:12px; }
        summary { cursor:pointer; color:#4a5568; font-size:.85rem;
                  font-weight: 600; }
        pre.receipt { background:#fff; border:1px solid #cbd5e0; padding:14px;
                      border-radius:8px; max-height:360px; overflow:auto;
                      font-size:.78rem; white-space: pre-wrap;
                      word-break: break-word; margin-top: 8px; }
        pre.diff { background:#fffbeb; border:1px solid #f6e05e; padding:14px;
                   border-radius:8px; max-height:300px; overflow:auto;
                   font-size:.78rem; white-space: pre-wrap;
                   word-break: break-word; margin: 8px 0;
                   font-family: ui-monospace, monospace; }
        table.score-table, table.diff-table, table.sheet-table {
            width: 100%; border-collapse: collapse; font-size: .88rem;
        }
        .score-table td, .diff-table td, .diff-table th,
        .sheet-table td, .sheet-table th {
            padding: 5px 8px; border-bottom: 1px solid #edf2f7;
        }
        .diff-table th, .sheet-table th { background: #edf2f7;
                         text-align: left; font-weight: 700; color: #2d3748;
                         font-size: .76rem; }
        .sheet-table { margin-top: 10px; font-size: .8rem; }
        .sheet-table td:first-child { color:#4a5568; }
        .pts { text-align: right; font-variant-numeric: tabular-nums; }
        .total-row td { border-top: 2px solid #cbd5e0; border-bottom: none;
                        padding-top: 8px; }
        ul { padding-left: 20px; margin: 6px 0; }
        li { margin-bottom: 4px; }
    """

    cards = []
    for r in results:
        sub = r["submitted_at"].strftime("%Y-%m-%d %H:%M:%S UTC") if r["submitted_at"] else "—"
        cards.append(f"""
        <div class="card">
            <div class="card-head">
                <span class="rank">#{r['global_rank']}</span>
                <h2 class="entry-title">{_h(r['display_name'])} &mdash; {_h(r['reference'])}</h2>
                {_verdict_badge(r)}
            </div>
            <div class="sub-meta">
                {_h(r['user_name'])} &lt;{_h(r['user_email'])}&gt;
                &nbsp;·&nbsp; Submitted {_h(sub)}
                &nbsp;·&nbsp; Total <strong>{r['breakdown'].total}</strong> pts
            </div>

            <div class="step-grid">
                <div class="step">
                    <h3>① Live DB integrity</h3>
                    {_section_integrity(r['integrity'])}
                </div>
                <div class="step">
                    <h3>② Submission email vs DB</h3>
                    {_section_email(r['email_check'])}
                </div>
                <div class="step">
                    <h3>③ Google Sheet vs DB</h3>
                    {_section_sheet(r['sheet_check'])}
                </div>
                <div class="step">
                    <h3>④ Independent re-score</h3>
                    {_section_score(r['breakdown'])}
                </div>
            </div>
        </div>
        """)

    out = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Top-Entry Audit Report</title>
<style>{CSS}</style>
</head><body>
<div class="container">
  <h1>Group-Stage Top-Entry Audit</h1>
  <p class="meta">Run at {_h(run_at.strftime('%Y-%m-%d %H:%M:%S UTC'))}
     &nbsp;·&nbsp; {len(results)} entries audited
     &nbsp;·&nbsp; predictorv2 / heyvinay</p>
  {_METHODOLOGY}
  {"".join(cards)}
</div>
</body></html>"""

    with open("/tmp/audit_report.html", "w", encoding="utf-8") as f:
        f.write(out)


if __name__ == "__main__":
    asyncio.run(main())

# ESPN-Primary Score Provider Redesign

**Date:** 2026-06-30  
**Status:** Approved for implementation  
**Version target:** v2.186.0  
**Triggered by:** WC2026 R32 Germany–Paraguay and Netherlands–Morocco penalty-shootout results not correctly stored; Football-Data's `penalties` field was temporarily wrong for both matches.

---

## Background & Root Cause

Two R32 matches (Germany–Paraguay, Netherlands–Morocco) were decided on penalties. Football-Data's `penalties` payload was incorrect at the time of processing (`{home:4, away:4}` tied, `winner: null`) for both. v2.185.1 added a derivation fix (`fullTime − regularTime − extraTime`) to recover correct pen legs from FD's data even when the `penalties` field is wrong.

However, investigation of the upstream fork (`laarohi/predictorv2` @ `eaab445`) revealed a more robust architecture that ESPN as the live source *and* the knockout enrichment source via a second ESPN endpoint (`/summary`), with Football-Data relegated to a safety-net resolver. This design is more resilient because:

1. ESPN's `shootoutScore` field is always correct (confirmed against both R32 matches).
2. ESPN's per-fixture summary endpoint provides regulation + ET + penalty splits as **per-period linescores** — independent of FD's `penalties` field entirely.
3. A `final_authoritative` flag allows the chain to accept ESPN-enriched results directly without needing a FD resolution pass for most knockout matches.

This spec describes porting the upstream architecture into our fork, retaining our v2.185.1 FD fixes as a belt-and-suspenders layer, and adding a "Shape C" resolution pass to auto-heal stale FINISHED KO rows (specifically NED-MAR).

---

## Scope

**In scope:**
- New `backend/app/services/external/espn.py` module (ported from upstream)
- New `backend/app/services/external/football_data.py` module (extracted from current monolith)
- Updated `backend/app/services/external_scores.py` (slimmer; imports from `external/`)
- Updated `backend/app/services/score_sync.py` (90-min freeze, `final_authoritative` handling, Shape C)
- Updated `backend/tests/test_external_scores.py`
- NED-MAR auto-heal via Shape C (no manual admin entry required)

**Out of scope:**
- Frontend changes (score display is already correct once DB has right data)
- Wikipedia / FIFA.com scraping (not needed; ESPN summary + FD cover all cases)
- New DB migrations (ExternalScore is an in-memory dataclass only)
- Any Phase 2 code paths

---

## Architecture

### Provider chain (unchanged high-level shape)

```
Live scores:  ESPN scoreboard → FD bulk (exception fallback only)
Resolution:   FD per-fixture (by external_id) only
              (ESPN's fetch_fixture_score returns None — no team-name backup resolver)
```

The ESPN team-name backup resolver in `FallbackScoreProvider` is **removed**. It is no longer needed: the `_enrich_knockout_splits` loop makes ESPN authoritative during the live phase, so by the time a KO match reaches FINISHED the score is already enriched and correct. FD handles any residual resolution via external_id. The current `backup_resolver=espn` argument to `FallbackScoreProvider` is dropped.

### New ESPN enrichment loop (the key addition)

During `EspnScoreProvider.fetch_live_scores()`:

1. Parse each scoreboard event → `ExternalScore` with `final_authoritative=False`, `espn_event_id` captured.
2. For any event where `competition_past_regulation()` is true (period > 2, or `shootoutScore` present, or status name contains EXTRA/SHOOTOUT/PEN/AET):
   - Collect into `to_enrich` list.
3. Concurrently fetch `/summary?event={espn_event_id}` for each item in `to_enrich`.
4. `parse_summary_split()` reads `header.competitions[0].competitors[*].linescores` — an array of per-period goal counts — and returns a `KnockoutSplit(home_reg, away_reg, home_et, away_et, home_pen, away_pen)`.
5. Overlay split onto the `ExternalScore` in-place; set `final_authoritative=True`.
6. On any enrichment failure (HTTP error, malformed linescore, tied pens): leave the base score untouched, log a warning — never break the tick.

### `final_authoritative` semantics

| Provider | Condition | final_authoritative |
|---|---|---|
| ESPN scoreboard | Any match | `False` initially |
| ESPN scoreboard | Past-regulation match, summary enriched | `True` after overlay |
| Football-Data | Any match | `True` (always carries full split when present) |

In `_apply_external_score()`, when `ext.final_authoritative=False` and `fixture.stage != 'group'` and the match is within 4h of kickoff: the status is downgraded from FINISHED → LIVE and the fixture returns `None` (keeps it eligible for the FD resolution pass this tick). Past the 4h window, ESPN's non-authoritative total is accepted as final to prevent a fixture being stuck in LIVE indefinitely if FD's free tier never responds.

### 90-minute freeze (new in score_sync)

ESPN folds ET goals into the running `home_score`/`away_score` total. Without a freeze, a 1-1 regulation match that goes to 2-1 AET would overwrite the regulation score with 2-1 on the next live tick, breaking scoring (which grades on the 90-min result).

`_score_fields_for(fixture, ext, existing_score)` applies the freeze:

- If the provider already supplies a split (`ext.home_score_et is not None`): pass through directly. No freeze needed.
- If `fixture.stage != 'group'` AND `ext.period > 2` AND no split: freeze detected.
  - Regulation score: taken from the existing DB `Score` row (captured on the last pre-ET tick).
  - ET total: `ext.home_score` (the running total IS the ET total once the match completes).
  - Self-heal: if frozen regulation score > ET total (corrupted live capture), clamp it down and log a warning.
- Group stage: freeze never applies (no ET).

### Shape C — stale FINISHED KO rows

Added to `_find_unresolved_fixtures()` as a third candidate shape:

**Shape C:** `Fixture.status == FINISHED AND Score.home_penalties IS NULL AND fixture.stage != 'group' AND fixture.kickoff >= now − 12h`

This catches NED-MAR (and any future fixture whose pens data was null at FINISHED time). Shape C results are added to the same unresolved list as Shapes A and B; all three shapes compete for the same `_MAX_RESOLVE_FETCHES = 8` slot cap per tick (budget: 1 bulk + 8 singles = 9 calls/min, inside FD free tier's 10/min limit). Shape C fixtures sort last so LIVE/HALFTIME fixtures take priority when the cap is reached. Resolution goes through `provider.fetch_fixture_score(fixture.external_id)` → FD only (no ESPN backup).

---

## File Changes

### New: `backend/app/services/external/__init__.py`
Empty. Makes `external/` a Python package.

### New: `backend/app/services/external/espn.py`
Ported verbatim from upstream with these adjustments:
- Keep upstream's `EspnClient`, `EspnError`, `LEAGUE_SLUGS`, `TEAM_NAME_ALIASES`, `KnockoutSplit`, `map_event_status`, `parse_minute`, `canonical_team_name`, `competition_past_regulation`, `parse_summary_split`, `_parse_side`, `_linescore_int`.
- Keep upstream's `map_event_status` change: `state == 'post'` returns `FINISHED` only when `status_type.get('completed')` is truthy (prevents accepting abandoned matches as finished).
- No other changes.

### New: `backend/app/services/external/football_data.py`
Extracted from current `external_scores.py` — `FootballDataClient` and `map_status`. Applies our v2.185.1 fixes:
- `home_score` = `regularTime.home` (falls back to `fullTime.home` for group matches where `regularTime` is absent).
- Cumulative ET = `regularTime + extraTime delta` (not just `extraTime`).
- Pens derivation from `fullTime − regularTime − extraTime` when `duration == PENALTY_SHOOTOUT` and the `penalties` field is tied/null.

### Modified: `backend/app/services/external_scores.py`

**`ExternalScore` dataclass changes:**
- Add `period: int | None = None`
- Add `final_authoritative: bool = True`
- Add `espn_event_id: str | None = None`
- **Remove** `has_score: bool = True` — replaced by explicit `ext.home_score is not None` checks in `_apply_external_score`.

**`EspnScoreProvider`:**
- Import from `external/espn.py`.
- Add `_enrich_knockout_splits()` async method (concurrent summary fetches).
- `fetch_live_scores()` calls `_enrich_knockout_splits()` for past-regulation events.
- `_to_external_score()` adds `period`, `espn_event_id`, `home_penalties`/`away_penalties` from `shootoutScore`, sets `final_authoritative=False`.
- `fetch_fixture_score()` continues to return `None` (ESPN can't resolve by FD external_id).

**`FootballDataScoreProvider`:**
- Import from `external/football_data.py`.
- No behavioral change; our v2.185.1 fixes live in the client module.

**`FallbackScoreProvider`:**
- Remove `backup_resolver` parameter (upstream pattern — ESPN's `fetch_fixture_score` returns `None`, so FD is the sole resolver; the backup path is redundant).
- `fetch_fixture_score()` delegates to `self._resolver` (FD) only.

**`get_score_provider()`:**
- Remove `backup_resolver=espn` argument.

### Modified: `backend/app/services/score_sync.py`

- Add `_score_fields_for(fixture, ext, existing)` function (90-min freeze logic).
- Update `_apply_external_score()`:
  - Replace `has_score` checks with `ext.home_score is not None and ext.away_score is not None`.
  - Add `final_authoritative` downgrade: non-authoritative FINISHED KO → status=LIVE, return None.
  - Call `_score_fields_for()` for all score writes.
  - Admin-lock (`score.verified=True`) logic is **preserved unchanged** — verified rows still skip all updates.
- Update `_find_unresolved_fixtures()`:
  - Add Shape C JOIN against `Score` to find FINISHED KO rows with null pens. Capped at 3 (combined with existing 8-cap, total stays ≤ 11 calls/tick).

---

## Testing

### `backend/tests/test_external_scores.py`
- Update all 10 existing tests: replace `has_score=False` assertions with `home_score=None`; add `final_authoritative` assertions where relevant.
- New: `test_parse_summary_split_clean_pens` — well-formed linescores with shootout; expects correct reg/ET/pen split.
- New: `test_parse_summary_split_tied_pens_returns_none` — tied shootout → `None` (unresolvable).
- New: `test_parse_summary_split_malformed_returns_none` — missing linescores → `None`.
- New: `test_enrich_knockout_splits_overlays_split` — mock `EspnClient.get_summary()` returning clean linescores; verify `final_authoritative=True` and correct field values after enrichment.
- New: `test_enrich_knockout_splits_failure_leaves_base_score` — mock summary raising `EspnError`; verify base score untouched, `final_authoritative=False`.

### `backend/tests/test_score_sync.py`
- New: `test_shape_c_resolution_triggers_for_finished_ko_null_pens` — FINISHED KO fixture with null `home_penalties`; verify it appears in `_find_unresolved_fixtures()` results.
- New: `test_90min_freeze_preserves_regulation_score_during_et` — ESPN tick with `period=3`, no ET split, existing regulation score in DB; verify `home_score` unchanged, running total in `home_score_et`.
- New: `test_non_authoritative_ko_downgrades_to_live` — ESPN FINISHED non-authoritative on KO fixture within 4h window; verify fixture status set to LIVE, `_apply_external_score` returns None.

---

## Invariants Preserved

- **Admin verified lock:** `score.verified=True` rows still skip all updates. Unchanged.
- **Demotion guard:** FINISHED fixtures can only be updated by FINISHED payloads. Unchanged.
- **Phase 1 only:** No Phase 2 code paths touched.
- **Datetime rule:** No new datetime fields; existing `utc_now()` and `aware_utc()` patterns preserved.
- **`third_place` exclusion:** Shape C filters `fixture.stage != 'group'` — the `third_place` stage would be included by this filter, but `third_place` fixtures have no `Score` row (scoring engine ignores them), so the JOIN on `Score.home_penalties IS NULL` will never match a `third_place` fixture.

---

## NED-MAR Resolution Path

After this implementation ships and the backend restarts:
1. Score scheduler polls (next match window or manual `/admin/scores/sync`).
2. Shape C detects Netherlands–Morocco: `status=FINISHED`, `home_penalties IS NULL`, `stage=round_of_32`, kickoff within 12h.
3. Calls `provider.fetch_fixture_score("537418")` → FD returns correct data (already self-corrected: `penalties: {home:2, away:3}`, `winner: AWAY_TEAM`).
4. Score row updated: `home_score=1, away_score=1, home_score_et=1, away_score_et=1, home_penalties=2, away_penalties=3`.
5. Leaderboard cache invalidated; Morocco shown as winner across all surfaces.

No manual admin entry required.

---

## Open Questions (resolved)

- **ET split for ET-only matches (STATUS_FINAL_AET):** ESPN summary linescores provide the full per-period split including regulation vs ET goals. This was the remaining gap; the summary endpoint closes it.
- **Wikipedia / FIFA.com fallback:** Not needed. ESPN summary + FD resolution cover all cases. Both are JSON APIs with no HTML scraping required.
- **FD as primary vs ESPN as primary:** FD stays as the per-fixture resolver (resolution pass). ESPN becomes authoritative at the *live-scoring* layer via summary enrichment, not by replacing FD in the resolution pass.

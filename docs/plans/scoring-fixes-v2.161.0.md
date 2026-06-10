# Scoring System Fixes — v2.161.0 Implementation Plan

Branch: `claude/scoring-system-review-pp98pc`. Alembic head at planning time:
`9a1b2c3d4e5f`. Upstream reference: clone with
`git clone --depth 1 https://github.com/laarohi/predictorv2 /tmp/upstream`
(Steps 4 and 6 port code from it).

> **Handover note.** This plan was produced by a full scoring-system review
> in a prior Claude Code session (2026-06-10) and approved by the project
> owner. It is ready to implement as written — Steps 1–9 in order. The
> review compared this fork against upstream `laarohi/predictorv2`, which
> already fixed the critical bug below. Target version **2.161.0**. Must
> deploy **before the Round of 32 finishes** (knockout results are when the
> bug becomes visible and irreversible on the leaderboard). First group
> kickoff is June 11 — the rarity-eligibility change should also land
> before the first fixture finishes. Do not create a PR; commit and push
> to this branch. Delete this file in the final version-bump commit (or
> keep it — owner's call).

## Context

A full scoring review found that **quarter-final and semi-final bracket
picks score 0 points**: the frontend stores `TeamPrediction.stage` as
`quarter_finals`/`semi_finals` (plural) while the scoring engine
(`scoring.py:342-357`), YAML keys, fixture stages, bracket-exposure widget,
and email recap all use singular. Verified impact: a perfect champion pick
pays 245 instead of 315; up to 520 pts/entry never paid. Production rows
are plural (submit validation requires it), so a data migration is needed.
Upstream fixed this exact bug by storing singular.

Also being fixed (all owner-approved): the leaderboard's
O(entries × fixtures) cold rebuild (~7,200 queries by end of group stage;
no single-flight lock → thundering herd with ~50 concurrent users),
unauthenticated cache-control endpoints, rarity denominators counting
draft/withdrawn/disabled entries, the upstream scoring-parity harness
(pytest + Vitest golden cases), and stale docs/config values.

**Confirmed product decision (owner, 2026-06-10):** the rarity bonus must
count **only eligible entries** — at least one SUBMITTED phase,
`is_disabled = false`, `withdrawn_at IS NULL` (same predicate as
`leaderboard._list_eligible_entries`). This is a requirement, not an
optional optimization; it ships in Step 4a/4b and is asserted by Step 8
test #2. Consequences (retroactive, reversible, non-payment interaction)
are documented under Risks/notes.

---

## Step 1 — Canonical stage map + backend write-path normalization

**1a. `backend/app/models/prediction.py`** (next to `TeamPrediction`, ~line 68):

```python
# Canonical TeamPrediction.stage values are SINGULAR ("quarter_final",
# "semi_final"), matching Fixture.stage (fixture_sync._STAGE_MAP) and the
# scoring.advancement YAML keys. Plural spellings are accepted defensively
# on write (stale cached frontend bundles) and normalized before storage.
STAGE_ALIASES: dict[str, str] = {
    "quarter_finals": "quarter_final",
    "semi_finals": "semi_final",
}

def normalize_stage(stage: str) -> str:
    return STAGE_ALIASES.get(stage, stage)
```

**1b. `backend/app/services/predictions.py` — `replace_bracket_predictions`
(366-442):** normalize `stage = normalize_stage(pick.get("stage") or "")`
AND de-dupe on `(team, stage, group_position)` via a `seen` set before
insert — a payload containing both spellings for the same team would
otherwise hit the `uq_team_pred_entry_phase_team_stage` unique constraint
after normalization. Audit `picks_summary` reads from `new_rows`, so it
records normalized values automatically.

**1c. `backend/app/services/entries.py` — submit validation:**
`expected_counts` (768-769) → `"quarter_final": 8, "semi_final": 4`;
`stage_order` (790-791) → singular; fix the comment at :707. Bucket via
`normalize_stage(tp.stage)` at :762 for read-side defense.

**1d. `backend/app/api/entry_predictions.py` — `_organize_bracket`
(273-303):** stages dict keys become singular; map back to the **unchanged
plural response fields** (`BracketPrediction.quarter_finals =
stages["quarter_final"]`, etc. — mirror
`/tmp/upstream/backend/app/api/predictions.py:459-489`). Route row lookups
through `normalize_stage()`. The API schema
(`backend/app/schemas/prediction.py:66-74`) and all frontend types keep
plural **field names** — only stored stage **values** change. This also
fixes the admin slide-over: `backend/app/api/admin.py:1032` imports
`_organize_bracket`.

**1e. `entry_recap.py`** — no change; already singular, QF/SF reappear in
confirmation emails once rows are singular.

## Step 2 — Frontend writes singular

**2a. `frontend/src/routes/entries/[entryId]/+page.svelte` —
`bracketToPredictions` (1401-1414):** `push('quarter_final',
b.quarter_finals); push('semi_final', b.semi_finals);` + upstream's
explanatory comment (singular stored values, plural display fields).
`makeEmptyBracket` keys stay plural (they're `BracketPrediction` fields).

**2b. `frontend/src/routes/profile/[userId]/+page.svelte`:**
`bracket_summary.stages` from `backend/app/api/users.py:218-226` is keyed
by RAW stored values → becomes singular after migration.
`stageLabels`/`stageMaxWidth` (55-77) already have both spellings;
**`stageOrder` (line 54) is plural-only** — add singular entries (keep
both, order-stable).

No other frontend consumer reads raw stage values (verified:
EntryRecapBody, EntryDetailSlideOver, KnockoutBracket, bracketResolver,
smartFill, bracketConfig all use the plural response fields / internal
round codes).

## Step 3 — Alembic data migration

New revision `down_revision = "9a1b2c3d4e5f"`, pattern per
`8d9e0f1a2b66_simplify_entry_lifecycle.py`. For each (plural, singular)
pair:

1. Guard DELETE of plural rows that would collide with an existing
   singular row for the same (entry_id, phase, team) — protects the unique
   constraint.
2. `UPDATE team_predictions SET stage = '<singular>' WHERE stage = '<plural>'`.

Downgrade reverses the UPDATEs. Docstring notes: plain String column (no
enum swap); audit-event metadata intentionally not rewritten; **tests use
`create_all`, not migrations — manual verification required** (Verification
section below). Startup auto-runs `alembic upgrade head`
(`database.py:init_db`), so deploy order is safe.

## Step 4 — Performance: batched outcome counts + single-flight leaderboard

Port `/tmp/upstream/backend/app/services/{scoring,leaderboard}.py`
patterns, adapted user_id → entry_id.

**4a. `scoring.py` — eligibility helper** `eligible_entry_ids_select()`
(not disabled, not withdrawn, ≥1 SUBMITTED phase — same predicate as
`leaderboard._list_eligible_entries`). **Delete dead
`_count_eligible_entries` (490-505)** — no callers.

**4b. `scoring.py` — `get_all_outcome_counts(session)`** →
`dict[fixture_id, {"1","X","2"}]` in ONE query: column projection
`select(MatchPrediction.fixture_id, home_score, away_score)
.where(MatchPrediction.entry_id.in_(eligible_entry_ids_select()))`,
aggregate outcome in Python. **This applies the confirmed
rarity-eligibility decision** — only eligible entries' predictions count
toward rarity numerators and denominators. **Delete per-fixture
`get_outcome_counts` (641-659)** — sole caller was :553 (confirm
`services/__init__.py` re-exports before deleting).

**4c. `scoring.py` — `calculate_entry_points`** gains keyword-only
`outcome_counts_by_fixture=None, actual_advancement=None`; when omitted,
compute each ONCE per call. Existing positional callers
(`api/leaderboard.py:185`, `profile.py:69`) unchanged and drop from ~104
queries to ~3.

**4d. `leaderboard.py`:** precompute both caches once per rebuild, pass
per entry; **drop the redundant `get_entry_match_stats` call and delete
the function (66-96)** — read
`breakdown.correct_outcomes`/`breakdown.exact_scores` instead (fields
verified equivalent). Add single-flight: per-cache-key `asyncio.Lock`
(`_lock_for(cache_key)`, port upstream leaderboard.py:46-67) — fast-path
cache check → lock → re-check → rebuild. 30s TTL unchanged.

**4e. `predictions.py` — `compute_agreements` (:551):** apply the same
`eligible_entry_ids_select()` filter so the Results-card rarity
*projection* matches what scoring actually pays (verified drift risk).

## Step 5 — Security: admin-gate cache controls

`backend/app/api/leaderboard.py`:

- `POST /invalidate` (156-163): add `_admin: AdminUser` (import from
  `app.dependencies`, alias :115; pattern `api/admin.py:150-151`).
- `GET /` (112-153): `force = bool(refresh and user is not None and
  user.is_admin)`; docstring updated.

Verified safe: no frontend code calls either; internal callers use the
service function `invalidate_cache()` directly.

## Step 6 — Scoring parity harness (port from upstream)

**6a. `scoring.py`:** add `_outcome()` + pure `compute_match_points(*,
mode, predicted_home, predicted_away, actual_home, actual_away,
total_predictors, correct_predictors, outcome_points, exact_points, cap)`
(verbatim from `/tmp/upstream/backend/app/services/scoring.py:203-257`);
refactor `FixedScoring`/`HybridScoring`/`LogarithmicScoring.calculate()`
to delegate (hybrid passes `cap=config.get("hybrid_cap", 10)`). Protocol
signature unchanged; existing `test_scoring.py` must pass unmodified.

**6b. `shared/scoring-parity-cases.json`:** copy verbatim from
`/tmp/upstream/shared/` (11 cases).

**6c. `frontend/src/lib/utils/matchBreakdown.ts`:** port upstream's
`computeMatchPoints` (upstream matchBreakdown.ts:101-132; fix the
`/ mode 'fixed'` comment typo) and rewire `computeBreakdown`'s earned/live
`totalPts` (this fork's lines 207, 220) through it so the parity-tested
path IS the production path. Leave the potential/upcoming branch as-is.

**6d. Tests:** port `backend/tests/test_scoring_parity.py` (parent-walk
file finder) and `frontend/src/lib/utils/matchBreakdown.parity.test.ts`
(Node `readFileSync` parent-walk — no Vitest config change needed;
verified `bracketResolver.test.ts` runs under defaults).

**6e. `docker-compose.yml`:** mount `- ./shared:/app/shared:ro` into BOTH
`backend` (volumes ~lines 48-54) and `frontend-dev` (~line 125), mirroring
upstream compose, so the parent-walk resolves in containers.

## Step 7 — Docs/config sync

- `scoring.py:38-47` `DEFAULT_SCORING_CONFIG.advancement` →
  20/30/40/50/75/100 (sync to `config/worldcup2026.yml:65-70`).
- `scoring.py:271` fallback `"hybrid"` → `"logarithmic"`.
- `docs/scoring-system.md`: three stale advancement blocks (~34-42,
  ~185-193, ~327-335) → 20/30/40/50/75/100.
- `bracket_exposure.py`: `PICKS_PER_STAGE_PHASE_1` → `{round_of_32: 32,
  round_of_16: 16, quarter_final: 8, semi_final: 4, final: 2, winner: 1}`
  (teams-reaching-stage semantics, total 63) + docstring rewrite. Zero
  blast radius — frontend never calls `getBracketExposure` yet (verified;
  dashboard uses the stub fallback).
- `CLAUDE.md`: add invariant under Scoring — stage values are SINGULAR;
  plurals exist only as `BracketPrediction` field names;
  `normalize_stage()` is the write guard.
- `docs/functional-codebase-overview.md:599`: update the existing
  mismatch warning to "resolved".

## Step 8 — Tests

New:

1. `backend/tests/test_bracket_stage_normalization.py` — payload with BOTH
   spellings → stored singular, de-duped; champion-chain + finished
   knockout fixtures → `calculate_advancement_points` pays 40/50 and
   `calculate_entry_points` buckets into
   `quarter_final_points`/`semi_final_points` (reuse
   `_fixed_scoring_config` fixture pattern from
   `test_entry_scoring.py:46-67`); `_organize_bracket` singular→plural
   mapping; submit validation accepts all-singular bracket, rejects
   missing-QF.
2. `backend/tests/test_leaderboard_perf.py` — `get_all_outcome_counts` ==
   manual per-fixture counts; **excludes draft/withdrawn/disabled entries'
   predictions** (the confirmed rarity-eligibility requirement);
   `calculate_entry_points` with vs without caches identical
   (`model_dump()` compare); leaderboard rows carry correct
   `correct_outcomes`/`exact_scores`; single-flight (gather N concurrent
   cold calls, assert one rebuild — patch a counter; share the session
   factory).
3. `backend/tests/test_leaderboard_admin_gate.py` (or extend
   `test_leaderboard_visibility.py`, which has the ASGITransport
   scaffolding) — invalidate: 401 unauth / 403 non-admin / 200 admin;
   `?refresh=true` ignored for non-admin (stale cache stays), honoured for
   admin.
4. `backend/tests/test_bracket_exposure.py` — 63-row singular bracket →
   `picks_total == 63`, `points_available == 1890` under patched config
   (reference `/tmp/upstream/backend/tests/test_bracket_exposure.py`,
   adapt user→entry).
5. Parity tests (Step 6d).

Edits: `test_entries_service.py:563` + comment :544 → singular;
`test_users_api.py:142,146` → singular. `test_entry_scoring.py` must pass
unmodified.

Gotchas: aiosqlite tzinfo rule (nothing new returns datetimes here);
`npm run check` must stay 0 errors.

## Step 9 — Version + changelog + commits

- Bump 2.160.0 → **2.161.0** in `frontend/package.json`,
  `frontend/package-lock.json` (top-level AND `packages[""]`),
  `backend/pyproject.toml`.
- Append to END of `entries` in `frontend/src/lib/data/changelog.json`:
  `{ "version": "2.161.0", "date": "<today>", "type": "fix", "summary":
  "Knockout-bracket picks for the quarter-finals and semi-finals now score
  correctly — a naming mismatch meant those rounds were silently worth 0
  points. Submission-recap emails include those rounds again. Leaderboard
  loads are much faster under load, only submitted entries count toward
  the rarity-bonus maths, and leaderboard cache controls are admin-only.",
  "commit": "pending" }`.
- Feature commits first, then `chore(version): bump to 2.161.0`. Push
  `-u origin claude/scoring-system-review-pp98pc`.

## Verification

1. `docker-compose exec -T backend pytest tests/ -v` (worktree-overlay
   pattern per CLAUDE.md if in a Claude worktree) — green.
2. `docker-compose exec -T frontend-dev npm run check` — 0 errors;
   `npx vitest run` — green incl. parity.
3. Migration dry-run on dev Postgres: `alembic heads` (single head),
   `alembic upgrade head`, `SELECT stage, COUNT(*) FROM team_predictions
   GROUP BY stage` → no plurals; `downgrade -1` + re-upgrade round-trips.
   **The only gate for the migration — tests don't run Alembic.**
4. API spot-checks: entry bracket GET returns populated
   `quarter_finals`/`semi_finals`; stale-bundle simulation (PUT bracket
   with plural stages via curl → stored singular);
   `POST /leaderboard/invalidate` unauth → 401.
5. Pre-deploy: `pg_dump` of prod first (insurance for the data
   migration); deploy per CLAUDE.md; grep compose output for
   `Conflict. The container name`.

## Risks / notes

- **Decided & out of scope (owner, 2026-06-10):** advancement "reached
  stage" timing stays results-based — R32 points pay when each R32 fixture
  is FINISHED, not when the lineup is published. (Tie-breaks are
  inherently safe: the app never computes group qualification; it scores
  against the named knockout fixtures synced from Football-Data, which
  reflect FIFA's official tie-break outcomes. Admin can override fixture
  teams via `PUT /api/fixtures/{id}` if the API lags.) Do NOT change
  `get_actual_advancement`'s `FINISHED` filter in this release.
- Unique-constraint collisions on normalize → handled by migration guard
  DELETE + service de-dupe (Step 1b/3).
- `bracket_summary` keys flip to singular on the public profile API →
  handled in Step 2b.
- Old audit events keep plural stage strings (historical, intentional —
  note in migration docstring).
- Rarity-eligibility change can shift displayed bonuses the moment it
  deploys — harmless while no fixture has finished; ship before kickoff
  (June 11).
- **Non-payment removals interact with rarity (by design):**
  disabling/withdrawing an entry now removes its predictions from rarity
  denominators on the next rebuild — retroactive (scores recompute from
  raw predictions; no frozen ledger) and reversible (predictions never
  deleted; re-enabling restores everything). Advise admin to do non-payer
  removals BEFORE the first fixture finishes to avoid visible ±1 bonus
  shifts mid-competition.
- Per-process leaderboard cache assumes a single backend worker (true
  today) — keep the upstream NOTE comment when porting the lock.

# Tournament Conclusion — Backend, Announce & Audit (Sub-project A)

**Date:** 2026-07-18 · **Status:** approved design, pending implementation
**Companions:** `2026-07-18-compare-page-design.md` (B), `2026-07-18-wrapup-page-design.md` (C)
**Deadline context:** the WC26 final is Sun 19 Jul 2026. A + C are launch-critical;
everything ships **admin-gated** and the admin releases when ready (likely Sunday
night), with the broadcast sent Monday.

## Goal

Give the competition a proper ending: a `tournament_concluded` end-state that the
whole app can key off, a champion/Trionda announcement service, a pool-retrospective
aggregate, an on-demand full-rescore audit, and a short final broadcast. This spec
covers backend + email + admin controls; the user-facing page is Sub-project C.

## 1. The conclusion flag

- New column `Competition.tournament_concluded: bool`, server default `false`
  (Alembic migration; same family as `post_deadline_live`,
  `group_stage_winner_released`).
- Surfaced on `PhaseStatus` as `tournament_concluded` (and everything the
  frontend needs keys off phase-status — no new polling).
- Admin toggle on `/admin`, "Tournament conclusion" section, mirroring the GSW
  release UI (`setGroupStageWinnerReleased` pattern: API wrapper in
  `frontend/src/lib/api/admin.ts`, handler + confirm dialog in
  `frontend/src/routes/admin/+page.svelte`). The confirm dialog lists ALL
  effects (below) and **warns if no final-audit artifact exists yet**.
  Retractable (flip back = full rollback, nothing destructive).

**One flag flips everything:**
1. `/` dispatcher switches everyone to the wrap-up page (C).
2. Wrap-up data endpoints become publicly readable (§6).
3. TOURNAMENT_FINAL broadcast tokens unlock (§5).
4. Leaderboard surfaces show a 🏁 "Final standings" pill; live-projection
   overlay is suppressed; frontend live polling (`livePoll.ts` callers) does
   not start; countdown/deadline chrome stays retired.
5. `SiteNoticeBanner` re-arms with a new `NOTICE_ID`
   (`2026-07-19-wrapup`) and wrap-up copy funnelling inner pages to `/`.

## 2. Champion / final-podium service

`backend/app/services/tournament_champion.py`, endpoint
`GET /api/leaderboard/final-podium`.

Service is **ungated** (GSW precedent — the gate lives at the API layer:
`tournament_concluded OR current_user.is_admin`, so the admin preview works
pre-flip).

Payload:
- `podium`: top 3 of the FINAL leaderboard (live board order — totals are final
  once all fixtures are FINISHED). Per entry: name (via `rowDisplayName`
  convention), final_rank, total, group/knockout/bonus split
  (from `breakdown.phase1` + bonus fields — no new math), champion_pick +
  champion_hit, exact_scores, rarity points (`hybrid_bonus_points`),
  days_at_top (COUNT of snapshot dates at position 1 — GSW pattern), prize
  (€595 champion; **ties share** per the rules page — joint champions are all
  flagged `is_champion`, prize string rendered accordingly).
- `story_line`: server-composed narrative (pure helpers, GSW style) so page
  and email agree.
- `trionda`: the side-prize block (§3).
- `final_match`: the Final fixture's result (teams, score, ET/pens flags,
  kickoff, venue string) + `final_match_narrative` (§4).
- `audit`: summary block from the latest audit artifact (§7), or `null`.

## 3. Trionda ball recipient (side prize)

Per [rules/+page.svelte:335](../../frontend/src/routes/rules/+page.svelte):
runner-up on total points; entries that **won or shared the group-stage cash**
are ineligible; skip down to the next eligible entry; ties at the landing rank
break on group-stage points; a persisting tie is drawn by lots.

Algorithm in `tournament_champion.py`:
1. Ineligible set = every eligible entry whose group-stage total equals the
   maximum group-stage total. Group-stage total MUST reuse the GSW definition —
   extract `_group_stage_total` from `group_stage_winner.py` into a shared
   helper (one canonical resolver; read-time-consistency rule).
2. Runner-up rank = first rank strictly below the champion(s). Walk final
   standings from there downward, skipping ineligible entries.
3. Multiple eligible entries tied at the landing rank → higher group-stage
   points wins. Still tied → return `requires_draw: true` + candidate list;
   the page renders "draw pending between X and Y" (defensive state only —
   logarithmic rarity decimals make exact total ties near-impossible).
4. Payload: `{recipient, final_rank, reason}` where `reason` is a short factual
   label ("runner-up on total points" / "moved down from #2 — group-stage
   champion not eligible"), never derived prose beyond these fixed templates.

## 4. Final-match narrative

- New nullable column `Competition.final_match_narrative: text`.
- Editable from the `/admin` conclusion section (plain textarea + save), so the
  admin writes the match story minutes after full time with **no deploy**.
- Served in the final-podium payload; the wrap-up page renders it under the
  scoreline. Empty → the card shows the result without a story.

## 5. TOURNAMENT_FINAL broadcast

New `BroadcastSegment.TOURNAMENT_FINAL` — audience =
`_has_submitted_phase_predicate` (same as every recap). Wiring per the
established recipe (enum + `_broadcast_content_for_segment` branch +
`SEGMENT_LABELS` + `admin.ts` union + counts interface).

**Deliberately short.** Body: champion one-liner
(`{{CHAMPION_NAME}}`, `{{CHAMPION_TOTAL}}`), one CTA to the homepage
("See the final story"), one feedback ask ("rating + feedback box on the
homepage — 30 seconds"). NO per-recipient rank, NO UTM, no spam-trigger word
pairs, no verification detail, no prize amounts (the page carries all of
that). Token compute gated on `tournament_concluded` (GSW pattern: pre-flip test-send
shows literal `{{TOKEN}}` placeholders as the defensive signal). Regression
test pins full interpolation (no `{TOKEN}`/`{{TOKEN}}` leakage — the
f-string double-brace class).

Send timing is operational (admin sends Monday); nothing in code cares.

## 6. Public access when concluded

The wrap-up page is **fully public post-conclusion** (staff-forward audience).
Gate shape on each endpoint: `tournament_concluded OR authenticated` (anonymous
allowed only once concluded; before that, behavior unchanged). Endpoints:

- `GET /api/leaderboard/` (banked board; live projection is moot)
- `GET /api/leaderboard/final-podium` (new; also `OR is_admin` pre-flip)
- `GET /api/leaderboard/pool-retrospective` (new, §8; same gate)
- `GET /api/leaderboard/scoring-rules`, `GET /api/competition/phase-status`
  (already public or harmless — verify)
- `/rules` verification anchor (§7) — /rules is a public route already.

NOT public: per-entry prediction detail, /compare data, feedback POST — all
stay auth-required. Guests see aggregates and names only (same disclosure as
the public Google Sheet precedent). The wrap-up page carries
`<meta name="robots" content="noindex">` (C).

## 7. Full-rescore audit — on-demand admin button

- Extend `scripts/audit_top3_v2.py` into a service-callable full audit
  (`backend/app/services/final_audit.py`): independently re-score **every
  match, every bracket advancement credit, and all 4 bonus questions for every
  eligible entry**, reading only immutable inputs (deadline-night predictions
  snapshot committed in `backend/snapshots/`, DB modification log, official
  results). Compare recomputed totals against the live leaderboard; report
  per-entry discrepancies.
- `POST /api/admin/audit/run` (admin-only) launches it as a background task;
  `GET /api/admin/audit/status` polls; result written to
  `backend/snapshots/final-audit-<UTC date>.json`
  (`{run_at, entries_verified, matches_rescored, bonus_questions,
  discrepancies: [...], sources: [...]}`) — re-runnable at any time, latest
  artifact wins.
- `/admin` conclusion section gets a **"Run audit"** button + last-run summary.
- `/rules` section 06 gains an anchored `#verification` block, rendered from
  the served audit summary (real numbers, not boilerplate): "All 104 matches …
  re-scored for all 183 entries … 0 discrepancies", plus the four immutable
  sources. Pre-conclusion (or artifact missing): block hidden / sources-only.
  The wrap-up hero's "✓ Verified result — how this was checked →" pill links
  here.
- **Dress rehearsal is part of implementation**: run the audit against current
  prod data during development; first production run must not be finals night.

## 8. Pool-retrospective aggregate

`GET /api/leaderboard/pool-retrospective` — ONE aggregation pass over all
predictions + results (avoids 104 per-fixture community fetches). Gate as §6.
Cache aggressively (data frozen once concluded; simple in-process cache keyed
on flag + latest fixture update). `third_place` excluded everywhere
(unscored-stage invariant). Returns:

- `group_hit_rate`: {called_right, total} — pool majority outcome pick vs
  result per group fixture.
- `final_called_right`: {pct, winner_team} — share of entries whose champion
  pick was the actual winner.
- `exact_scores`: {total, avg_per_entry}.
- `misses`: top 3 results with the LOWEST share of correct outcome picks
  (match label, pct, why-line data).
- `bankers`: top 3 with the HIGHEST share (plus exact-count).
- `ko_ladder`: per KO stage {stage, consensus_had, of, fallen_teams[]} —
  consensus lineup (Consensus-Bracket team counts) vs
  `get_actual_advancement`; plus a `winner` row (consensus champion vs actual).
- `bonus`: per question {label, answer_label, hit_pct} (answers from the
  settled bonus scoring).
- `champion_distribution`: top 5 picked teams + counts, actual flagged.
- `personal` (auth only, per requesting user's entries): final rank, splits,
  and **superlatives** — computed in the same pass (see C spec §Your
  tournament for the catalog). Anonymous callers get `personal: null`.

## 9. Analytics

New backend-relevant events in `ALLOWED_EVENTS` where server-fired; frontend
events enumerated in spec C. `FEATURE_GROUPS` additions (per the /admin/usage
rule): "Wrap-up page" (`wrapup_viewed` + click events), "Compare"
(`compare_opened`, from B). Mark neither `frozen` (post-tournament is their
live phase).

## 10. Tests (pytest, required)

- Podium: top-3 shape, shared-champion tie, prize labelling.
- Trionda: direct runner-up; GSW-winner-at-#2 skip; all-of-rank-ineligible
  walk-down; tie broken on group points; persisting tie → requires_draw.
- Shared `_group_stage_total` helper: GSW service and champion service agree
  (regression pin).
- Retrospective: hit-rate math against a seeded fixture set; third_place
  excluded; misses/bankers ordering; ko_ladder vs actual advancement; personal
  superlatives present for auth user, null anonymous.
- Gating: anonymous 401/403 pre-flip on every §6 endpoint, 200 post-flip;
  admin 200 pre-flip on final-podium/retrospective.
- Broadcast: token interpolation regression (no literal token leakage);
  audience = submitters.
- Audit: runner produces artifact; status endpoint; 0-discrepancy happy path
  and injected-discrepancy detection.
- Full backend suite after the migration (schema-drift rule).

## Out of scope (deliberate)

- No changes to scoring, snapshots, score_sync (scheduler already
  self-quiesces via `has_active_or_imminent_match`).
- No Phase 2 anything.
- No automated draw-by-lots; no per-recipient email personalization.
- Prize-figure reconciliation (€137/€500/€650 wording) happens at
  implementation against the rules page; the Atlas card copy avoids stating a
  summed total.

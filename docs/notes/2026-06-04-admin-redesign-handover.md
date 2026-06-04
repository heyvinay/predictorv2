# Admin redesign — handover for next session (2026-06-04)

## TL;DR

**v2.156.0 + v2.156.1 are pushed to `origin/main` but v2.156.1 is NOT
yet deployed to production.** The first thing to do next session is
run the deploy from a terminal where the SSH key works:

```bash
ssh root@167.235.145.76 "cd /opt/predictor && git pull && docker compose --profile prod up -d --build"
```

Then verify at https://wc26.heyvinay.com/admin/entries that the stats
strip shows real counts (Submitted with `X drafts pending` underneath,
non-zero Paid count, etc.).

After that, attack the deferred items in **Task #22** below.

---

## What shipped (commits in order)

```
fb06bcd  chore(version): bump to 2.156.1
e64a770  fix(admin): entries page stats now correct + per-row status differentiated
c3eb6cc  fix(admin): replace duplicate sub-header with pageTitle store
1c3cb24  fix(admin): test failures (SQLite tzinfo) + type-check errors (H1 + H2)
7e08b91  feat(admin): slide-over restructure (E1, E2, E3) — summary in header, audit last
288141a  fix(admin): sub-nav active tab now updates on navigation
6a3ee27  fix(admin): user-detail sparkline compile error — move {@const} hoist into script
28e22c3  fix(admin): dev-review feedback batch 1 — UX fixes + user-detail completeness
30b3e4f  test: merge v2.156.0 admin redesign into main for dev verification
49b0861  chore(version): bump to 2.156.0
c0f9bb8  feat(admin): v2.156.0 redesign — cohort filtering, audit feed, engagement card
```

**v2.156.0 (feature)** brought:
- New `/admin/users` with three-cohort filtering (Active /
  Signed-up-only / Verified-only) and "Email Inactive" CSV export
- New `/admin/users/[id]` drill-down with KPI strip, PostHog
  Engagement card (last seen / sessions / 14-day sparkline),
  Entries grid, Permissions panel, Danger zone, Activity log
  with filters
- New `/admin/audit` global feed with day separators, namespace
  chips, free-text search, pagination
- New `/admin/entries` reconciliation table + `EntryDetailSlideOver`
  component with restructured tabs (Group / Knockout / Bonus /
  Audit log) and reason-required Pattern C confirmation modal
- Backend: `query_audit_events`, `last_login_for_users`,
  `last_activity_for_users`, `list_users_with_cohort`,
  `list_inactive_emails`, `posthog_read` service, audit additions
  in `verify_magic_link` + `update_current_user`
- pageTitle-store integration: global top nav shows
  "Admin Console v2.156.1 · 9 Jun 2026" on admin pages

**v2.156.1 (fix)** brought:
- Entries page Submitted count now uses Phase 1 actual status (was
  `!is_disabled` which conflated drafts + submitted + withdrawn)
- Paid count honours per-user payment mode via `getPaidLocal`
  fallback (matches legacy /admin)
- Per-row status pill differentiates Draft / Submitted /
  Withdrawn / Disabled
- Submitted KPI card shows `X drafts pending` delta

---

## Verification state

- ✅ **58 of 58 backend tests pass** (`pytest tests/test_audit_query.py
  tests/test_admin_users_cohort.py tests/test_admin_entries_search.py
  tests/test_auth_audit_additions.py tests/test_posthog_read.py`)
- ✅ **`npm run check` reports 0 errors, 53 warnings (all pre-existing)**

---

## What's deferred (Task #22 — 15 items)

The substantial work still pending. These are documented but not
shipped. Each is "could be better" not "blocking" — they belong in
v2.156.2+ patches or v2.157.0 alongside the results/scoring work.

| Item | What |
|---|---|
| **B3** | Users CSV export — new backend endpoint `GET /admin/users.csv` + frontend Export button. Backend already has `list_users_with_cohort` to query; just need CSV streaming + frontend anchor. |
| **D1, D3** | Entries table — Owner + Paid to columns. Needs backend extension to join `User` into the `admin_list_entries` response (or add a parallel `enrichments` map keyed by entry id). |
| **D2** | Entries table — Completion column (X% with X/Y breakdown). The backend `get_completion_summary` exists but is scoped to the current user; needs an admin variant that accepts arbitrary entry ids. |
| **D4** | Entries table — Prize column (eligibility chip from `entry.prize_eligible`). Data already in the response; just needs UI. |
| **E1, E2, E3** | ✅ Already shipped in v2.156.0 (commit 7e08b91). |
| **F1, F2, F3** | Slide-over Group stage / Knockout / Bonus tabs render **real** prediction data. Currently show informative placeholders explaining what's coming. Needs an admin endpoint that returns an entry's `MatchPrediction` / `TeamPrediction` / `BonusPrediction` rows on behalf of another user. Heaviest single item. |
| **G2** | Bonus answers becomes its own tab on `/admin` (legacy 1310-line page). Currently inline within Configuration. |
| **G3** | Pattern C reason-required modal applied to existing /admin destructive actions (disable / withdraw / reinstate / paid toggle / prize toggle). Currently uses simple `confirm()` or inline dialogs. |
| **G4** | Expose all 11 entry settings on the existing /admin (only 6 visible today). Backend `EntrySettingsUpdate` already accepts the missing 5. |
| **H1, H2** | ✅ Already done in v2.156.0 — pytest + npm check both green. |
| **I1** | Duplicate the rich `/entries` player card markup into `/admin/users/[id]` so admins see the same card (completion %, predicted winner, status pill, group/bracket/bonus counts). Decision was: duplicate markup, do NOT extract to a shared component. Risk-averse. |

---

## Where things live

**Frontend admin code** (all in main checkout):
- `frontend/src/routes/admin/+layout.svelte` — guard + sub-nav + pageTitle store push
- `frontend/src/routes/admin/+page.svelte` — legacy 1310-line monolith (UNTRIMMED — G2/G3/G4 deferred)
- `frontend/src/routes/admin/users/+page.svelte` — three-cohort roster
- `frontend/src/routes/admin/users/[id]/+page.svelte` — user-detail
- `frontend/src/routes/admin/entries/+page.svelte` — reconciliation table
- `frontend/src/routes/admin/audit/+page.svelte` — global audit feed
- `frontend/src/lib/components/admin/EntryDetailSlideOver.svelte` — slide-over (shared)
- `frontend/src/lib/api/admin.ts` — extended with cohort + audit + engagement endpoints
- `frontend/src/app.css` — new `@layer components` for `.kpi-card`, `.status-pill`, `.confirm-modal`, etc.
- `frontend/tailwind.config.js` — new tokens: `primary-soft`, `primary-deep`, `base-150`, `base-250`

**Backend admin code:**
- `backend/app/services/audit.py` — reader (`query_audit_events`, `last_login_for_users`, `last_activity_for_users`) on top of the existing writer
- `backend/app/services/users.py` (NEW) — `list_users_with_cohort`, `list_inactive_emails`, auth-provider-aware cohort SQL
- `backend/app/services/posthog_read.py` (NEW) — generic HogQL read service with TTL cache
- `backend/app/services/entries.py` — `admin_list_entries` extended (name search + `modified_within` filter)
- `backend/app/api/admin.py` — new endpoints (`/audit`, `/users/list`, `/users/{id}`, `/users/{id}/engagement`, `/users/inactive`)
- `backend/app/api/auth.py` — surgical audit additions in `verify_magic_link` + `update_current_user`
- `backend/app/schemas/admin.py` (NEW) — `AuditEventRead`, `UserAdminPage`, `UserCohort`, `UserDetailRead`, `EngagementSummary`, etc.
- `backend/app/config.py` — added `posthog_personal_api_key` + `posthog_project_id` env vars

**Tests (5 new files):**
- `backend/tests/test_audit_query.py`
- `backend/tests/test_admin_users_cohort.py`
- `backend/tests/test_admin_entries_search.py` (extended)
- `backend/tests/test_auth_audit_additions.py`
- `backend/tests/test_posthog_read.py`

**Design artifacts:**
- `mockups/admin-redesign/` — 7 HTML mockup files + `_theme.css`, used to plan the redesign. Currently untracked in main.

**Plan file:**
- `C:\Users\vinay\.claude\plans\c-temp-admin-theme-css-c-temp-admin-aud-cosmic-pudding.md` — the originally-approved plan.

---

## Repo state at handover

- **`main` branch** is the production source. Last commit: `fb06bcd
  chore(version): bump to 2.156.1`. **Pushed to `origin/main`** (heyvinay
  fork). Has 11 commits since the pre-redesign HEAD (`995ee2c`).
- **`origin/main` ≡ `main`** — no unpushed commits.
- **`production` (the VPS at `/opt/predictor`)** is still on
  v2.156.0 — needs the `git pull && docker compose up -d --build`
  command to land v2.156.1. SSH from the Claude harness can't auth;
  user runs from their own terminal.
- **Worktree at `.claude/worktrees/gallant-mcclintock-79c63f`** is on
  branch `claude/gallant-mcclintock-79c63f`. That branch's history
  ends at v2.156.0 (commits `c0f9bb8 + 49b0861`). All subsequent
  fixes (28e22c3 → fb06bcd) went directly to main, NOT to this
  worktree. The worktree's `services/users.py` shows as modified but
  it's the same fix already in main — safe to ignore. The worktree
  is essentially "retired."
- **Pre-existing dirty files in main** (untouched by this session):
  `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `issues.md` (deleted),
  `BACKLOG.md`, `BUGS.md`, `Untitled.md`, `docs/notes/`,
  `docs/onboarding-design.md`, `mockups/`. These predate the session.
- **One git stash** worth noting: `stash@{0}: On main: pre-merge
  stash for v2.156.0 admin redesign test`. Contained `.gitignore` +
  `issues.md` changes that conflicted on pop. Safe to drop:
  `git stash drop stash@{0}`.

---

## Caveats to remember

1. **SSH from Claude harness fails** — `Permission denied (publickey,password)`.
   User must run prod deploys manually.
2. **OneDrive sync** had caused file-state drift mid-session, fixed
   by setting the project to "Always keep on this device." If similar
   issues recur, re-check that setting.
3. **Stale `.git/worktrees/*` directory references** show as
   "Permission denied" warnings during git commits. Cosmetic, not
   functional — commits succeed.
4. **PostHog Engagement card** is gated on env vars
   `POSTHOG_PERSONAL_API_KEY` + `POSTHOG_PROJECT_ID`. Currently
   UNSET on prod → card renders "—" placeholders (intentional
   graceful fallback). Set them when you want the live data.
5. **`get_user_detail` endpoint** uses `search=user.email` (substring)
   as a hack to derive the row via `list_users_with_cohort`. Works
   because emails are unique-constrained, but technically fragile.
   Flagged for future cleanup; not blocking.

---

## Suggested next-session order of operations

1. **Run the prod deploy** (one-liner above). Verify
   https://wc26.heyvinay.com/admin/entries stats look right.
2. **Decide Task #22 priorities.** Recommended:
   - D1 + D3 + D4 first (Entries table extra columns — needs a
     small backend join, biggest visible win, ~30-60 min)
   - F1 + F2 + F3 second (slide-over real content — needs new
     admin endpoint that returns an entry's predictions; ~60-90 min)
   - B3 third (CSV export — backend endpoint + frontend button;
     ~30 min)
   - G2 + G3 + G4 if time (touches the legacy 1310-line monolith;
     do these last; pair with a careful re-test of legacy /admin)
   - I1 anytime (just duplicate /entries card markup into
     user-detail page)
3. **Optionally drop the stale stash and worktree** if you want
   to clean up the local repo:
   - `git stash drop stash@{0}` (the pre-merge stash from this
     session)
   - `git worktree remove .claude/worktrees/gallant-mcclintock-79c63f
     --force` (if you're done with that branch)

---

## Handover prompt for the new session

Paste this verbatim to bootstrap the next session:

> Continuing the admin redesign work from 2026-06-04. The full
> handover is at `docs/notes/2026-06-04-admin-redesign-handover.md`
> — read it first. Current state:
>
> - v2.156.1 is pushed to `origin/main` but the prod VPS is still
>   on v2.156.0. **First step: I'll run the SSH deploy from my own
>   terminal then verify.** Don't try to SSH from your harness — it
>   doesn't have my key access.
> - After deploy verification, the deferred work is documented in
>   Task #22 (or the handover doc). Highest priority is **D1 + D3 +
>   D4** (Entries table Owner + Paid to + Prize columns — needs a
>   small backend `User` join in `admin_list_entries`'s response).
> - Read `CLAUDE.md` and the handover doc before any code changes.
> - Tests + type-check are green at start: `pytest tests/test_audit_query.py
>   tests/test_admin_users_cohort.py tests/test_admin_entries_search.py
>   tests/test_auth_audit_additions.py tests/test_posthog_read.py`
>   (58/58 pass) and `npm run check` (0 errors). Don't break them.
> - Mockups live in `mockups/admin-redesign/` (untracked but used
>   as the design spec).

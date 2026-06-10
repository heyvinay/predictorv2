# Next session handover — Leaderboard / Standings rebuild

> Paste this whole file into a new Claude session as the opening prompt
> (or summarise — the key bits are the **What I want** section + memory
> references). The agent should auto-load the memory referenced below.

---

## Context this session inherits

**Just shipped (v2.163.0, 2026-06-10):** V4 Results page redesign + Match
Detail page + admin completeness check. **All currently hidden behind**
`V4_RESULTS_ENABLED = false` const at `frontend/src/routes/results/+page.svelte:67`
— the page renders the pre-tournament stub for users; admin completeness
button is live on `/admin/entries`; backend `MatchPredictionRead.points`,
`CommunityPrediction.rank`, and `/api/leaderboard/scoring-rules` are
live but dormant. Merge commit `9afb8a7` on `main`, live on
https://wc26.heyvinay.com.

**Memory to read before starting** (the auto-memory system loads
`MEMORY.md` automatically; these are the high-leverage files):

- `predictorv2-results-leaderboard-rebuild.md` — what just shipped and
  the 7 gotchas the V4 rebuild hit (`match_number = NULL` in prod,
  bracket expected = 63 not 87, MatchStatus enum stringification, Bearer
  CSV pattern, types-outside-barrel, etc.)
- `predictorv2-worktree-overlay-pattern.md` — the cp/test/restore
  pattern used to test against the running docker-compose stack from a
  Claude worktree on a Windows OneDrive mount
- `predictorv2-v2161-scoring-release.md` — the scoring engine semantics
  (lineup-banked KO, logarithmic rarity, parity harness)
- `feedback-daisyui-surface-ladder.md` + `feedback-text-warning-token-trap.md`
  — DaisyUI surface conventions (`bg-base-200` cards, `bg-base-300`
  dividers, `text-warning-text` for amber foreground)
- `predictorv2-production-deploy.md` — `ssh root@... git pull && docker
  compose --profile prod up -d --build` (force-recreate nginx only when
  `nginx/nginx.conf` changed)

## What I want this session to deliver

Rebuild the **Leaderboard / Standings page** at `/leaderboard` (sidebar
label is "Standings"). Currently shows the pre-tournament stub
"Standings open at kickoff". Real standings render once any match
finishes — but the UI hasn't been touched since the v2.161.0 scoring
fixes, so this is the right moment to redesign against actual points
data flowing.

**Target release: v2.164.0** (or v2.165.0 if the work splits across
sessions). Separate from the V4 Results work — different page,
different scope, different deploy.

**The data is largely ready.** Solid backend already exists:
- `GET /api/leaderboard/` — full leaderboard with cached
  `calculate_leaderboard` (30s TTL), per-entry `PointBreakdown`
  (phase1/phase2 split, match + bracket + bonus components)
- `GET /api/leaderboard/breakdown/{entry_id}` — detailed per-entry
  point breakdown
- `GET /api/leaderboard/snapshots/me`, `/snapshots/{entry_id}` — rank
  trajectory over N days
- `GET /api/leaderboard/climbers` — top movers in the last N days

This rebuild is **mostly frontend**. Backend may need small additive
extensions (e.g., per-category bonus point split if we want it on the
leaderboard rows — same gap the Phase 1 PointsSummary card hit).

## How I want to work the session

1. **Start with brainstorming** (`superpowers:brainstorming` skill).
   Don't propose architecture until you've explored: what's the user
   asking the Leaderboard to answer? Is it "where am I in the pack" /
   "who's gaining on me" / "what does my trajectory look like" / all
   three? What does mobile-first look like at 375px? Sparklines /
   movement arrows / per-entry drilldown — what stays, what's new?
2. **Look at the V3 Leaderboard first** to understand what users have
   today: `frontend/src/routes/leaderboard/+page.svelte`. Don't blindly
   redesign what already works — improve what's clunky.
3. **Check for stashed mockups**: `mockups/Leaderboard-redesign/` may
   exist if I've collected reference imagery; otherwise the design
   conversation is fresh.
4. **Three-plan structure if scope warrants it** — same shape as the
   V4 work: backend additions → leaderboard page core → drilldown /
   detail. Or one plan if scope is smaller.
5. **Same execution constraints as v2.163.0:**
   - Branch `claude/leaderboard-revamp` (worktree)
   - Both themes (`premium-night` default, `hybrid` light)
   - Mobile-first at 375px
   - DaisyUI semantic tokens — NO raw hex
   - Blind pool rule still applies pre-deadline (already
     backend-enforced)
   - **Don't touch `frontend/src/lib/types/index.ts`** — user has WIP
     pending there. New types go in `$lib/types/leaderboard.ts` or
     similar.
   - Same worktree-overlay pattern for tests + browser smoke
6. **Feature-flag the new UI** the way V4 Results was flagged —
   `LEADERBOARD_V4_ENABLED = false` (or similar). Ships safely
   alongside the current page until the user OKs the flip.

## Hazards inherited from the v2.163.0 session

- **OneDrive / VS Code may revert working-tree files mid-session
  without a git command.** I lost the user's Mission Control WIP at
  one point and had to flag it for VS Code Timeline recovery. If files
  reappear missing from `git status` that you didn't touch, **stop and
  ask before proceeding** — don't silently restore from HEAD.
- **The frontend-dev container's `./shared` mount may not exist** —
  parity test fails until `docker compose up -d --force-recreate
  frontend-dev`. Pre-existing test failure (unrelated to leaderboard
  work) — note it, don't fix it.
- **`match_number = NULL`** in the real DB for group fixtures. Already
  worked around in the V4 round-bucketing util — if the leaderboard
  ever needs round-mapping, reuse `deriveGroupMatchdays` from
  `frontend/src/lib/utils/resultsRounds.ts`.
- **`text-warning` is a surface token, not a foreground.** Use
  `text-warning-text` for amber text.
- **Latent layout bug** in `+layout.svelte:68-69` (`pathname`
  TypeError) is still unfixed because the user's WIP held the file
  open. If you touch the layout for any reason, fix it as part of the
  same change.

## When you're done

1. Run the same v2.163.0-style verification: full backend pytest
   suite green, frontend vitest green, `npm run check` 0 new errors,
   browser smoke at desktop + 375px in both themes.
2. Version bump to v2.164.0 (or whatever's next) per CLAUDE.md
   versioning rule, append a changelog entry, commit as `chore(version):`.
3. Merge `claude/leaderboard-revamp` → main with `--no-ff`, push, and
   deploy via the standard recipe.
4. Update CLAUDE.md + the
   `predictorv2-results-leaderboard-rebuild.md` memory file with the
   ship state and any new gotchas.
5. Write a handover prompt for the NEXT session — there's always
   another thing.

## Things explicitly NOT in scope this session

- Touching anything in `/results` or `/results/[fixture_id]` — that's
  v2.163.0 surface. If V4 Results bugs surface, file them as separate
  small fixes; don't bundle them with the Leaderboard release.
- Phase 2 endpoint cleanup (`/standings/actual`, `/knockout/actual`).
  Dormant. Per CLAUDE.md, do not extend.
- The user's Mission Control WIP under
  `frontend/src/lib/components/landing/`. That's a separate project.
- The latent `pathname` TypeError unless you happen to be editing
  `+layout.svelte` for leaderboard reasons.

---

**Opening line for the new session:**

> I'm ready to rebuild the Leaderboard / Standings page (v2.164.0).
> Read `docs/superpowers/NEXT_SESSION_HANDOVER.md` first — it has the
> full context from the v2.163.0 ship that just landed. Start with
> `superpowers:brainstorming` to explore the design.

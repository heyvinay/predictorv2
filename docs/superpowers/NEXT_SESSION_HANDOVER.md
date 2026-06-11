# Next session handover — post-V4-Leaderboard (v2.164.0)

> The Leaderboard rebuild this file used to describe is DONE (built
> 2026-06-11, dev-verified, merged to main). This file now covers what
> remains.

## State you inherit

- **v2.164.0 on main, NOT yet deployed.** The user deploys themselves:
  `ssh root@167.235.145.76 'cd /opt/predictor && git pull && docker
  compose --profile prod up -d --build'`. No nginx changes, no DB
  migrations in this release. After deploy, grep output for
  `Conflict. The container name` (see memory).
- **V4 Leaderboard is flag-ON** (`V4_LEADERBOARD_ENABLED = true`,
  deadline-ANDed) — it goes live the moment prod deploys AND the
  19:00 UTC 2026-06-11 deadline has passed. Rollback = flip to false.
- **V4 Results is still flag-OFF** (`V4_RESULTS_ENABLED = false` at
  `frontend/src/routes/results/+page.svelte:66`). The user may want
  both flipped together — ask.
- CLAUDE.md has the full V4 Leaderboard section (architecture, flag,
  pools, elimination rules, dev-loop gotchas).

## Obvious next pieces (none committed to)

1. **Backend insights endpoint** to unlock the 5 gated cards
   (`INSIGHTS_EXTENDED` in `InsightsGrid.svelte`): herd %, heartbreak
   (near-miss), biggest hauls, hot hand streaks, pick twins. One pass
   over all match predictions × scores server-side; pairwise twins is
   O(n²·fixtures) but fine at ~100 entries.
2. **Flip V4_RESULTS_ENABLED** once the user okays the Results page.
3. **Latent layout `pathname` TypeError** in `+layout.svelte:68-69` —
   still unfixed (user WIP held the file). Fix opportunistically.
4. Post-deploy sanity: leaderboard rows show employer pools correctly
   against real prod users; daily_movement appears after the second
   snapshot day.

## Hazards (verified again this session)

- **Vite file-watching is DEAD on the OneDrive bind mount.** Overlay
  copies are invisible to HMR — `docker compose restart frontend-dev`
  after every frontend overlay, or you chase phantom
  "does not provide an export" / SSR 500 errors.
- **Never gate page data loads on `onMount`** — `$phase1Deadline`
  hydrates after mount; use the reactive one-shot pattern
  (`$: if (gate && !requested)`), as both V4 pages now do.
- The `./shared` mount may be missing in frontend-dev →
  `matchBreakdown.parity.test.ts` fails. Pre-existing; recreate the
  container if you need it green.
- Main worktree carries user dirt (`.gitignore` M, `issues.md` D,
  `mockups/` untracked) — never sweep it into restores or commits.

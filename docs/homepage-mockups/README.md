# The Predictor — "Mission Control" design mockups

Static, throwaway **design mockups** for the live World Cup 2026 member
experience (homepage, results, leaderboard) — not app code. Each screen is a
self-contained HTML file rendered to PNG with the real `premium-night` /
`hybrid` theme tokens, the house font stack, and scoring numbers from
`config/worldcup2026.yml`. See **[`DESIGN-PROMPT.md`](DESIGN-PROMPT.md)** for the
paste-ready brief (e.g. to seed a Claude Project).

> **Viewing:** renders on GitHub as-is. For **Obsidian**, copy this whole folder
> into your vault — the image embeds below resolve locally.
> **Stack:** designs map 1:1 onto SvelteKit 2 + Svelte 4 + Tailwind 3 + DaisyUI 4
> (see the compatibility section in `DESIGN-PROMPT.md`).
> **Note:** `flags.css` (gradient flags) and `theme-hybrid.css` are mockup-only
> scaffolding (CDN flag services are blocked in the build sandbox).

---

## Homepage — pre-tournament (dynamic)
Auth- & entry-status-aware. The hero renders ONE state per user; stacked here.
Mitigates the "created but never submitted" risk (a `draft` doesn't count).

![pre-tournament landing — dark](landing-pretournament.png)
![pre-tournament landing — light](landing-pretournament-light.png)

## Homepage — Mission Control (live, post-kickoff)
Broadcast hero, match rail, AI Newsroom, you-vs-field, crowd-vs-you, widgets.

| v1 | v2 (broadcast hero + rank line) | v2 mobile |
|---|---|---|
| ![](dashboard-dark.png) | ![](dashboard-v2-dark.png) | ![](dashboard-v2-mobile.png) |

Light theme (v1) and multi-entry hero (v3):

| dashboard light | v3 multi-entry hero | v3 light |
|---|---|---|
| ![](dashboard-light.png) | ![](dashboard-v3-mobile.png) | ![](dashboard-v3-light.png) |

## Homepage — early / thin-data (Matchday 1)
Everyone level, leaderboard not yet meaningful, but still alive.

![early state — dark](state-early-mobile.png)
![early state — light](state-early-light.png)

## Homepage — guest "live" landing
Signed-out visitor once the tournament is underway.

![guest live landing](landing-live-mobile.png)

---

## Results — season landing
Round-by-round (Group + Knockout) with running total + rank-over-time.

| mobile | desktop |
|---|---|
| ![](results-season-mobile.png) | ![](results-season-desktop.png) |

## Results — My Round
Your slate for a round; verdict pills surface the rarity bonus. Filter/sort bar.

| mobile | light | desktop |
|---|---|---|
| ![](results-myround-mobile.png) | ![](results-myround-light.png) | ![](results-myround-desktop.png) |

## Results — Match detail (rarity-forward)
Three-pill breakdown + "how the rarity bonus was assigned" + scoreline bubble
grid + pool sorted by points.

| mobile | light | desktop |
|---|---|---|
| ![](results-match-mobile.png) | ![](results-match-light.png) | ![](results-match-desktop.png) |

## Results — Upcoming match (pool split)
Reachable post-deadline: outcome split with rarity under-braces, bubble grid,
pool picks; provisional/ghost points.

![upcoming match pool split](match-upcoming-mobile.png)

## Results — Knockout / bracket
Separate, simpler scoring: flat points per correctly-advanced team — no exact,
no rarity.

| mobile | light |
|---|---|
| ![](results-knockout-mobile.png) | ![](results-knockout-light.png) |

---

## Leaderboard
All entries ranked; search, sort, filter chips, follow ★. Row → entry detail.

| mobile | light | desktop |
|---|---|---|
| ![](leaderboard-mobile.png) | ![](leaderboard-light.png) | ![](leaderboard-desktop.png) |

## Entry detail
The shared "open an entry" destination: follow, head-to-head, form, recent
points, their upcoming (locked) picks.

| mobile | desktop |
|---|---|
| ![](entry-detail-mobile.png) | ![](entry-detail-desktop.png) |

---

## Multi-entry handling
Single entry is the clean default; with 2+, a switcher appears; points never
aggregate; in pools the viewed entry is highlighted, others get a subtle marker.

![multi-entry](multi-entry.png)

## Connectivity
How the surfaces link — the entry is the join key.

![connectivity map](connectivity-map.png)

# Post-Tournament Wrap-up Page (Sub-project C)

**Date:** 2026-07-18 · **Status:** approved design, pending implementation
**Companions:** `2026-07-18-tournament-conclusion-backend-design.md` (A),
`2026-07-18-compare-page-design.md` (B)
**Mock:** iterated to approval as a Claude artifact ("WC26 — Post-tournament
page mock", member + guest toggle, mobile-verified at 390px). The mock is the
visual source of truth for layout, density and copy tone.

## Goal

When `tournament_concluded` flips, `/` becomes a celebratory, **fully public**
wrap-up page for everyone — replacing DashboardV4 for members and the
marketing landing for guests. It is the tournament's permanent record and the
app's last impression: engagement (personal stories, head-to-head hook,
feedback capture) is the design driver.

## 1. Dispatcher & preview switcher

- `frontend/src/routes/+page.svelte` home view model gains a fourth state:
  `concluded` → `WrapUp.svelte` (new, `frontend/src/lib/components/wrapup/`).
  Pre/during states untouched — **the marketing landing survives unchanged
  for future tournaments.**
- Guests get the same page (public data per A §6); the layout swaps
  member-only tiles via the same composition, not a separate page.
- `<meta name="robots" content="noindex">` when the wrap-up renders
  (link-shareable, not searchable).
- **Admin preview switcher** (extends the existing "View as pool" button):
  a bottom-right cluster with two rows — Audience: Admin/Pool · Phase:
  Auto/Pre/During/Post. Client-side override of the dispatcher inputs only,
  persisted per-device beside `ADMIN_VIEW_KEY`, with a visible
  "previewing: post-tournament" tag whenever non-Auto. This + the A-spec
  admin bypass on data endpoints = full production dress-rehearsal before
  the flag flips.

## 2. Layout — bento grid

6-column CSS grid, `grid-auto-flow: dense`, 12px gap. **DOM stays in
narrative order**; tiles declare spans (`b2/b3/b4/b6`, `tall`). Collapse
tiers: full bento >1100px; mid tier (b4→6, b2/b3→3) to 760px; single column
below. Dense flow means member-only/guest-only tiles swap without layout
holes.

Tile inventory, in DOM order (M = member-only, G = guest-only):

| # | Tile | Span | Notes |
|---|---|---|---|
| 1 | Podium hero | b4 tall | §3 |
| 2 | The Final | b2 | result + admin narrative (A §4) |
| 3 | Why didn't I win? | b2 M | gold-bordered CTA card → /compare (B); hidden for guests — dense flow backfills |
| 4 | How the title was won | b3 | §4 matrix |
| 5 | Leaderboard 🏁 | b3 | §5 |
| 6 | Your tournament | b4 M | §6 superlatives |
| 7 | Sign-in strip | b6 G | §7 |
| 8 | Feedback | b2 M | §8 |
| 9 | The pool vs the tournament | b4 tall | §9 |
| 10 | Who picked whom — champion | b2 | actual champion highlighted, "41 entries backed…" |
| 11 | Bonus questions — hit rate | b2 | correct answer in gold under each question |
| 12 | Points DNA | b6 | §10 |
| 13 | Atlas thank-you | b2 | §11 |
| 14 | Charity + links | b4 | §11 |

**Every stat tile opens with a one-line muted narrative explainer** (`.narr`
convention) — template strings with interpolated values (entry counts,
percentile), per the approved copy in the mock. Not derived-condition prose
(structural-display rule stays respected).

## 3. Podium hero (b4 tall)

- Subtle stadium background: goal frame + floodlight beams + pitch lines at
  ~15% opacity behind the content. Production uses a **free-licensed photo
  asset** shipped in `frontend/static` (Atlas-TRIONDA precedent); the admin
  approves the final image at implementation. SVG placeholder acceptable
  until then.
- Classic 2·1·3 podium: champion center on the tall gold plinth (Bebas
  `font-hero` name, 🏆, pts + €595), runner-up left, third right; medals,
  points, champion-pick meta (hidden ≤560px). 🏐 Trionda badge pinned on the
  recipient's column when they're on the podium.
- **Honours board** under the plinths: 🏆 Overall Champion €595 ·
  🏅 Group Stage Champion €183 · 🏐 Trionda ball (recipient + reason label;
  `requires_draw` renders "draw pending between X and Y"). Rows click through
  to `/leaderboard?entry={id}`.
- Story line (served `story_line`), meta strip, and the
  **"✓ Verified result — how this was checked →"** pill linking to
  `/rules#verification` (A §7). Verification narrative does NOT live on this
  page.

## 4. How the title was won (b3)

Transposed matrix fed by the final-podium payload + B's `compareEntries`
engine over the top-3 entries' picks:

- Columns: 🏆 champion (gold-tinted column) · 🥈 2nd · 🥉 3rd.
- Rows in three sections: **Points** (Group / Knockouts / Bonus / Total —
  gold rule above Total), **Decisive moments** (top ~3 swings among the trio,
  from the engine, with why-sublabels), **The race in numbers** (Exact
  scores, Rarity bonus, Days at #1, Champion pick ✓/✗ — all served fields).
- Gold = best in row. Footer: caption + member-only "Full head-to-head →
  /compare" gold link.

## 5. Leaderboard tile (b3)

Mimics the real board: header row GRP/KO/TOTAL; each row = rank, name
(`rowDisplayName`), **champion pick sub-line** (gold ✓ when it was the actual
champion), group pts, knockout pts, total. Top 10; viewer's row highlighted
(member); 🏁 Final pill; footer link to the full `/leaderboard`.

## 6. Your tournament (b4, member)

Header: "Your tournament — {name}", stat line (rank of N · pts · splits),
narrative line with pool percentile. Below: **three personal superlative
cards** from `pool-retrospective.personal` (A §8). Catalog (computed in the
aggregate pass; pick the 3 strongest per entry, fallbacks guarantee every
member gets 3):

1. *Only you called it* — rarest correct exact (fewest co-predictors; "1 of
   183" gold moment).
2. *Sharp shooter* — exact-score count + pool percentile.
3. *Faithful to the end* — champion pick went the distance (or furthest-run
   variant).
4. *Giant killer* — most points from low-consensus (<15%) correct picks.
5. *Best matchday* — biggest single-day points haul.
6. *Bracket architect* — KO advancement hit-rate percentile.
Fallbacks 5/6 fire when 1–4 are weak. Multi-entry holders: card shows their
best entry with an entry switcher consistent with existing conventions.

## 7. Guest sign-in strip (b6, guest)

Full-width: copy left ("In the pool? Sign in to see your personal wrap…",
"Not in the pool? Keep scrolling"), controls right — **mount the real
`SignInCard` flows** (email magic link + Continue with Google), restyled into
the strip; zero new auth code. Members with live sessions never see this
(token persists — arriving from the email lands signed-in).

## 8. Feedback tile (b2, member)

- Stars are the entry point: **tapping a star records the rating instantly**
  (existing `markRatingAsked()` semantics; this surface force-opens regardless
  of the 4-view threshold and is tappable even if previously "asked" — it's
  an explicit user action).
- After the tap, inline: **feature chips** (Leaderboard, Insights, Match
  detail, Compare, Smart Fill) + free-text + Send.
- `POST /api/feedback/` extended with optional `features: string[]`
  (validated against a fixed list, serialized into the Resend email body).
  No DB table (unchanged posture).
- Chip taps fire `feature_rated`-style analytics so /admin/usage gets a
  popularity signal even without text.

## 9. The pool vs the tournament (b4 tall)

All data from `pool-retrospective` (A §8):
- Three stat tiles: Group games called right (41/72) · **Final called right**
  (62%, gold-tinted tile, "backed 🏆 Argentina — world champions") · Exact
  scores landed (total + avg).
- Two pill columns: 😱 Biggest collective misses (top 3, red) · 🏦 Bankers
  that landed (top 3, green).
- **Bracket-faith ladder**: per KO stage a gradient progress bar (consensus
  share, % in-bar), fraction (26/32…), fallen-team ✕ chips (+N-more
  overflow); Final row gold at 100% with "called both finalists ✓"; **Winner
  row** — pool's consensus champion vs actual (gold ✓ chip, or the fell-chip
  naming the consensus pick).

## 10. Points DNA (b6)

The Insights-tab format reused: horizontal stacked bars (Exact / Result /
Rarity hatch / Bracket blues R32→Winner / Bonus), top 8 + viewer's entries
appended & highlighted, totals right. **Tweak: point values labelled in-bar;
segments narrower than ~28px drop the label** (value stays in the tooltip).
Extract the card from `InsightsGrid.svelte` for reuse if currently inlined.

## 11. Atlas + charity close (b2 + b4)

- **Atlas card**: logo (real asset from Atlas at implementation), headline
  **€500** "donated to charity by Atlas Insurance, topping up the pool's own
  Soup Kitchen donation", secondary line for the Trionda ball (€150). No
  summed charity total on this card.
- **Charity strip**: €595 champion · €183 group stage · €137 Soup Kitchen ·
  thank-you line · footer link pills (Final leaderboard · Head-to-head
  compare [member] · Results archive).

## 12. Analytics (all → EventName union; discretionary → FEATURE_GROUPS)

`wrapup_viewed` (with auth_state), `wrapup_compare_cta_clicked` (the Why card
— the headline engagement metric), `wrapup_podium_row_clicked`,
`wrapup_verified_link_clicked`, `wrapup_matrix_compare_clicked`,
`wrapup_leaderboard_full_clicked`, `wrapup_footer_link_clicked` (with target),
`wrapup_signin_started` (guest), rating/feedback events (existing ones fire;
chips per §8). Guests track under PostHog anonymous device IDs — the usage
dashboard shows member engagement by name + an anonymous visitor count.

## 13. Mobile acceptance checklist (390px — from the verified audit)

- Podium: 3-up plinths compressed, champion-pick meta hidden.
- Matrix: first column ellipsizes; Bonus column yields so Group/KO/Total fit.
- Points DNA: bars wrap to their own line; narrow segments unlabelled.
- Misses/bankers pills and KO ladder stack cleanly; sign-in strip stacks
  centered; all tiles single-column in DOM (narrative) order.
- Feedback band must not sink below the fold-equivalent — verify placement on
  phone; use the render-twice breakpoint pattern only if needed.
- Light-mode (hybrid theme) pass before ship (standing checklist rule).

## Dependencies & build order

1. A's flag + final-podium + retrospective endpoints (page data).
2. B's `compareEntries.ts` + shared components (matrix decisive moments,
   Why-card target).
3. This page last; integrate; verify via the preview switcher in prod.

## Out of scope

- Race chart (cut), Consensus-bracket matrix (cut), "This was The Predictor"
  note (cut) — all deliberate removals; do not resurrect.
- No Phase 2 anything; no changes to /results, /leaderboard internals beyond
  the 🏁/live-cue gating in A.

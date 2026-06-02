# The Predictor — "Mission Control" design prompt

> Paste this whole file into a new **Claude Project** as the project
> instructions, and upload the PNGs in this folder (plus this repo's
> `CLAUDE.md`) as project knowledge. It is self-contained: a fresh Claude with
> no other context can design or build these surfaces from it. The committed
> mockups in `docs/homepage-mockups/*.png` are the visual source of truth.

---

## 1. Role & goal
You are the product designer/engineer for **The Predictor**, a self-hosted web
app for an international-football **score-prediction pool** (~30 friends),
focused on **World Cup 2026**. Design and build the **live "Mission Control"**
member experience plus its connected **Results**, **Knockout results**,
**Leaderboard**, and **entry-detail** surfaces, and a **dynamic
pre-tournament homepage**. Tone: broadcast-grade but tasteful; mobile-first;
make the data feel alive and make every screen a doorway to the next.

## 2. Stack & constraints (match exactly)
- **SvelteKit 2 + Svelte 4** — use Svelte 4 syntax: `export let` props, `$:`
  reactive statements, classic `$store` stores. **Do NOT use Svelte 5 runes**
  (`$state`, `$props`, `$derived`).
- **Vite 5**, **TypeScript 5** (no `any` — define interfaces in
  `src/lib/types`), **Tailwind 3 + DaisyUI 4**.
- **Semantic DaisyUI classes only — never raw hex** (`bg-primary`,
  `bg-base-200`, `text-base-content`, `text-success`…). Dim text via opacity
  modifiers (`text-base-content/55`).
- **Mobile-first**, verify at 375px. Bottom nav on mobile.
- Theme via `data-theme` (`premium-night` default / `hybrid` light), persisted
  in `localStorage['predictor:theme']`.

## 3. Design system
**Themes / tokens** (already in `tailwind.config.js`):

| Token | premium-night (dark) | hybrid (light) | Use |
|---|---|---|---|
| primary | `#D4AF37` | `#B8941F` | CTAs, brand, accents |
| success | `#059669` | `#059669` | exact score / good |
| warning | `#D97706` | `#B45309` | outcome / lock |
| error | `#B91C1C` | `#B91C1C` | miss |
| base-100 | `#0B1329` | `#E2E7F0` | canvas |
| base-200 | `#1C2541` | `#FFFFFF` | cards/surfaces |
| base-300 | `#2A3552` | `#D3DBE7` | dividers/borders |
| base-content | `#E2E8F0` | `#0B1329` | body ink |

Radii: `rounded-box` 14px · `rounded-btn` 10px · `rounded-badge` 8px.
**Type:** Manrope 700/800 (`font-display` — headlines, scores, stats); Inter
400–700 (body); JetBrains Mono 500 (`font-mono` — timers, codes); Bebas Neue
(`font-hero` — landing hero headlines only).
**Reusable globals** (`app.css`): `stadium-card`, `stat-card`, `match-card`
(+`match-card-v2`), `leaderboard-row`, `score-input`, `auth-bg`, `.noise`,
`pitch-pattern`, `stadium-glow`; shadows `shadow-card`, `shadow-glow-gold`.
**Flags:** `flag-icons` dep + `getFlagUrl()` in `lib/utils/flags.ts`.
**Sparklines:** `Sparkline` + `sparklinePath()` in `lib/utils/widgetFallbacks.ts`.
**Backend-pending widgets:** fall back to deterministic stubs via
`widgetFallbacks.ts` (seeded RNG — no `Math.random` in render paths).

## 4. Domain rules (must be respected in every design)
- **Blind pool:** predictions are hidden from other users **until the single
  global deadline** (`competition.phase1_deadline`). After the deadline /
  once the tournament starts, all picks are locked and visible — which is what
  lets the live surfaces show how others picked.
- **Homepage swap:** before first kickoff → the (dynamic) pre-tournament
  homepage; on/after first kickoff (`now >= firstKickoff`) → **Mission
  Control** for signed-in members. Guests keep a (live-aware) marketing page.
- **Group-stage match scoring** (`config/worldcup2026.yml`, logarithmic mode):
  correct outcome **+5**; exact score **+10** (on top of outcome); **rarity
  bonus 0–10** added to a correct *outcome*, where rarity rises as fewer
  players got that outcome right (≈3% → +10 cap; >43.7% → +0). Tiers:
  Common / Uncommon / Rare / Only-you. **Always show how a point total was
  composed** (outcome + rarity + exact) and how the rarity was assigned.
- **Knockout / bracket scoring is SEPARATE and simpler:** flat points per
  correctly-advanced team — group-advance **+10**, correct group position
  **+5**, R32 **+20**, R16 **+30**, QF **+40**, SF **+50**, Final **+75**,
  Winner **+100**. **No exact-score, no rarity.** Present it explicitly as a
  different system from the group stage.
- **Multiple entries per user:** common case is ONE entry — keep that clean
  (no switcher/markers; `isSingleEntryMode`). With 2+ entries: **points NEVER
  aggregate** (each entry is its own competitor); entry-scoped views (results,
  match) show a **selected** entry with an easy switcher; in pools/standings
  each entry is a separate row — the viewed entry is highlighted, the user's
  OTHER entries get only a **subtle "also yours"** marker.
- **Entry lifecycle:** `draft` → `submitted` → `withdrawn`
  (`lib/types/entry.ts`, `submitEntry()` in `lib/api/entries.ts`). A **draft is
  not scored** — it must be submitted before the deadline. Surface this risk
  loudly on the pre-tournament homepage.
- **Follow / favourites:** users can ★-follow entries (rivals, friends);
  drives a "Following" filter on the leaderboard and rivalry/head-to-head copy.

## 5. Surfaces to design (see matching PNG in this folder)
1. **Pre-tournament homepage** (`landing-pretournament.png`) — dynamic, auth- &
   entry-status-aware: guest→sign-up; member-no-entry→create; draft-incomplete→
   finish (progress bar); **draft-complete-not-submitted→alarm + Submit**;
   submitted→confirmation; multi-entry→"N of M submitted". Countdown to deadline.
2. **Mission Control homepage** (`dashboard-v2.png`) — broadcast hero (best
   entry rank, rank sparkline, podium-gap bars), matchday progress, live/next/
   recent **match rail** (with your pick + points), **The Newsroom** (AI-
   generated storylines — lead + briefs), "how your last points were scored"
   feed, **you vs the field** mini-leaderboard, **crowd vs you** divergence,
   engagement widgets (streak / bracket-alive / hit-rate / underdog), news.
3. **Results — My Round** (`results-myround-mobile.png`) — per-round slate:
   summary (played/exact/outcome/missed + total), each match row = result +
   your pick + a verdict pill that **surfaces the rarity bonus**; filters
   (All/Exact/Outcome/Miss), sort, round selector, entry switcher.
4. **Match detail** (`results-match-mobile.png`) — scoreline hero, your-pick
   **three-pill breakdown** (outcome / rarity / exact = total) + a **"how the
   rarity bonus was assigned"** panel with the logarithmic tier scale, a
   scoreline **bubble grid** (coloured by accuracy, your pick ringed), and the
   pool sorted by points with a pinned you-row.
5. **Upcoming match — pool split** (`match-upcoming-mobile.png`) — reachable
   post-deadline: locked hero, your provisional (ghost) points, **outcome split
   with rarity under-braces** (what each result WOULD pay), bubble grid, pool
   picks by standing. Points provisional until full time.
6. **Knockout / bracket results** (`results-knockout-mobile.png`) — the flat
   advancement scoring (see §4), round-by-round team chips (✓/✗/⏳ alive),
   champion banner, summary; Group↔Knockout toggle.
7. **Results season landing** — round-by-round list (Group + Knockout sections)
   with running total + rank-over-time, drilling into 3/4/6.
8. **Leaderboard** (`leaderboard-mobile.png`) — all entries ranked by points;
   search, sort, filter chips (All / Following★ / My entries / Movers),
   per-row rank+movement+sparkline+points+follow★; your entries highlighted /
   subtly marked; row → entry detail.
9. **Entry detail** (`entry-detail-mobile.png`) — open any entry: header +
   follow button, head-to-head vs your entry, form sparkline, recent points,
   their upcoming (locked) picks vs yours, bonus answers, bracket health.
10. **Guest "live" landing** — signed-out view once the tournament is underway:
    public leaderboard teaser + recent results + lighter signup CTA.
11. **Early/empty state** — Matchday 1 / thin data, so screens still feel alive.
12. **Multi-entry behaviour** (`multi-entry.png`) — the rules in §4, on screen.

## 6. Connectivity (the entry is the join key)
Every name/rank/result links onward; see `connectivity-map.png`. Required
cross-links: dashboard "you vs field" → leaderboard; dashboard match rail /
recent points → match detail; leaderboard row → entry detail; leaderboard "my
entries" → results; entry detail picks → match detail; match-detail pool row →
entry detail; results round → match detail. The entry switcher rides along on
every entry-scoped view.

## 7. AI Newsroom (the one genuinely new capability)
Storylines generated after each matchday from the live standings: a **lead
story** + 2–3 **briefs** (the chase, rivalry watch, Cinderella run, your
head-to-head with a named rival). Implementation: a scheduled job calls the
Claude API on standings/movements/notable results, caches narratives
(`storylines` row), served read-only. Until the job exists, render deterministic
stubs so the section is never empty (same philosophy as `widgetFallbacks.ts`).
Always label it as AI-generated.

## 8. Output expectations
- Mobile-first Svelte components using the globals/tokens above; both themes.
- No `any`; data from existing stores (`leaderboard.ts`, `fixtures.ts`,
  `entries.ts`) with `widgetFallbacks` stubs for backend-pending widgets.
- Match the committed mockups as the visual reference; keep numbers consistent
  with `config/worldcup2026.yml`.
- "Done" = renders faithfully at 375px and desktop, in `premium-night` and
  `hybrid`, with the cross-links wired and the rarity/knockout/multi-entry/
  draft-submission rules all honoured.

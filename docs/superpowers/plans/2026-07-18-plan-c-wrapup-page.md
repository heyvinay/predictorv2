# Post-Tournament Wrap-up Page (Plan C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `tournament_concluded` flips, `/` becomes the public bento wrap-up page (member + guest variants) — podium hero, Final card, compare CTA, title matrix, final leaderboard, personal superlatives, pool retrospective, Points DNA, interactive feedback, Atlas/charity close.

**Architecture:** A new `WrapUp.svelte` composition mounted by a fourth `HomeView` state in `+page.svelte`. Data: `getFinalPodium()` + `getPoolRetrospective()` (Plan A endpoints) + `getLeaderboardV4()` + fixtures store; the title matrix reuses Plan B's `compareEntries` engine over the top-3 entries. Tiles are `section` children of a 6-col dense bento grid — DOM order = narrative order; member/guest swaps via `member-only`/`guest-only` and dense backfill.

**Tech Stack:** SvelteKit + TypeScript, Tailwind/DaisyUI semantic tokens, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-18-wrapup-page-design.md` · **Visual source of truth:** the approved artifact mock ("WC26 — Post-tournament page mock", member/guest toggle, mobile-verified).

**Prerequisites:** Plan A Tasks A1–A7 (flag, endpoints) and Plan B Tasks B1–B3 (engine + shared components) are merged.

**Testing note:** overlay pattern for all checks; the LIVE :5173 dev server needs `docker compose restart frontend-dev` per overlay round. Light-mode (hybrid) pass + 390px pass are explicit steps, not optional.

---

### Task C1: Types + API clients + dispatcher state

**Files:**
- Create: `frontend/src/lib/types/wrapup.ts` (outside the barrel, V4 convention)
- Modify: `frontend/src/lib/api/leaderboard.ts`
- Modify: `frontend/src/routes/+page.svelte`
- Test: `frontend/src/lib/utils/wrapupView.test.ts` (new; dispatcher logic extracted pure)

- [ ] **Step 1: Types**

Create `frontend/src/lib/types/wrapup.ts` mirroring Plan A's schemas field-for-field:

```ts
/** Wrap-up page payloads (Plan C). Import directly, never via $types
 * (V4 convention: barrel is held open by WIP). */

export interface FinalPodiumEntry {
	entry_id: string;
	user_name: string;
	entry_name: string;
	final_rank: number;
	total_points: number;
	group_points: number;
	knockout_points: number;
	bonus_points: number;
	exact_scores: number;
	rarity_points: number;
	days_at_top: number;
	champion_pick: string | null;
	champion_hit: boolean;
	is_champion: boolean;
}

export interface TriondaOut {
	recipient_name: string | null;
	recipient_entry_id: string | null;
	final_rank: number | null;
	reason: string;
	requires_draw: boolean;
	draw_candidate_names: string[];
}

export interface FinalMatchOut {
	home_team: string;
	away_team: string;
	home_score: number | null;
	away_score: number | null;
	went_to_extra_time: boolean;
	penalties: string | null;
	kickoff: string | null;
	venue: string | null;
	narrative: string | null;
}

export interface AuditSummaryOut {
	run_at: string;
	entries_verified: number;
	matches_rescored: number;
	bonus_questions: number;
	discrepancies: number;
	sources: string[];
}

export interface FinalPodium {
	entries: FinalPodiumEntry[];
	trionda: TriondaOut;
	story_line: string;
	total_days: number;
	final_match: FinalMatchOut | null;
	audit: AuditSummaryOut | null;
}

export interface MatchCallOut { label: string; pct: number; exact_count: number; }
export interface KoLadderRowOut { stage: string; consensus_had: number; of: number; fallen_teams: string[]; }
export interface BonusAnswerOut { question_id: string; label: string; answer_label: string; hit_pct: number; }
export interface ChampionPickOut { team: string; count: number; is_actual: boolean; }
export interface SuperlativeOut { emoji: string; title: string; body: string; }

export interface PersonalWrapOut {
	entry_id: string;
	entry_name: string;
	final_rank: number;
	total_points: number;
	group_points: number;
	knockout_points: number;
	bonus_points: number;
	percentile_label: string;
	superlatives: SuperlativeOut[];
}

export interface PoolRetrospective {
	group_called_right: number;
	group_total: number;
	final_called_right_pct: number;
	final_winner_team: string | null;
	exact_total: number;
	exact_avg_per_entry: number;
	misses: MatchCallOut[];
	bankers: MatchCallOut[];
	ko_ladder: KoLadderRowOut[];
	bonus: BonusAnswerOut[];
	champion_distribution: ChampionPickOut[];
	personal: PersonalWrapOut[] | null;
}
```

- [ ] **Step 2: API clients**

Add to `frontend/src/lib/api/leaderboard.ts` (after `getGroupStagePodium`, ~line 205, same idiom):

```ts
/** GET /leaderboard/final-podium — null until concluded (admins preview). */
export async function getFinalPodium(): Promise<import('$lib/types/wrapup').FinalPodium | null> {
	return api.get('/leaderboard/final-podium');
}

/** GET /leaderboard/pool-retrospective — null until concluded (admins preview). */
export async function getPoolRetrospective(): Promise<
	import('$lib/types/wrapup').PoolRetrospective | null
> {
	return api.get('/leaderboard/pool-retrospective');
}
```

- [ ] **Step 3: Failing dispatcher test**

The view choice becomes pure so it's testable. Create `frontend/src/lib/utils/wrapupView.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { resolveHomeView } from './wrapupView';

describe('resolveHomeView', () => {
	const base = {
		isAuthenticated: false, isAdmin: false, adminPreviewPool: false,
		phaseOverride: 'auto' as const, deadlinePassed: true,
		postDeadlineLive: true, tournamentConcluded: false
	};

	it('guest pre-conclusion → landing', () => {
		expect(resolveHomeView({ ...base })).toBe('landing');
	});
	it('guest post-conclusion → wrapup (public page)', () => {
		expect(resolveHomeView({ ...base, tournamentConcluded: true })).toBe('wrapup');
	});
	it('member during tournament → dash', () => {
		expect(resolveHomeView({ ...base, isAuthenticated: true })).toBe('dash');
	});
	it('member post-conclusion → wrapup', () => {
		expect(resolveHomeView({ ...base, isAuthenticated: true, tournamentConcluded: true })).toBe('wrapup');
	});
	it('admin phase override forces post preview', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, isAdmin: true, phaseOverride: 'post' })
		).toBe('wrapup');
	});
	it('admin override pre shows the marketing landing', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, isAdmin: true, phaseOverride: 'pre' })
		).toBe('landing');
	});
	it('override is ignored for non-admins', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, phaseOverride: 'post' })
		).toBe('dash');
	});
});
```

- [ ] **Step 4: Run to verify failure**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/wrapupView.test.ts`
Expected: FAIL — module missing

- [ ] **Step 5: Implement `wrapupView.ts` + rewire `+page.svelte`**

Create `frontend/src/lib/utils/wrapupView.ts`:

```ts
/** Home dispatcher (pre / during / post) — extracted pure from
 * +page.svelte so the fourth state is unit-tested. */

export type HomeView = 'landing' | 'holding' | 'dash' | 'wrapup';
export type PhaseOverride = 'auto' | 'pre' | 'during' | 'post';

export interface HomeViewInputs {
	isAuthenticated: boolean;
	isAdmin: boolean;
	adminPreviewPool: boolean;
	phaseOverride: PhaseOverride;
	deadlinePassed: boolean;
	postDeadlineLive: boolean;
	tournamentConcluded: boolean;
}

export function resolveHomeView(i: HomeViewInputs): HomeView {
	// Admin phase override (preview switcher) — admins only, client-side only.
	const effective =
		i.isAdmin && i.phaseOverride !== 'auto'
			? i.phaseOverride
			: i.tournamentConcluded
			? 'post'
			: 'auto';

	if (effective === 'post') return 'wrapup';
	if (effective === 'pre') return 'landing';
	if (effective === 'during') return i.isAuthenticated ? 'dash' : 'landing';

	// auto — the pre-existing v2.166.0 model, unchanged
	if (!i.isAuthenticated) return 'landing';
	if (i.isAdmin && !i.adminPreviewPool) return 'dash';
	if (i.postDeadlineLive) return 'dash';
	if (i.deadlinePassed) return 'holding';
	return 'landing';
}
```

Rewire `frontend/src/routes/+page.svelte` (the block at lines 86-103):

```ts
	import { phase1Deadline, postDeadlineLive, tournamentConcluded } from '$stores/phase';
	import { resolveHomeView, type HomeView, type PhaseOverride } from '$lib/utils/wrapupView';
	import WrapUp from '$lib/components/wrapup/WrapUp.svelte';

	const PHASE_OVERRIDE_KEY = 'predictor:admin:phase-override';
	let phaseOverride: PhaseOverride = 'auto';
	onMount(() => {
		adminPreviewPool = localStorage.getItem(ADMIN_VIEW_KEY) === 'pool';
		phaseOverride = (localStorage.getItem(PHASE_OVERRIDE_KEY) as PhaseOverride) ?? 'auto';
	});
	function setPhaseOverride(p: PhaseOverride) {
		phaseOverride = p;
		localStorage.setItem(PHASE_OVERRIDE_KEY, p);
	}

	$: view = resolveHomeView({
		isAuthenticated: $isAuthenticated,
		isAdmin: $user?.is_admin === true,
		adminPreviewPool,
		phaseOverride,
		deadlinePassed,
		postDeadlineLive: V4_DASHBOARD_ENABLED && $postDeadlineLive,
		tournamentConcluded: $tournamentConcluded
	});
```

(The old `poolView`/`view` reactive pair is replaced by this single call; keep `V4_DASHBOARD_ENABLED` folded in as shown so the kill switch semantics are preserved.)

Template: add the branch ABOVE the `'dash'` branch:

```svelte
{#if view === 'wrapup'}
	<WrapUp />
{:else if view === 'dash'}
	...
```

And extend the admin floating control into the preview cluster (replacing the single button at lines 214-227):

```svelte
{#if $isAuthenticated && $user?.is_admin === true}
	<div class="fixed bottom-20 right-4 z-40 rounded-box border border-base-300/70 bg-base-200 p-2.5 shadow-card min-[700px]:bottom-6 text-[11px]">
		<p class="mb-1 font-bold text-base-content/50 uppercase tracking-wider text-[9px]">👁 Preview</p>
		<div class="flex items-center gap-1 mb-1">
			<span class="w-14 text-base-content/50">Audience</span>
			{#each [{ v: false, l: 'Admin' }, { v: true, l: 'Pool' }] as o}
				<button
					class="rounded-badge px-2 py-0.5 font-bold {adminPreviewPool === o.v ? 'bg-primary/15 text-primary' : 'text-base-content/60'}"
					on:click={() => { adminPreviewPool = o.v; localStorage.setItem(ADMIN_VIEW_KEY, o.v ? 'pool' : 'admin'); }}
				>{o.l}</button>
			{/each}
		</div>
		<div class="flex items-center gap-1">
			<span class="w-14 text-base-content/50">Phase</span>
			{#each ['auto', 'pre', 'during', 'post'] as p}
				<button
					class="rounded-badge px-2 py-0.5 font-bold capitalize {phaseOverride === p ? 'bg-primary/15 text-primary' : 'text-base-content/60'}"
					on:click={() => setPhaseOverride(p as PhaseOverride)}
				>{p}</button>
			{/each}
		</div>
		{#if phaseOverride !== 'auto'}
			<p class="mt-1 text-[10px] text-primary">previewing: {phaseOverride} · tap Auto to reset</p>
		{/if}
	</div>
{/if}
```

Create a placeholder `frontend/src/lib/components/wrapup/WrapUp.svelte` so check passes (filled in C2+):

```svelte
<div class="container mx-auto max-w-[1240px] mobile-padding py-6">
	<p class="text-base-content/50">Wrap-up loading…</p>
</div>
```

- [ ] **Step 6: Run tests + check**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/wrapupView.test.ts` → PASS
Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types/wrapup.ts frontend/src/lib/api/leaderboard.ts frontend/src/lib/utils/wrapupView.ts frontend/src/lib/utils/wrapupView.test.ts frontend/src/routes/+page.svelte frontend/src/lib/components/wrapup/WrapUp.svelte
git commit -m "feat(wrapup): fourth home-view state + admin phase-preview cluster + API clients"
```

---

### Task C2: WrapUp shell — bento grid, data load, hero (podium + honours + Final + Atlas)

**Files:**
- Modify: `frontend/src/lib/components/wrapup/WrapUp.svelte`
- Create: `frontend/src/lib/components/wrapup/PodiumHero.svelte`
- Create: `frontend/src/lib/components/wrapup/FinalMatchCard.svelte`
- Create: `frontend/src/lib/components/wrapup/AtlasCard.svelte`

- [ ] **Step 1: WrapUp.svelte shell**

Mirrors DashboardV4's `Promise.all` loading convention. Full file:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { fixtures, fixtureById, fetchAllFixtures } from '$stores/fixtures';
	import { getFinalPodium, getPoolRetrospective, getLeaderboardV4, getScoringRules } from '$api/leaderboard';
	import { track } from '$lib/analytics';
	import type { FinalPodium, PoolRetrospective } from '$lib/types/wrapup';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import PodiumHero from './PodiumHero.svelte';
	import FinalMatchCard from './FinalMatchCard.svelte';
	import AtlasCard from './AtlasCard.svelte';
	import CompareCtaCard from './CompareCtaCard.svelte';
	import TitleMatrix from './TitleMatrix.svelte';
	import FinalLeaderboardTile from './FinalLeaderboardTile.svelte';
	import YourTournament from './YourTournament.svelte';
	import GuestSignInStrip from './GuestSignInStrip.svelte';
	import FeedbackTile from './FeedbackTile.svelte';
	import PoolVsTournament from './PoolVsTournament.svelte';
	import ChampionPicksTile from './ChampionPicksTile.svelte';
	import BonusAnswersTile from './BonusAnswersTile.svelte';
	import PointsDnaTile from './PointsDnaTile.svelte';
	import CharityStrip from './CharityStrip.svelte';

	let podium: FinalPodium | null = null;
	let retro: PoolRetrospective | null = null;
	let rows: LbEntryV4[] = [];
	let rules: ScoringRules | null = null;
	let loading = true;

	async function load() {
		const [p, r, lb, sr] = await Promise.all([
			getFinalPodium().catch(() => null),
			getPoolRetrospective().catch(() => null),
			getLeaderboardV4().catch(() => null),
			getScoringRules().catch(() => null),
			fetchAllFixtures()
		]);
		podium = p;
		retro = r;
		rows = lb?.entries ?? [];
		rules = sr;
		loading = false;
	}

	onMount(() => {
		void load();
		track('wrapup_viewed', { auth_state: $isAuthenticated ? 'authenticated' : 'guest' });
	});

	$: personal = retro?.personal?.[0] ?? null;
</script>

<svelte:head>
	<title>World Cup 2026 — the final story · The Predictor</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="container mx-auto max-w-[1240px] mobile-padding pb-10 pt-3">
	{#if loading}
		<div class="stadium-card no-glow p-10 text-center text-base-content/50">Loading the final story…</div>
	{:else if !podium}
		<div class="stadium-card no-glow p-10 text-center text-base-content/50">
			The wrap-up appears once the tournament concludes.
		</div>
	{:else}
		<div class="grid grid-cols-6 gap-3 [grid-auto-flow:dense] items-stretch">
			<!-- Row 1: hero (4-wide, 2 rows) + Final + [compare CTA | Atlas for guests] -->
			<section class="col-span-6 min-[1100px]:col-span-4 min-[1100px]:row-span-2 min-w-0">
				<PodiumHero {podium} />
			</section>
			<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
				<FinalMatchCard finalMatch={podium.final_match} />
			</section>
			{#if $isAuthenticated}
				<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
					<CompareCtaCard championEntryId={podium.entries[0]?.entry_id ?? null} myEntryId={personal?.entry_id ?? null} />
				</section>
			{:else}
				<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
					<AtlasCard />
				</section>
			{/if}

			<!-- Row 2: title matrix + final leaderboard -->
			<section class="col-span-6 min-[760px]:col-span-3 min-w-0">
				<TitleMatrix {podium} {rows} {rules} />
			</section>
			<section class="col-span-6 min-[760px]:col-span-3 min-w-0">
				<FinalLeaderboardTile {rows} championTeam={retro?.final_winner_team ?? null} myUserId={$user?.id ?? null} />
			</section>

			<!-- Row 3: personal / sign-in + feedback -->
			{#if $isAuthenticated && personal}
				<section class="col-span-6 min-[1100px]:col-span-4 min-w-0">
					<YourTournament {personal} poolSize={rows.length} />
				</section>
				<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
					<FeedbackTile />
				</section>
			{:else if !$isAuthenticated}
				<section class="col-span-6 min-w-0">
					<GuestSignInStrip />
				</section>
			{/if}

			<!-- Row 4: pool retrospective (tall) + two small tiles -->
			{#if retro}
				<section class="col-span-6 min-[1100px]:col-span-4 min-[1100px]:row-span-2 min-w-0">
					<PoolVsTournament {retro} />
				</section>
				<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
					<ChampionPicksTile picks={retro.champion_distribution} />
				</section>
				<section class="col-span-6 min-[760px]:col-span-3 min-[1100px]:col-span-2 min-w-0">
					<BonusAnswersTile bonus={retro.bonus} />
				</section>
			{/if}

			<!-- Row 5: Points DNA full width -->
			<section class="col-span-6 min-w-0">
				<PointsDnaTile {rows} myUserId={$user?.id ?? null} />
			</section>

			<!-- Row 6: Atlas (members; guests saw it up top) + charity -->
			{#if $isAuthenticated}
				<section class="col-span-6 min-[760px]:col-span-2 min-w-0">
					<AtlasCard />
				</section>
			{/if}
			<section class="col-span-6 min-[760px]:col-span-4 min-w-0">
				<CharityStrip isMember={$isAuthenticated} />
			</section>
		</div>
	{/if}
</div>
```

Create stubs for every imported component so `npm run check` passes at each step; each stub is a `stadium-card` with its title, replaced in C3–C6.

- [ ] **Step 2: PodiumHero.svelte**

Podium + honours + story + verified link, per the mock. Champion-pick meta hides ≤560px; SVG stadium placeholder until the licensed asset lands:

```svelte
<script lang="ts">
	import { track } from '$lib/analytics';
	import type { FinalPodium } from '$lib/types/wrapup';

	export let podium: FinalPodium;

	$: [first, second, third] = [
		podium.entries.find((e) => e.final_rank === 1) ?? podium.entries[0],
		podium.entries[1] ?? null,
		podium.entries[2] ?? null
	];
	$: trionda = podium.trionda;
	$: ballOn = (entryId: string) => trionda.recipient_entry_id === entryId;
</script>

<div class="relative overflow-hidden rounded-box border border-primary/40 stadium-card p-5 text-center h-full">
	<!-- stadium backdrop placeholder: swap for the licensed photo asset
	     (frontend/static/wrapup-stadium.webp) at implementation sign-off -->
	<svg class="pointer-events-none absolute inset-0 h-full w-full opacity-15" viewBox="0 0 1200 420" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
		<polygon points="0,0 190,0 70,320" class="fill-primary" opacity=".5" />
		<polygon points="1010,0 1200,0 1130,320" class="fill-primary" opacity=".5" />
		<line x1="0" y1="368" x2="1200" y2="368" class="stroke-primary" stroke-width="2" />
		<ellipse cx="600" cy="368" rx="250" ry="42" fill="none" class="stroke-primary" stroke-width="1.5" />
		<g class="stroke-base-content" stroke-width="3" fill="none">
			<path d="M760,368 V218 H1080 V368" />
			<path d="M760,218 L800,190 H1116 L1080,218" />
			<path d="M1116,190 V340 L1080,368" />
		</g>
	</svg>

	<div class="relative">
		<p class="text-[10px] uppercase tracking-[.24em] text-base-content/55">World Cup 2026 · Final podium</p>

		<div class="mx-auto mt-3 grid max-w-[600px] grid-cols-[1fr_1.15fr_1fr] items-end gap-2.5">
			{#each [{ e: second, cls: 'p2', h: 'h-14', medal: '🥈' }, { e: first, cls: 'p1', h: 'h-[86px]', medal: '🏆' }, { e: third, cls: 'p3', h: 'h-10', medal: '🥉' }] as col}
				{#if col.e}
					<div class="grid gap-1.5">
						<span class={col.cls === 'p1' ? 'text-3xl' : 'text-xl'}>{col.medal}</span>
						<span class="font-bold leading-tight {col.cls === 'p1' ? 'font-hero text-3xl text-primary tracking-wide' : 'text-sm'}">{col.e.user_name}</span>
						<span class="font-display text-xs font-extrabold {col.cls === 'p1' ? 'text-primary' : ''}">{col.e.total_points} pts{col.cls === 'p1' ? ' · €595' : ''}</span>
						{#if ballOn(col.e.entry_id)}
							<span class="justify-self-center rounded-badge border border-primary/45 bg-primary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary">🏐 Trionda ball</span>
						{/if}
						<span class="hidden text-[11px] text-base-content/55 min-[560px]:block">
							Champion pick: {col.e.champion_pick ?? '—'} {col.e.champion_hit ? '✓' : '✗'}
							{col.cls === 'p1' && col.e.days_at_top ? ` · led ${col.e.days_at_top} of ${podium.total_days} days` : ''}
						</span>
						<div class="grid place-items-center rounded-t-lg border border-b-0 {col.h}
							{col.cls === 'p1' ? 'border-primary/55 bg-primary/10 text-primary shadow-glow-gold' : 'border-base-300 bg-base-100 text-base-content/30'}
							font-display text-xl font-extrabold">{col.e.final_rank}</div>
					</div>
				{/if}
			{/each}
		</div>

		<!-- honours board -->
		<div class="mx-auto mt-3 grid max-w-[600px] gap-1 border-t border-primary/35 pt-2.5 text-left">
			<a href={`/leaderboard?entry=${first.entry_id}`} class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-primary/50 bg-primary/5 px-2.5 py-1 text-[13px]"
				on:click={() => track('wrapup_podium_row_clicked', { rank: 1 })}>
				<span>🏆</span>
				<span><b>{first.user_name}</b> <span class="text-xs text-base-content/55">· Overall Champion — highest total after the Final</span></span>
				<span class="font-display text-sm font-extrabold text-primary">€595</span>
			</a>
			<div class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-2.5 py-1 text-[13px]">
				<span>🏅</span>
				<span><b>James</b> <span class="text-xs text-base-content/55">· Group Stage Champion — led when the groups closed</span></span>
				<span class="font-display text-sm font-extrabold text-primary">€183</span>
			</div>
			<div class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-2.5 py-1 text-[13px]">
				<span>🏐</span>
				<span>
					{#if trionda.requires_draw}
						<b>Draw pending</b> <span class="text-xs text-base-content/55">· between {trionda.draw_candidate_names.join(' and ')}</span>
					{:else}
						<b>{trionda.recipient_name ?? '—'}</b>
						<span class="text-xs text-base-content/55">· Adidas Trionda match ball — {trionda.reason}</span>
					{/if}
				</span>
				<span class="font-display text-sm font-extrabold text-primary">Side prize</span>
			</div>
		</div>

		<p class="mx-auto mt-2.5 max-w-[64ch] text-[13px] text-base-content/55">{podium.story_line}</p>

		<p class="mt-2.5 text-xs text-base-content/40">
			{podium.total_days} matchdays · {podium.audit?.entries_verified ?? '183'} entries · one champion ·
			<a href="/rules#verification"
				class="rounded-badge border border-success/40 bg-success/10 px-2 py-0.5 font-bold uppercase tracking-wide text-success no-underline"
				on:click={() => track('wrapup_verified_link_clicked', {})}>
				✓ Verified result — how this was checked →
			</a>
		</p>
	</div>
</div>
```

**Group Stage Champion name:** hardcoding "James" is a mock artifact — fetch via the existing `getGroupStagePodium()` (already released) inside this component (`onMount`, degrade to hiding the row on null) and render `gsw.entries[0].user_name`. Implement that, not the literal.

- [ ] **Step 3: FinalMatchCard.svelte**

```svelte
<script lang="ts">
	import type { FinalMatchOut } from '$lib/types/wrapup';

	export let finalMatch: FinalMatchOut | null;

	const d = (iso: string | null) =>
		iso ? new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(iso)) : '';
</script>

<div class="stadium-card no-glow flex h-full flex-col p-4">
	{#if finalMatch}
		<div class="flex items-center justify-between gap-2">
			<h2 class="font-display text-sm font-extrabold">The Final · {d(finalMatch.kickoff)}</h2>
			{#if finalMatch.venue}<span class="rounded-badge bg-base-100 px-2 py-0.5 text-[10px] uppercase tracking-wider text-base-content/50">{finalMatch.venue}</span>{/if}
		</div>
		<div class="my-2.5 flex flex-wrap items-center justify-center gap-3">
			<span class="font-display font-extrabold">{finalMatch.home_team}</span>
			<span class="font-display text-2xl font-extrabold text-primary whitespace-nowrap">
				{finalMatch.home_score ?? '–'} – {finalMatch.away_score ?? '–'}
			</span>
			<span class="font-display font-extrabold">{finalMatch.away_team}</span>
		</div>
		{#if finalMatch.went_to_extra_time || finalMatch.penalties}
			<p class="text-center text-[11px] text-base-content/40">
				{finalMatch.went_to_extra_time ? 'after extra time' : ''}{finalMatch.penalties ? ` · ${finalMatch.penalties} on penalties` : ''}
			</p>
		{/if}
		{#if finalMatch.narrative}
			<p class="mt-2 text-[13px] text-base-content/60">{finalMatch.narrative}</p>
		{/if}
	{:else}
		<p class="m-auto text-sm text-base-content/40">The Final hasn't been played yet.</p>
	{/if}
</div>
```

(Use flag-icons spans next to team names if the codebase exposes a helper — grep `flag-icons` usage in results components and copy the idiom; plain names are acceptable v1.)

- [ ] **Step 4: AtlasCard.svelte**

```svelte
<div class="stadium-card no-glow grid h-full content-center gap-1.5 p-4 text-center">
	<!-- Real Atlas logo asset (frontend/static/atlas-logo.svg) once provided -->
	<span class="justify-self-center rounded-lg border-2 border-base-300 bg-base-100 px-4 py-1 font-display text-sm font-extrabold tracking-[.18em]">ATLAS<span class="text-primary">▲</span></span>
	<p class="font-display text-2xl font-extrabold leading-none text-primary">€500</p>
	<p class="text-[13px] text-base-content/60">
		donated to charity by <b class="text-base-content">Atlas Insurance</b>, topping up the pool's own Soup Kitchen donation.
	</p>
	<p class="text-[11px] text-base-content/40">…plus the Adidas Trionda match ball (€150), the runner-up side prize.</p>
</div>
```

- [ ] **Step 5: svelte-check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

```bash
git add frontend/src/lib/components/wrapup/ frontend/src/lib/components/wrapup/WrapUp.svelte
git commit -m "feat(wrapup): bento shell + podium hero + Final card + Atlas card"
```

---

### Task C3: CompareCtaCard, TitleMatrix, FinalLeaderboardTile

**Files:**
- Create: `frontend/src/lib/components/wrapup/CompareCtaCard.svelte`
- Create: `frontend/src/lib/components/wrapup/TitleMatrix.svelte`
- Create: `frontend/src/lib/components/wrapup/FinalLeaderboardTile.svelte`

- [ ] **Step 1: CompareCtaCard**

```svelte
<script lang="ts">
	import { track } from '$lib/analytics';

	export let championEntryId: string | null;
	export let myEntryId: string | null;

	$: href =
		myEntryId && championEntryId ? `/compare?a=${myEntryId}&b=${championEntryId}` : '/compare';
</script>

<div class="grid h-full content-center gap-2 rounded-box border border-primary/45 stadium-card p-4 text-center">
	<span class="text-2xl">🤔</span>
	<h2 class="font-display font-extrabold">Why didn't I win?</h2>
	<p class="text-[13px] text-base-content/55">
		Put your entry side-by-side with the champion's — every pick, every point, and the exact
		moments the title slipped away.
	</p>
	<a
		{href}
		class="btn btn-primary btn-sm justify-self-center"
		on:click={() => track('wrapup_compare_cta_clicked', {})}
	>Compare my entry →</a>
</div>
```

(While /compare is still admin-gated, non-admin members clicking through see its holding stub — acceptable during the preview window; the CTA card only renders for members and the page releases before the Monday email.)

- [ ] **Step 2: TitleMatrix**

Consumes the podium payload for the points/number rows and Plan B's engine for decisive moments (champion vs 2nd, champion vs 3rd, merged and top-3 by |delta|). It fetches the top-3 entries' picks itself (same fan-out as /compare):

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { isAuthenticated } from '$stores/auth';
	import { fixtures, fixtureById } from '$stores/fixtures';
	import { getEntryBonusReads } from '$api/leaderboard';
	import { getMatchPredictions, getBracketPredictions } from '$api/predictions';
	import { getBonusQuestions } from '$api/bonus';
	import { track } from '$lib/analytics';
	import { buildSwings, type ActualAdvancement, type CompareEntryInput } from '$lib/utils/compareEntries';
	import type { FinalPodium, FinalPodiumEntry } from '$lib/types/wrapup';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';

	export let podium: FinalPodium;
	export let rows: LbEntryV4[];
	export let rules: ScoringRules | null;

	$: top3 = podium.entries.slice(0, 3);
	let moments: { label: string; why: string; values: number[] }[] = [];

	// Actual advancement from the fixtures store (per-side seeded check).
	function deriveActual(fx: typeof $fixtures): ActualAdvancement {
		const out: Record<string, Set<string>> = {};
		const real = (t: string | null | undefined) => !!t && !t.startsWith('slot:');
		for (const f of fx) {
			if (f.stage === 'group' || f.stage === 'third_place') continue;
			const set = (out[f.stage] ??= new Set<string>());
			if (real(f.home_team)) set.add(f.home_team);
			if (real(f.away_team)) set.add(f.away_team);
			if (f.stage === 'final' && f.status === 'finished' && f.score) {
				const w = f.score.outcome === '1' ? f.home_team : f.score.outcome === '2' ? f.away_team : null;
				if (w) (out['winner'] ??= new Set()).add(w);
			}
		}
		return out;
	}

	async function loadInput(e: FinalPodiumEntry): Promise<CompareEntryInput> {
		const [m, br, bq, qs] = await Promise.all([
			getMatchPredictions(e.entry_id) as Promise<MatchPredictionWithPoints[]>,
			getBracketPredictions(e.entry_id, 'phase_1'),
			getEntryBonusReads(e.entry_id),
			getBonusQuestions().catch(() => [])
		]);
		return {
			entryId: e.entry_id, displayName: e.user_name, finalRank: e.final_rank,
			totalPoints: e.total_points, groupPoints: e.group_points,
			knockoutPoints: e.knockout_points, bonusPoints: e.bonus_points,
			matches: m, bracket: br, bonusReads: bq,
			questionLabels: new Map(qs.map((q) => [q.id, q.label]))
		};
	}

	onMount(async () => {
		if (top3.length < 2 || !rules) return;
		try {
			const inputs = await Promise.all(top3.map(loadInput));
			const actual = deriveActual($fixtures);
			// swings champion↔2nd and champion↔3rd, merged by label
			const vs2 = buildSwings(inputs[0], inputs[1], $fixtureById, actual, rules);
			const vs3 = inputs[2] ? buildSwings(inputs[0], inputs[2], $fixtureById, actual, rules) : [];
			const byLabel = new Map<string, { label: string; why: string; values: number[] }>();
			for (const s of vs2.slice(0, 6)) {
				byLabel.set(s.label, { label: s.label, why: s.why, values: [s.delta, 0] });
			}
			for (const s of vs3) {
				const hit = byLabel.get(s.label);
				if (hit) hit.values[1] = s.delta;
			}
			moments = [...byLabel.values()].slice(0, 3);
		} catch {
			moments = [];
		}
	});
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">How the title was won</h2>
	<p class="mb-2 text-xs text-base-content/50">The top three side by side — where each entry built its points, and the handful of moments that split them.</p>

	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="text-right text-[10px] uppercase tracking-wider text-base-content/40">
					<th class="text-left"></th>
					{#each top3 as e, i}
						<th class="{i === 0 ? 'bg-primary/10 text-primary rounded-t-lg' : ''} px-2 py-1">
							{i === 0 ? '🏆' : i === 1 ? '🥈' : '🥉'} {e.user_name}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody class="tabular-nums">
				{#each [
					{ label: 'Group stage', get: (e) => e.group_points },
					{ label: 'Knockouts', get: (e) => e.knockout_points },
					{ label: 'Bonus', get: (e) => e.bonus_points }
				] as row}
					{@const vals = top3.map(row.get)}
					{@const best = Math.max(...vals)}
					<tr class="border-t border-base-300/40">
						<td class="py-1.5 max-w-[110px] truncate">{row.label}</td>
						{#each vals as v, i}
							<td class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10' : ''} {v === best ? 'font-bold text-primary' : ''}">{v}</td>
						{/each}
					</tr>
				{/each}
				<tr class="border-t border-primary/40 font-extrabold">
					<td class="py-1.5">Total</td>
					{#each top3 as e, i}
						<td class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10 text-primary' : ''}">{e.total_points}</td>
					{/each}
				</tr>
				{#if moments.length}
					<tr><td colspan={top3.length + 1} class="pt-2.5 pb-0.5 text-[10px] font-bold uppercase tracking-[.12em] text-base-content/40">Decisive moments</td></tr>
					{#each moments as m}
						<tr class="border-t border-base-300/40">
							<td class="py-1.5 max-w-[130px]">
								<span class="block truncate">{m.label}</span>
								<span class="block truncate text-[10px] text-base-content/40">{m.why}</span>
							</td>
							<td class="px-2 py-1.5 text-right bg-primary/10 font-bold text-primary">{m.values[0] > 0 ? '+' : ''}{Math.round(m.values[0] * 10) / 10}</td>
							<td class="px-2 py-1.5 text-right text-base-content/60">ref</td>
							{#if top3.length > 2}
								<td class="px-2 py-1.5 text-right text-base-content/60">{m.values[1] > 0 ? '+' : ''}{Math.round(m.values[1] * 10) / 10}</td>
							{/if}
						</tr>
					{/each}
				{/if}
				<tr>
					<td colspan={top3.length + 1} class="pt-2.5 pb-0.5 text-[10px] font-bold uppercase tracking-[.12em] text-base-content/40">The race in numbers</td>
				</tr>
				{#each [
					{ label: 'Exact scores', get: (e) => e.exact_scores },
					{ label: 'Rarity bonus', get: (e) => e.rarity_points },
					{ label: 'Days at #1', get: (e) => e.days_at_top }
				] as row}
					{@const vals = top3.map(row.get)}
					{@const best = Math.max(...vals)}
					<tr class="border-t border-base-300/40">
						<td class="py-1.5">{row.label}</td>
						{#each vals as v, i}
							<td class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10' : ''} {v === best ? 'font-bold text-primary' : ''}">{v}</td>
						{/each}
					</tr>
				{/each}
				<tr class="border-t border-base-300/40">
					<td class="py-1.5">Champion pick</td>
					{#each top3 as e, i}
						<td class="px-2 py-1.5 text-right text-xs {i === 0 ? 'bg-primary/10' : ''} {e.champion_hit ? 'font-bold text-primary' : 'text-base-content/55'}">
							{e.champion_pick ?? '—'} {e.champion_hit ? '✓' : '✗'}
						</td>
					{/each}
				</tr>
			</tbody>
		</table>
	</div>

	<div class="mt-2 flex flex-wrap items-center justify-between gap-2">
		<span class="text-[11px] text-base-content/40">Gold = best in row · the title was decided in the knockouts</span>
		{#if $isAuthenticated}
			<a href="/compare?a={top3[1]?.entry_id}&b={top3[0]?.entry_id}" class="text-[11px] font-bold text-primary"
				on:click={() => track('wrapup_matrix_compare_clicked', {})}>Full head-to-head → /compare</a>
		{/if}
	</div>
</div>
```

**Guest behaviour (deliberate):** the decisive-moment rows need per-entry
prediction fetches, which stay auth-gated (Spec A §6). For anonymous
visitors those calls 401 → the `catch` leaves `moments = []` and the
section simply doesn't render; the points/race-in-numbers rows come from
the public podium payload and always show. Same for a null
`getScoringRules()` — moments skip, table stands. This is the intended
degradation, not a bug.

**Decisive-moment column semantics** — the mock shows per-entry VALUES per moment (champion / 2nd / 3rd), not deltas. In implementation, replace the `values`/`ref` cells with the actual per-entry points for that element: for a `match` swing, the entry's `points.total` on that fixture; for `bracket`, `hits × per-stage points`; for `bonus`, the entry's points. Extend the engine minimally if needed with an exported `elementValues(inputs, swing, fixtureById, actual, rules): number[]` helper (add a vitest case for it in `compareEntries.test.ts`). Do NOT render deltas in this table — values per column, gold on the best.

- [ ] **Step 3: FinalLeaderboardTile**

```svelte
<script lang="ts">
	import { track } from '$lib/analytics';
	import { rowDisplayName } from '$lib/utils/leaderboardV4';
	import { groupPtsOf, koPtsOf } from '$lib/utils/leaderboardV4';
	import type { LbEntryV4 } from '$lib/types/leaderboard';

	export let rows: LbEntryV4[];
	export let championTeam: string | null;
	export let myUserId: string | null;

	$: multiOwners = (() => {
		const counts = new Map<string, number>();
		for (const r of rows) counts.set(r.user_id, (counts.get(r.user_id) ?? 0) + 1);
		return new Set([...counts].filter(([, n]) => n > 1).map(([id]) => id));
	})();
	$: top10 = rows.slice(0, 10);
</script>

<div class="stadium-card no-glow h-full p-4">
	<div class="mb-1 flex items-center justify-between">
		<h2 class="font-display font-extrabold">Leaderboard</h2>
		<span class="rounded-badge border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">🏁 Final</span>
	</div>
	<p class="mb-2 text-xs text-base-content/50">The board the prizes were paid on — every entry's split and the champion it backed.</p>

	<div class="grid grid-cols-[20px_1fr_40px_44px_48px] items-center gap-1.5 border-b border-base-300/60 pb-1 text-[9px] uppercase tracking-wider text-base-content/40">
		<span></span><span></span><span class="text-right">Grp</span><span class="text-right">KO</span><span class="text-right">Total</span>
	</div>
	{#each top10 as r (r.entry_id)}
		<div class="grid grid-cols-[20px_1fr_40px_44px_48px] items-center gap-1.5 border-b border-base-300/40 py-1 text-[13px] {r.user_id === myUserId ? 'rounded-md bg-primary/5' : ''}">
			<span class="font-display font-extrabold text-base-content/50">{r.position}</span>
			<span class="min-w-0">
				<span class="block truncate {r.position === 1 ? 'font-bold text-primary' : ''}">{rowDisplayName(r, multiOwners)}{r.position === 1 ? ' 🏆' : ''}</span>
				<span class="block text-[10px] {r.champion_pick === championTeam ? 'font-bold text-primary' : 'text-base-content/40'}">
					{r.champion_pick ?? '—'} {r.champion_pick === championTeam ? '✓' : '✗'}
				</span>
			</span>
			<span class="text-right text-xs tabular-nums text-base-content/55">{groupPtsOf(r, r.bonus_group_points)}</span>
			<span class="text-right text-xs tabular-nums text-base-content/55">{koPtsOf(r, r.bonus_knockout_points)}</span>
			<span class="text-right font-display font-extrabold tabular-nums">{r.total_points}</span>
		</div>
	{/each}
	<p class="mt-2 text-center text-[11px] text-base-content/40">
		champion pick under each name · {rows.length} entries ·
		<a href="/leaderboard" class="text-primary" on:click={() => track('wrapup_leaderboard_full_clicked', {})}>standings are final → full table</a>
	</p>
</div>
```

- [ ] **Step 4: check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

```bash
git add frontend/src/lib/components/wrapup/
git commit -m "feat(wrapup): compare CTA, title matrix (shared engine), final leaderboard tile"
```

---

### Task C4: YourTournament, GuestSignInStrip, FeedbackTile

**Files:**
- Create: `frontend/src/lib/components/wrapup/YourTournament.svelte`
- Create: `frontend/src/lib/components/wrapup/GuestSignInStrip.svelte`
- Create: `frontend/src/lib/components/wrapup/FeedbackTile.svelte`
- Modify: `frontend/src/lib/api/feedback.ts` (features param)
- Modify: `frontend/src/lib/analytics/index.ts` (wrapup events)

- [ ] **Step 1: Analytics events**

Add to the `EventName` union:

```ts
	| 'wrapup_viewed'
	| 'wrapup_compare_cta_clicked'
	| 'wrapup_podium_row_clicked'
	| 'wrapup_verified_link_clicked'
	| 'wrapup_matrix_compare_clicked'
	| 'wrapup_leaderboard_full_clicked'
	| 'wrapup_footer_link_clicked'
	| 'wrapup_signin_started'
```

- [ ] **Step 2: YourTournament**

```svelte
<script lang="ts">
	import type { PersonalWrapOut } from '$lib/types/wrapup';

	export let personal: PersonalWrapOut;
	export let poolSize: number;
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">Your tournament — {personal.entry_name}</h2>
	<p class="text-[13px] text-base-content/55">
		{personal.final_rank}{['st','nd','rd'][((personal.final_rank + 90) % 100 - 10) % 10 - 1] ?? 'th'} of {poolSize}
		· <b class="text-base-content">{personal.total_points} pts</b>
		· Group {personal.group_points} / Knockout {personal.knockout_points} / Bonus {personal.bonus_points}
	</p>
	<p class="mt-0.5 text-xs text-base-content/40">Your final standing, and the moments that defined your five weeks — {personal.percentile_label}.</p>

	<div class="mt-2.5 grid gap-2 min-[760px]:grid-cols-3">
		{#each personal.superlatives as s (s.title)}
			<div class="grid gap-0.5 rounded-box border border-primary/30 bg-base-100 px-2.5 py-2">
				<span class="text-lg">{s.emoji}</span>
				<span class="font-display text-[13px] font-extrabold text-primary">{s.title}</span>
				<span class="text-xs text-base-content/55">{s.body}</span>
			</div>
		{/each}
	</div>
</div>
```

(Multi-entry holders: `retro.personal` is a list — v1 renders `personal[0]` (best entry); if the list has >1, add a small switcher row of entry-name chips setting which element renders. Implement the chips — it's six lines — when `personal.length > 1`; WrapUp.svelte passes the full list in that case.)

- [ ] **Step 3: GuestSignInStrip**

Reuses the real `SignInCard` flows — mount the actual component (zero new auth code):

```svelte
<script lang="ts">
	import SignInCard from '$lib/components/SignInCard.svelte';
	import { track } from '$lib/analytics';
</script>

<div class="grid items-center gap-4 rounded-box border border-dashed border-primary/45 bg-primary/5 p-4 min-[760px]:grid-cols-[1.1fr_1fr]"
	on:pointerdown={() => track('wrapup_signin_started', {})}>
	<div class="grid gap-1">
		<h2 class="font-display font-extrabold">In the pool?</h2>
		<p class="text-[13px] text-base-content/55">
			Sign in to see your personal wrap — your final rank, superlatives, and how you compared to the champion.
		</p>
		<p class="text-[11px] text-base-content/40">Not in the pool? Keep scrolling — the whole story is below.</p>
	</div>
	<SignInCard id="wrapup-signin" placement="wrapup" />
</div>
```

(SignInCard brings its own `stadium-card` chrome — if the nesting reads doubled, add a `variant="bare"` prop to SignInCard that skips the outer wrapper; keep the change additive so the landing mount is untouched.)

- [ ] **Step 4: FeedbackTile + feedback API extension**

`frontend/src/lib/api/feedback.ts`:

```ts
export async function sendFeedback(
	rating: number,
	message: string,
	features: string[] = []
): Promise<void> {
	await api.post('/feedback/', { rating, message, features });
}
```

(Existing callers pass two args — the default keeps `RatingPrompt.svelte` untouched.)

`FeedbackTile.svelte` — stars record instantly, chips + text follow:

```svelte
<script lang="ts">
	import { sendFeedback } from '$lib/api/feedback';
	import { markRatingAsked } from '$stores/ratingPrompt';
	import { track } from '$lib/analytics';

	const STARS = [1, 2, 3, 4, 5];
	const FEATURES = [
		{ id: 'leaderboard', label: 'Leaderboard' },
		{ id: 'insights', label: 'Insights' },
		{ id: 'match_detail', label: 'Match detail' },
		{ id: 'compare', label: 'Compare' },
		{ id: 'smart_fill', label: 'Smart Fill' }
	];

	let rating = 0;
	let selected = new Set<string>();
	let message = '';
	let status: 'idle' | 'sending' | 'sent' | 'error' = 'idle';

	function rate(n: number) {
		rating = n;
		markRatingAsked();
		track('app_rating_submitted', { rating: n });
	}

	function toggle(id: string) {
		selected = new Set(selected.has(id) ? [...selected].filter((x) => x !== id) : [...selected, id]);
		track('feature_rated', { feature: id, direction: selected.has(id) ? 'up' : 'off' });
	}

	async function send() {
		if (!rating || status === 'sending') return;
		status = 'sending';
		try {
			await sendFeedback(rating, message.trim() || '(no message)', [...selected]);
			status = 'sent';
			track('feedback_submitted', { rating, has_message: !!message.trim() });
		} catch {
			status = 'error';
		}
	}
</script>

<div class="grid h-full content-start gap-2 rounded-box border border-primary/50 bg-gradient-to-br from-primary/15 to-primary/[.02] p-4 text-center">
	<h2 class="font-display font-extrabold">How was The Predictor?</h2>
	{#if status === 'sent'}
		<p class="m-auto text-sm text-success">Thank you — that shapes the next one. 🙌</p>
	{:else}
		<div class="text-xl leading-none tracking-[.18em]">
			{#each STARS as s}
				<button class="px-0.5 {s <= rating ? 'text-primary' : 'text-base-content/25'}" on:click={() => rate(s)} aria-label={`Rate ${s} stars`}>★</button>
			{/each}
		</div>
		<p class="text-[11px] text-base-content/40">tap a star — your rating is recorded instantly</p>
		{#if rating > 0}
			<div class="flex flex-wrap justify-center gap-1.5">
				{#each FEATURES as f}
					<button
						class="rounded-badge border px-2.5 py-0.5 text-[11px] font-semibold
							{selected.has(f.id) ? 'border-primary/50 bg-primary/15 text-primary' : 'border-base-300/60 text-base-content/55'}"
						on:click={() => toggle(f.id)}
					>{f.label}</button>
				{/each}
			</div>
			<textarea class="textarea textarea-bordered textarea-sm w-full text-left" rows="2" maxlength="2000"
				placeholder="Tell us what to build (or fix) for the next one…" bind:value={message}></textarea>
			<button class="btn btn-primary btn-sm justify-self-center" on:click={send} disabled={status === 'sending'}>
				{status === 'sending' ? 'Sending…' : 'Send feedback'}
			</button>
			{#if status === 'error'}<p class="text-xs text-error">Couldn't send — try again.</p>{/if}
		{/if}
	{/if}
</div>
```

- [ ] **Step 5: check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

```bash
git add frontend/src/lib/components/wrapup/ frontend/src/lib/api/feedback.ts frontend/src/lib/analytics/index.ts
git commit -m "feat(wrapup): personal wrap + guest sign-in strip + tap-to-rate feedback with feature chips"
```

---

### Task C5: PoolVsTournament, ChampionPicksTile, BonusAnswersTile

**Files:**
- Create: `frontend/src/lib/components/wrapup/PoolVsTournament.svelte`
- Create: `frontend/src/lib/components/wrapup/ChampionPicksTile.svelte`
- Create: `frontend/src/lib/components/wrapup/BonusAnswersTile.svelte`

- [ ] **Step 1: PoolVsTournament**

```svelte
<script lang="ts">
	import type { PoolRetrospective } from '$lib/types/wrapup';

	export let retro: PoolRetrospective;

	const STAGE_LABEL: Record<string, string> = {
		round_of_32: 'Round of 32', round_of_16: 'Round of 16',
		quarter_final: 'Quarter-finals', semi_final: 'Semi-finals',
		final: 'Final', winner: 'Winner'
	};
	const pct = (row: { consensus_had: number; of: number }) =>
		row.of ? Math.round((row.consensus_had / row.of) * 100) : 0;
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">The pool vs the tournament</h2>
	<p class="mb-2 text-xs text-base-content/50">How {'{'}pool{'}'} entries read the tournament collectively — what everyone saw coming, and what nobody did.</p>

	<div class="grid grid-cols-1 gap-2 min-[560px]:grid-cols-3">
		<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Group games called right</p>
			<p class="font-display text-xl font-extrabold">{retro.group_called_right} <span class="text-xs text-base-content/40">/ {retro.group_total}</span></p>
			<p class="text-[10px] text-base-content/40">pool majority pick vs result</p>
		</div>
		<div class="rounded-box border border-primary/45 bg-primary/5 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Final called right</p>
			<p class="font-display text-xl font-extrabold">{Math.round(retro.final_called_right_pct * 100)}%</p>
			<p class="text-[10px] text-base-content/40">backed <b class="text-primary">🏆 {retro.final_winner_team ?? '—'}</b> — world champions</p>
		</div>
		<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Exact scores landed</p>
			<p class="font-display text-xl font-extrabold">{retro.exact_total}</p>
			<p class="text-[10px] text-base-content/40">across the pool · {retro.exact_avg_per_entry} per entry</p>
		</div>
	</div>

	<div class="mt-3 grid gap-3 min-[720px]:grid-cols-2">
		{#each [
			{ title: '😱 Biggest collective misses', rows: retro.misses, tone: 'error' },
			{ title: '🏦 Bankers that landed', rows: retro.bankers, tone: 'success' }
		] as col}
			<div>
				<p class="mb-1 font-display text-[13px] font-extrabold">{col.title}</p>
				{#each col.rows as m (m.label)}
					<div class="mt-1 flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs
						{col.tone === 'error' ? 'border-error/25 bg-base-100' : 'border-success/25 bg-base-100'}">
						<span class="flex-none rounded-full px-2 py-0.5 font-display font-extrabold
							{col.tone === 'error' ? 'bg-error/10 text-error' : 'bg-success/10 text-success'}">{Math.round(m.pct * 100)}%</span>
						<span class="min-w-0">
							<span class="block truncate">{m.label}</span>
							<span class="block text-[10px] text-base-content/40">
								{col.tone === 'error' ? `only ${Math.round(m.pct * 100)}% called it` : `${m.exact_count} entries had it exact`}
							</span>
						</span>
					</div>
				{/each}
			</div>
		{/each}
	</div>

	<p class="mt-3 font-display text-[13px] font-extrabold">How far did the pool's bracket faith hold?</p>
	<p class="text-[11px] text-base-content/40">Share of each round's actual line-up the consensus predicted — and the teams it believed in that fell.</p>
	{#each retro.ko_ladder as row (row.stage)}
		<div class="grid grid-cols-[130px_1fr] items-center gap-x-3 gap-y-1 border-b border-base-300/40 py-1.5 last:border-none min-[560px]:grid-cols-[150px_1fr]">
			<span class="flex items-baseline justify-between text-[13px] font-bold">
				{STAGE_LABEL[row.stage] ?? row.stage}
				<span class="font-display">{row.consensus_had}<span class="text-[10px] text-base-content/40">/{row.of}</span></span>
			</span>
			<div class="h-4 overflow-hidden rounded-full border border-base-300/60 bg-base-100">
				<div class="flex h-full items-center justify-end rounded-l-full pr-1.5
					{row.stage === 'final' || row.stage === 'winner' ? 'bg-gradient-to-r from-primary/40 to-primary/80' : 'bg-gradient-to-r from-success/35 to-success/75'}"
					style={`width:${pct(row)}%`}>
					<span class="font-display text-[9px] font-extrabold text-base-100">{pct(row)}%</span>
				</div>
			</div>
			<span class="col-start-2 flex flex-wrap gap-1">
				{#if row.fallen_teams.length}
					{#each row.fallen_teams.slice(0, 3) as t}
						<span class="rounded-full border border-error/25 bg-error/[.06] px-2 py-0.5 text-[10px] font-semibold text-error/85">✕ {t}</span>
					{/each}
					{#if row.fallen_teams.length > 3}
						<span class="rounded-full border border-base-300/60 bg-base-100 px-2 py-0.5 text-[10px] text-base-content/40">+{row.fallen_teams.length - 3} more</span>
					{/if}
				{:else}
					<span class="rounded-full border border-success/25 bg-success/[.06] px-2 py-0.5 text-[10px] font-semibold text-success">
						{row.stage === 'winner' ? "🏆 the pool's favourite lifted it ✓" : 'the pool called them all ✓'}
					</span>
				{/if}
			</span>
		</div>
	{/each}
</div>
```

(Fix the narrative line to interpolate the real entry count: pass `poolSize` as a prop from WrapUp and render "How {poolSize} entries read the tournament…".)

- [ ] **Step 2: ChampionPicksTile**

```svelte
<script lang="ts">
	import type { ChampionPickOut } from '$lib/types/wrapup';

	export let picks: ChampionPickOut[];

	$: max = Math.max(1, ...picks.map((p) => p.count));
	$: actualCount = picks.find((p) => p.is_actual)?.count ?? 0;
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display text-[15px] font-extrabold">Who picked whom — champion</h2>
	<p class="mb-2 text-xs text-base-content/50">Where the pool placed its title faith before a ball was kicked.</p>
	{#each picks as p (p.team)}
		<div class="mt-1.5 grid grid-cols-[92px_1fr_34px] items-center gap-2 text-[13px]">
			<span class="truncate {p.is_actual ? 'font-bold text-primary' : ''}">{p.team} {p.is_actual ? '✓' : ''}</span>
			<div class="h-2.5 overflow-hidden rounded-full bg-base-300/60">
				<div class="h-full rounded-full {p.is_actual ? 'bg-primary' : 'bg-base-content/25'}" style={`width:${(p.count / max) * 100}%`}></div>
			</div>
			<span class="text-right text-xs tabular-nums text-base-content/55">{p.count}</span>
		</div>
	{/each}
	<p class="mt-2 text-[11px] text-base-content/40">{actualCount} entries backed the actual champion.</p>
</div>
```

- [ ] **Step 3: BonusAnswersTile**

```svelte
<script lang="ts">
	import type { BonusAnswerOut } from '$lib/types/wrapup';

	export let bonus: BonusAnswerOut[];

	$: hardest = bonus.length
		? bonus.reduce((a, b) => (a.hit_pct <= b.hit_pct ? a : b))
		: null;
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display text-[15px] font-extrabold">Bonus questions — pool hit rate</h2>
	<p class="mb-2 text-xs text-base-content/50">The four pre-tournament questions, their answers, and how much of the pool called each.</p>
	{#each bonus as q (q.question_id)}
		<div class="mt-1.5 grid grid-cols-[110px_1fr_34px] items-center gap-2 text-[13px]">
			<span class="min-w-0">
				<span class="block truncate">{q.label}</span>
				<span class="block truncate text-[10px] font-bold text-primary">{q.answer_label} ✓</span>
			</span>
			<div class="h-2.5 overflow-hidden rounded-full bg-base-300/60">
				<div class="h-full rounded-full bg-success" style={`width:${Math.round(q.hit_pct * 100)}%`}></div>
			</div>
			<span class="text-right text-xs tabular-nums text-base-content/55">{Math.round(q.hit_pct * 100)}%</span>
		</div>
	{/each}
	{#if hardest}
		<p class="mt-2 text-[11px] text-base-content/40">
			Gold = the correct answer. {hardest.label} was the pool's hardest — {Math.round(hardest.hit_pct * 100)}% got it.
		</p>
	{/if}
</div>
```

- [ ] **Step 4: check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

```bash
git add frontend/src/lib/components/wrapup/
git commit -m "feat(wrapup): pool-vs-tournament, champion picks, bonus answers tiles"
```

---

### Task C6: PointsDnaTile, CharityStrip, banner + finished-state gating

**Files:**
- Create: `frontend/src/lib/components/wrapup/PointsDnaTile.svelte`
- Create: `frontend/src/lib/components/wrapup/CharityStrip.svelte`
- Modify: `frontend/src/lib/components/SiteNoticeBanner.svelte`
- Modify: `frontend/src/routes/leaderboard/+page.svelte` (🏁 pill + polling gate)
- Modify: `frontend/src/lib/components/dashboard/v4/DashboardV4.svelte` (polling gate — belt & braces; dashboard is unmounted post-conclusion anyway)

- [ ] **Step 1: PointsDnaTile**

Reuses `DnaBar.svelte` and `dnaOf` exactly like `InsightsGrid.svelte:283-301`, plus in-bar labels with the ~28px drop rule:

```svelte
<script lang="ts">
	import DnaBar from '$lib/components/leaderboard/v4/DnaBar.svelte';
	import { dnaOf, rowDisplayName } from '$lib/utils/leaderboardV4';
	import type { LbEntryV4 } from '$lib/types/leaderboard';

	export let rows: LbEntryV4[];
	export let myUserId: string | null;

	$: multiOwners = (() => {
		const counts = new Map<string, number>();
		for (const r of rows) counts.set(r.user_id, (counts.get(r.user_id) ?? 0) + 1);
		return new Set([...counts].filter(([, n]) => n > 1).map(([id]) => id));
	})();
	$: own = rows.filter((r) => r.user_id === myUserId);
	$: dnaRows = [...rows.slice(0, 8), ...own.filter((r) => r.position > 8)];
	$: leaderTotal = Math.max(1, rows[0]?.total_points ?? 1);
	const isOwn = (r: LbEntryV4) => r.user_id === myUserId;
</script>

<div class="stadium-card no-glow p-4">
	<h2 class="font-display font-extrabold uppercase tracking-wide">Points DNA</h2>
	<p class="mb-2 text-xs text-base-content/50">
		The anatomy of a winning entry — each bar splits an entry's total into exact scores, results,
		rarity, bracket rounds and bonuses. The top entries built on the same group-stage base; the
		bracket columns are where they pulled apart.
	</p>
	{#each dnaRows as r (r.entry_id)}
		<div class="grid grid-cols-[30px_1fr_52px] items-center gap-2 py-1 min-[720px]:grid-cols-[30px_200px_1fr_52px] {isOwn(r) ? 'rounded-lg bg-primary/5 px-1' : ''}">
			<span class="font-display text-xs font-extrabold text-base-content/40">#{r.position}</span>
			<span class="truncate text-[13px] {isOwn(r) ? 'font-bold' : ''}">{rowDisplayName(r, multiOwners)}</span>
			<span class="col-span-3 block min-[720px]:col-span-1" style={`width:${(r.total_points / leaderTotal) * 100}%`}>
				<DnaBar split={dnaOf(r.breakdown)} />
			</span>
			<span class="hidden text-right font-display text-sm font-extrabold tabular-nums min-[720px]:block">{r.total_points}</span>
		</div>
	{/each}
	<p class="mt-1.5 text-[11px] text-base-content/40">Hover a segment for its exact value.</p>
</div>
```

**In-bar point labels (the approved tweak):** extend `DnaBar.svelte` additively — new prop `labels = false`; when true, each segment `<span>` renders its value centered (`font-display text-[10px] font-extrabold`) and hides the text when the segment is narrower than 28px (measure via `clientWidth` in an action, or approximate with `pct >= 8`). Pass `labels` from this tile only, so the Insights tab is untouched. Keep the existing tooltip.

- [ ] **Step 2: CharityStrip**

```svelte
<script lang="ts">
	import { track } from '$lib/analytics';

	export let isMember: boolean;
</script>

<div class="stadium-card no-glow h-full p-4 text-center text-[13px] text-base-content/60">
	❤️ Where the money went: <b class="text-base-content">€595</b> to the champion ·
	<b class="text-base-content">€183</b> to the group-stage winner ·
	<b class="text-primary">€137</b> Soup Kitchen donation.<br />
	<span class="text-xs">Thank you for playing. See you at the next one.</span>
	<div class="mt-2.5 flex flex-wrap justify-center gap-2">
		<a href="/leaderboard" class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary" on:click={() => track('wrapup_footer_link_clicked', { target: 'leaderboard' })}>Final leaderboard</a>
		{#if isMember}
			<a href="/compare" class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary" on:click={() => track('wrapup_footer_link_clicked', { target: 'compare' })}>Head-to-head compare</a>
		{/if}
		<a href="/results" class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary" on:click={() => track('wrapup_footer_link_clicked', { target: 'results' })}>Results archive</a>
	</div>
</div>
```

- [ ] **Step 3: SiteNoticeBanner re-arm**

In `SiteNoticeBanner.svelte` (lines 16-38 region), make the notice conclusion-aware:

```ts
	import { tournamentConcluded } from '$stores/phase';

	const SITE_NOTICE_ENABLED = true;
	// Post-conclusion wrap-up funnel (2026-07-19). Fresh ID = everyone sees it once.
	const NOTICE_ID = '2026-07-19-wrapup';
	const KEY = `predictor:notice:${NOTICE_ID}:dismissed`;
```

and gate `show` additionally on `$tournamentConcluded` with the new copy:

```svelte
	$: show =
		SITE_NOTICE_ENABLED &&
		$tournamentConcluded &&
		$isAuthenticated &&
		!dismissed &&
		!$page.url.pathname.startsWith('/admin') &&
		$page.url.pathname !== '/';
```

Copy in the markup: `🏆 That's a wrap on WC26 — congratulations to our champion. <a href="/">See the final story & tell us what you thought →</a>`. (The banner deliberately hides on `/` itself — the wrap-up page IS the destination.)

- [ ] **Step 4: Leaderboard finished state**

In `frontend/src/routes/leaderboard/+page.svelte`:
- import `tournamentConcluded` from `$stores/phase`;
- where the live pill / provisional badge renders, add: `{#if $tournamentConcluded}<span class="rounded-badge border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">🏁 Final</span>{:else}<existing live/provisional chrome>{/if}`;
- guard the `startLivePoll(...)` call: `if (!$tournamentConcluded) { <existing start> }` (grep `startLivePoll` in the page; same guard in `DashboardV4.svelte:144-165`).

- [ ] **Step 5: check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors
Run: `docker-compose exec -T frontend-dev npx vitest run` → all pass

```bash
git add frontend/src/lib/components/wrapup/ frontend/src/lib/components/SiteNoticeBanner.svelte frontend/src/routes/leaderboard/+page.svelte frontend/src/lib/components/dashboard/v4/DashboardV4.svelte frontend/src/lib/components/leaderboard/v4/DnaBar.svelte
git commit -m "feat(wrapup): Points DNA + charity tiles, wrap-up banner, finished-state gating"
```

---

### Task C7: Verification — browser, mobile, light mode, guest

- [ ] **Step 1: Overlay + restart dev server**

Copy all changed frontend files to the main worktree; `docker compose restart frontend-dev` (live-server overlay rule).

- [ ] **Step 2: Admin preview walk (desktop)**

Sign in as admin at :5173. Use the preview cluster → Phase: **Post**. Verify every tile renders with real (admin-preview) data: hero podium + honours + verified link → `/rules#verification`; Final card; compare CTA → /compare with `?a=&b=` prefilled; title matrix values match the leaderboard; leaderboard tile splits; personal superlatives (3 cards); feedback star-tap → chips+textarea → send (check backend log for the feedback email w/ features line); pool retrospective numbers; Points DNA labels.

- [ ] **Step 3: Guest walk**

Open :5173 in a private window with the flag flipped in the local DB (`UPDATE competitions SET tournament_concluded = true;` via `docker-compose exec backend python` or psql). Verify: wrap-up renders anonymously, Atlas card sits beside the Final card, sign-in strip renders the real SignInCard, no compare CTA / no feedback tile / no personal card, member-only footer link hidden. Flip the flag back after.

- [ ] **Step 4: Mobile 390px + light mode**

DevTools 390px: podium 3-up, champion-pick meta hidden; matrix scrolls/ellipsizes (name col truncates, all number columns visible); DNA bars drop narrow labels; KO ladder stacks; sign-in strip stacks. Then toggle the theme to **hybrid** and re-walk the page — no hardcoded dark hex, gold reads via `--p` (light-mode checklist rule).

- [ ] **Step 5: Restore main worktree + commit fixes**

`git checkout --` the overlay files in the main worktree (byte-diff first per the overlay memory). Commit any fixes here:

```bash
git add -A
git commit -m "fix(wrapup): verification pass fixes (mobile/light-mode/guest)"
```

---

### Task C8: /rules verification block

**Files:**
- Modify: `frontend/src/routes/rules/+page.svelte` (section 06, ~line 339)

- [ ] **Step 1: Implement**

Inside section 06 ("Provisional Standings"), append an anchored block that renders only when the wrap-up data exists. Load via `getFinalPodium()` in the page's script (it already fetches `info`; add the call, `catch(() => null)`):

```svelte
{#if finalPodium?.audit}
	<div id="verification" class="mt-4 rounded-box border border-success/35 bg-base-100 p-4 scroll-mt-20">
		<p class="mb-1"><span class="rounded-badge border border-success/40 bg-success/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-success">✓ Verified result</span></p>
		<p class="text-sm text-base-content/80">
			<b>How the final result was verified.</b> After the final whistle, every one of the
			<b>{finalPodium.audit.matches_rescored} matches</b>, all bracket advancement credits, and the
			<b>{finalPodium.audit.bonus_questions} bonus questions</b> were re-scored for all
			<b>{finalPodium.audit.entries_verified} entries</b> by an independent run of the scoring engine —
			reading only immutable inputs, never the live database. Recomputed totals matched the leaderboard
			with <b>{finalPodium.audit.discrepancies} discrepancies</b>.
		</p>
		<p class="mt-2 text-xs text-base-content/50">
			Immutable sources: {finalPodium.audit.sources.join(' · ')}. Last audit run: {finalPodium.audit.run_at}.
		</p>
	</div>
{/if}
```

- [ ] **Step 2: check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

```bash
git add frontend/src/routes/rules/+page.svelte
git commit -m "feat(wrapup): /rules#verification renders the audit narrative"
```

---

### Task C9: Release integration (one release, admin-controlled)

Sequenced for the release moment — **build now, execute on the admin's explicit signal**:

1. Merge order: Plan A → Plan B (B1–B3 may merge before A completes; B4 anytime) → Plan C.
2. Full gates: backend `pytest tests/` clean; `npm run check` 0 errors; `npx vitest run` clean.
3. Version bump (minor — `feat`): `frontend/package.json`, `frontend/package-lock.json` (both spots), `backend/pyproject.toml`; changelog entry appended (`type: "feature"`, user-friendly summary: "The tournament finale: a public wrap-up page with the champion's story, your personal highlights, and a head-to-head compare view.").
4. Commit `chore(version): bump to 2.214.0`; push to origin (verify origin/main first — parallel-worktree rule).
5. **STOP. Deploy only on the explicit ship signal.** Post-deploy: `docker compose` rename-conflict grep; admin dress-rehearsal via the preview cluster; audit dry-run from /admin.
6. Finals night runbook (admin): verify final score on /admin/sync → Run final audit → write the Final narrative → flip Tournament conclusion → spot-check / as guest+member → (Monday) release /compare (Plan B Task B5) → send TOURNAMENT_FINAL broadcast.

<!--
	Landing page (/) — public, marketing-driven, with an auth-aware hero
	card that swaps SignInCard ↔ WelcomeBackCard. Composes the 11
	landing components in the order defined by the design handoff:

	  1. StickyTopBar          (outside TrackedSection — anchors scroll)
	  2. Hero                  + auth-aware card
	  3. CountdownBand         live ticker with urgency tiers
	  4. HowItWorks            3 numbered steps
	  5. EntryDepth            quick / tinker / unlimited entries
	  6. ScoringAtAGlance      +5 / +10 / rarity, compact panel
	  7. StakesBanner          €600 / charity / bragging rights
	  8. FromTheTouchline      featured + grid + all-headlines tile
	  9. FinalCTABand          closing "Ready to pick?" call
	  10. ThemeTogglePill       fixed bottom-right toggle
	  (Site footer is rendered globally by +layout.svelte for every
	  non-wizard route — no longer landing-specific.)

	Server load (+page.server.ts) provides total_players, phase1Deadline,
	firstKickoff, and news[]. Each value has a documented null/empty
	fallback in the component that consumes it — backend or RSS failures
	degrade gracefully, never break the page.

	Analytics:
	  - landing_view fires once on mount (auth_state, referrer).
	  - section_viewed fires per <TrackedSection> on first ≥50% visibility.
	  - cta_clicked, signin_*, news_card_clicked, countdown_phase fire
	    from their respective components.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { loadEntries } from '$stores/entries';
	import { phase1Deadline, postDeadlineLive, tournamentConcluded } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { track } from '$lib/analytics';
	import { resolveHomeView, type HomeView, type PhaseOverride } from '$lib/utils/wrapupView';

	import DashboardV4 from '$lib/components/dashboard/v4/DashboardV4.svelte';
	import LockedInHero from '$lib/components/dashboard/v4/LockedInHero.svelte';
	import WrapUp from '$lib/components/wrapup/WrapUp.svelte';

	import StickyTopBar from '$lib/components/landing/StickyTopBar.svelte';
	import LandingHero from '$lib/components/landing/LandingHero.svelte';
	import TypographicHero from '$lib/components/landing/TypographicHero.svelte';
	import HowItWorks from '$lib/components/landing/HowItWorks.svelte';
	import FaqSection from '$lib/components/landing/FaqSection.svelte';
	import EntryDepth from '$lib/components/landing/EntryDepth.svelte';
	import ScoringAtAGlance from '$lib/components/landing/ScoringAtAGlance.svelte';
	import StakesBanner from '$lib/components/landing/StakesBanner.svelte';
	import FromTheTouchline from '$lib/components/landing/FromTheTouchline.svelte';
	import FinalCTABand from '$lib/components/landing/FinalCTABand.svelte';
	import ThemeTogglePill from '$lib/components/landing/ThemeTogglePill.svelte';
	import TrackedSection from '$lib/components/landing/TrackedSection.svelte';

	import type { PageData } from './$types';

	export let data: PageData;

	// ── Home-page view model (v2.166.0, extended v2.21x.0 with a fourth
	// 'wrapup' state) ──
	//
	// Four variants (resolved by the pure `resolveHomeView` dispatcher in
	// $lib/utils/wrapupView.ts — unit-tested there):
	//   'wrapup'  — post-tournament wrap-up page (public once concluded)
	//   'dash'    — V4 Dashboard (signed-in, released by the admin)
	//   'holding' — post-deadline, pre-release: "you're locked in" card
	//   'landing' — the marketing page (guests + pre-deadline users)
	//
	// The deadline passing does NOT release the dashboard — the admin
	// flips the go-live switch on /admin after the close-out clean-up
	// (`competitions.post_deadline_live`, read via phase-status). Admins
	// always see the dashboard, with a floating toggle to preview what
	// the pool currently sees. Flip the const to false for a 60-second
	// rollback to the marketing landing.
	//
	// The deadline reads the phase store with the server-load value as a
	// pre-hydration fallback, so a signed-in user doesn't flash the
	// marketing page while /competition/phase-status resolves.
	const V4_DASHBOARD_ENABLED = true;
	const ADMIN_VIEW_KEY = 'predictor:admin:view';
	const ADMIN_PHASE_OVERRIDE_KEY = 'predictor:admin:phase-override';
	// Svelte template expressions are plain JS, not TS (CLAUDE.md gotcha) —
	// an inline `as PhaseOverride[]` literal inside {#each} would fail to
	// compile, so the option list is a typed script const instead.
	const PHASE_OPTIONS: PhaseOverride[] = ['auto', 'pre', 'during', 'post'];
	let adminPreviewPool = false;
	let phaseOverride: PhaseOverride = 'auto';
	onMount(() => {
		adminPreviewPool = localStorage.getItem(ADMIN_VIEW_KEY) === 'pool';
		const stored = localStorage.getItem(ADMIN_PHASE_OVERRIDE_KEY);
		if (stored === 'pre' || stored === 'during' || stored === 'post') {
			phaseOverride = stored;
		}
	});
	function setAdminPreviewPool(next: boolean) {
		adminPreviewPool = next;
		localStorage.setItem(ADMIN_VIEW_KEY, next ? 'pool' : 'admin');
	}
	function setPhaseOverride(next: PhaseOverride) {
		phaseOverride = next;
		localStorage.setItem(ADMIN_PHASE_OVERRIDE_KEY, next);
	}

	$: effectiveDeadline = $phase1Deadline ?? data.phase1Deadline;
	$: deadlinePassed =
		!!effectiveDeadline && new Date(effectiveDeadline).getTime() < Date.now();
	// V4_DASHBOARD_ENABLED is the master kill switch for the whole V4
	// home-view system (dashboard + admin phase-preview cluster) — folded
	// into both inputs below so flipping it false reproduces the old
	// unconditional "everyone sees landing/holding" rollback behavior,
	// including for admins (who'd otherwise still hit the isAdmin-dash
	// branch inside resolveHomeView's 'auto' path).
	let view: HomeView = 'landing';
	$: view = resolveHomeView({
		isAuthenticated: $isAuthenticated,
		isAdmin: $user?.is_admin === true && V4_DASHBOARD_ENABLED,
		adminPreviewPool,
		phaseOverride,
		deadlinePassed,
		postDeadlineLive: V4_DASHBOARD_ENABLED && $postDeadlineLive,
		tournamentConcluded: $tournamentConcluded
	});

	onMount(() => {
		// Empty so the logo alone carries the brand and doesn't collide with the countdown pill on narrow viewports.
		pageTitle.set('');
		track('landing_view', {
			auth_state: $isAuthenticated ? 'authenticated' : 'guest',
			referrer: typeof document !== 'undefined' ? document.referrer || 'direct' : 'direct'
		});
	});

	// Hydrate entries so the WelcomeBackCard reflects real state on a
	// fresh post-magic-link landing. Root +layout.svelte only fetches
	// phase status on auth; entries hydration was previously gated
	// behind a /entries navigation, which made the landing card silently
	// report 0 entries for new sessions.
	let hasLoadedLanding = false;
	$: if ($isAuthenticated && $user?.id && !hasLoadedLanding && view === 'landing') {
		hasLoadedLanding = true;
		void loadEntries($user.id);
	}
</script>

<svelte:head>
	<title>Atlas World Cup 2026 Pools — Pick every match. Beat every friend.</title>
	<meta
		name="description"
		content="A blind-pool World Cup 2026 prediction competition. Pick scores, build a bracket, watch every match like it matters. €600 pot last year, a cut to charity."
	/>
</svelte:head>

<!--
	StickyTopBar and ThemeTogglePill are guest-only: authenticated users
	already get the layout's app top bar + a theme toggle elsewhere in
	`+layout.svelte`, so rendering the landing's versions would visibly
	stack two top bars and surface two toggles. Keep the components pure
	(no auth coupling inside them) — the page composer owns the gate.
-->
{#if view === 'wrapup'}
	<!-- Post-tournament wrap-up page (Plan C) — public once the admin
	     flips Competition.tournament_concluded, or previewable any time
	     via the admin phase-override cluster below. -->
	<WrapUp />
{:else if view === 'dash'}
	<!-- Signed-in landing: the V4 Dashboard (v2.165.0). The Touchline
	     news band rides along below it — same server-loaded RSS feed
	     (and the same section_viewed analytics) as the marketing page. -->
	<DashboardV4 />
	<!-- data.news is a STREAMED promise (see +page.server.ts) — the page
	     paints immediately and the news band pops in when the feeds
	     resolve. No pending skeleton: it's the last section on the page. -->
	<TrackedSection name="news">
		{#await data.news then news}
			<FromTheTouchline {news} />
		{/await}
	</TrackedSection>
{:else if view === 'holding'}
	<!-- Post-deadline, pre-release: the pool is sealed, the admin
	     hasn't flipped the go-live switch yet. -->
	<LockedInHero />
	<TrackedSection name="news">
		{#await data.news then news}
			<FromTheTouchline {news} />
		{/await}
	</TrackedSection>
{:else}
	{#if !$isAuthenticated}
		<StickyTopBar />
	{/if}

	<TrackedSection name="hero">
		<LandingHero phase1Deadline={data.phase1Deadline} />
	</TrackedSection>

	<TrackedSection name="typography">
		<TypographicHero totalPlayers={data.totalPlayers} phase1Deadline={data.phase1Deadline} />
	</TrackedSection>

	<TrackedSection name="how_it_works">
		<HowItWorks />
	</TrackedSection>

	<TrackedSection name="entry_depth">
		<EntryDepth />
	</TrackedSection>

	<TrackedSection name="scoring">
		<ScoringAtAGlance />
	</TrackedSection>

	<TrackedSection name="faq">
		<FaqSection phase1Deadline={data.phase1Deadline} />
	</TrackedSection>

	<TrackedSection name="stakes">
		<StakesBanner />
	</TrackedSection>

	<TrackedSection name="news">
		{#await data.news then news}
			<FromTheTouchline {news} />
		{/await}
	</TrackedSection>

	<TrackedSection name="final_cta">
		<FinalCTABand />
	</TrackedSection>

	<!-- SiteFooter now renders globally via +layout.svelte — no longer
	     mounted here. Removed 2026-06-01 to avoid double-render. -->

	{#if !$isAuthenticated}
		<ThemeTogglePill />
	{/if}
{/if}

{#if $isAuthenticated && $user?.is_admin === true && V4_DASHBOARD_ENABLED}
	<!-- Admin-only preview cluster: Audience toggle (admin view vs. exactly
	     what the pool currently sees) + Phase override (force-preview the
	     pre/during/post-tournament state regardless of the real deadline/
	     conclusion flags). Sits above the mobile bottom nav; bordered
	     chrome per the sticky-bar clipping rule. -->
	<div
		class="fixed bottom-20 right-4 z-40 rounded-box border border-base-300/70 bg-base-200 p-2.5 text-[11px] shadow-card min-[700px]:bottom-6"
	>
		<p class="mb-1 text-[9px] font-bold uppercase tracking-wider text-base-content/50">
			👁 Preview
		</p>
		<div class="mb-1 flex items-center gap-1">
			<span class="w-14 text-base-content/50">Audience</span>
			{#each [{ v: false, l: 'Admin' }, { v: true, l: 'Pool' }] as o}
				<button
					type="button"
					class="rounded-badge px-2 py-0.5 font-bold {adminPreviewPool === o.v
						? 'bg-primary/15 text-primary'
						: 'text-base-content/60'}"
					on:click={() => setAdminPreviewPool(o.v)}
				>{o.l}</button>
			{/each}
		</div>
		<div class="flex items-center gap-1">
			<span class="w-14 text-base-content/50">Phase</span>
			{#each PHASE_OPTIONS as p}
				<button
					type="button"
					class="rounded-badge px-2 py-0.5 font-bold capitalize {phaseOverride === p
						? 'bg-primary/15 text-primary'
						: 'text-base-content/60'}"
					on:click={() => setPhaseOverride(p)}
				>{p}</button>
			{/each}
		</div>
		{#if phaseOverride !== 'auto'}
			<p class="mt-1 text-[10px] text-primary">
				previewing: {phaseOverride} · tap Auto to reset
			</p>
		{/if}
	</div>
{/if}

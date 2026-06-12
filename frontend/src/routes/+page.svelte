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
	import { phase1Deadline, postDeadlineLive } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { track } from '$lib/analytics';

	import DashboardV4 from '$lib/components/dashboard/v4/DashboardV4.svelte';
	import LockedInHero from '$lib/components/dashboard/v4/LockedInHero.svelte';

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

	// ── Home-page view model (v2.166.0) ──
	//
	// Three variants:
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
	let adminPreviewPool = false;
	onMount(() => {
		adminPreviewPool = localStorage.getItem(ADMIN_VIEW_KEY) === 'pool';
	});
	function toggleAdminView() {
		adminPreviewPool = !adminPreviewPool;
		localStorage.setItem(ADMIN_VIEW_KEY, adminPreviewPool ? 'pool' : 'admin');
	}

	type HomeView = 'landing' | 'holding' | 'dash';
	$: effectiveDeadline = $phase1Deadline ?? data.phase1Deadline;
	$: deadlinePassed =
		!!effectiveDeadline && new Date(effectiveDeadline).getTime() < Date.now();
	// What a non-admin sees right now.
	let poolView: HomeView = 'landing';
	$: poolView = !$isAuthenticated
		? 'landing'
		: V4_DASHBOARD_ENABLED && $postDeadlineLive
		? 'dash'
		: deadlinePassed
		? 'holding'
		: 'landing';
	let view: HomeView = 'landing';
	$: view =
		$isAuthenticated && $user?.is_admin === true && V4_DASHBOARD_ENABLED && !adminPreviewPool
			? 'dash'
			: poolView;

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
{#if view === 'dash'}
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
	<!-- Admin-only: flip between the admin view (dashboard) and exactly
	     what the pool currently sees (landing / holding / dashboard,
	     depending on deadline + go-live state). Sits above the mobile
	     bottom nav; bordered chrome per the sticky-bar clipping rule. -->
	<button
		type="button"
		class="fixed bottom-20 right-4 z-40 flex items-center gap-1.5 rounded-btn border border-base-300/70 bg-base-200 px-3 py-1.5 text-[11px] font-bold text-base-content/80 shadow-card transition-colors hover:border-primary/50 min-[700px]:bottom-6"
		on:click={toggleAdminView}
	>
		<span aria-hidden="true">👁</span>
		{adminPreviewPool ? 'Viewing as pool — back to admin view' : 'View as pool'}
	</button>
{/if}

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
	import { pageTitle } from '$stores/pageTitle';
	import { track } from '$lib/analytics';

	import StickyTopBar from '$lib/components/landing/StickyTopBar.svelte';
	import PrizeHero from '$lib/components/landing/PrizeHero.svelte';
	import LandingHero from '$lib/components/landing/LandingHero.svelte';
	import CountdownBand from '$lib/components/landing/CountdownBand.svelte';
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
	$: if ($isAuthenticated && $user?.id && !hasLoadedLanding) {
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
{#if !$isAuthenticated}
	<StickyTopBar />
{/if}

<TrackedSection name="prize">
	<PrizeHero />
</TrackedSection>

<TrackedSection name="hero">
	<LandingHero totalPlayers={data.totalPlayers} phase1Deadline={data.phase1Deadline} />
</TrackedSection>

<TrackedSection name="countdown">
	<CountdownBand phase1Deadline={data.phase1Deadline} />
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
	<FromTheTouchline news={data.news} />
</TrackedSection>

<TrackedSection name="final_cta">
	<FinalCTABand />
</TrackedSection>

<!-- SiteFooter now renders globally via +layout.svelte — no longer
     mounted here. Removed 2026-06-01 to avoid double-render. -->

{#if !$isAuthenticated}
	<ThemeTogglePill />
{/if}

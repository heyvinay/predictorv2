<!--
  PreTournamentLanding — the home page we ship for guests + members who
  haven't hit the phase 1 lock. Mounted by the landing dispatcher in
  +page.svelte when $uxPhase === 'pre_tournament'.

  Composition is unchanged from the previous +page.svelte body — this
  component is a relocation, not a rewrite.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { loadEntries } from '$stores/entries';
	import { pageTitle } from '$stores/pageTitle';
	import { track } from '$lib/analytics';

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

	import type { PageData } from '../../../routes/$types';

	export let data: PageData;

	onMount(() => {
		pageTitle.set('');
		track('landing_view', {
			auth_state: $isAuthenticated ? 'authenticated' : 'guest',
			referrer: typeof document !== 'undefined' ? document.referrer || 'direct' : 'direct'
		});
	});

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
	<FromTheTouchline news={data.news} />
</TrackedSection>

<TrackedSection name="final_cta">
	<FinalCTABand />
</TrackedSection>

{#if !$isAuthenticated}
	<ThemeTogglePill />
{/if}

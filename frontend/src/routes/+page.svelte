<!--
  Landing dispatcher. Routes / to one of three phase-specific home
  components based on $uxPhase (see frontend/src/lib/stores/phase.ts):

    pre_tournament    → PreTournamentLanding (current marketing landing)
    during_tournament → DuringTournamentLanding (mission-control dashboard)
    post_competition  → PostTournamentLanding (final standings)

  Uses <svelte:component this={...}> rather than {#if}/{:else if} chain.
  Lifted from upstream (laarohi/predictorv2 +page.svelte). Their
  documented rationale: the if-chain interacted badly with svelte-hmr's
  proxy layer on the largest dashboard and produced a recursive
  proxy-instantiation loop (Maximum call stack size exceeded in
  scheduler.flush). The single mount point avoids it and reads cleaner.

  The dispatcher does NO data fetching — each phase component owns its
  own loads. Pre-tournament users don't pay for during-tournament
  endpoint calls.
-->
<script lang="ts">
	import { uxPhase } from '$stores/phase';
	import type { UxPhase } from '$types';
	import type { ComponentType } from 'svelte';

	import PreTournamentLanding from '$lib/components/landing/PreTournamentLanding.svelte';
	import DuringTournamentLanding from '$lib/components/landing/DuringTournamentLanding.svelte';
	import PostTournamentLanding from '$lib/components/landing/PostTournamentLanding.svelte';

	import type { PageData } from './$types';

	export let data: PageData;

	const DASHBOARDS: Record<UxPhase, ComponentType> = {
		pre_tournament: PreTournamentLanding,
		during_tournament: DuringTournamentLanding,
		post_competition: PostTournamentLanding
	};

	$: ActiveDashboard = DASHBOARDS[$uxPhase];
</script>

{#if ActiveDashboard}
	<svelte:component this={ActiveDashboard} {data} />
{/if}

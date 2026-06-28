<script lang="ts">
	/** Group Standings standalone page (v2.181.1, refactored 2.181.2).
	 *
	 *  Thin wrapper around GroupStandingsView — same view also surfaces as
	 *  the "Group Standings" tab on /results. Gated by post-deadline release
	 *  (admins always see; non-admins wait for /admin "Go live" flip).
	 */
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import { postDeadlineLive } from '$stores/phase';
	import { getActualStandings } from '$api/fixtures';
	import { startLivePoll } from '$lib/utils/livePoll';
	import type { ActualStandingsResponse } from '$types';
	import GroupStandingsView from '$lib/components/results/v4/GroupStandingsView.svelte';

	$: if (!$isAuthenticated) goto('/login');

	const STANDINGS_ENABLED = true;
	$: standingsOpen = STANDINGS_ENABLED && ($user?.is_admin === true || $postDeadlineLive);

	let loading = true;
	let payload: ActualStandingsResponse | null = null;
	let loadError: string | null = null;
	let lastUpdatedAt: Date | null = null;

	async function loadStandings() {
		try {
			payload = await getActualStandings();
			lastUpdatedAt = new Date();
			loadError = null;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load standings';
		} finally {
			loading = false;
		}
	}

	let dataRequested = false;
	$: if (standingsOpen && !dataRequested) {
		dataRequested = true;
		void loadStandings();
	}

	let stopPoll: (() => void) | null = null;
	onMount(() => {
		stopPoll = startLivePoll(() => {
			if (standingsOpen) void loadStandings();
		});
	});
	onDestroy(() => {
		stopPoll?.();
	});
</script>

<svelte:head>
	<title>Group Standings — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !standingsOpen}
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Standings open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					Live group tables go live once the tournament begins.
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{:else if $isAuthenticated}
	<div class="container mx-auto mobile-padding max-w-[1180px] py-4">
		<header class="mb-6">
			<h1 class="font-display text-3xl sm:text-4xl tracking-wide">Group Standings</h1>
			<p class="mt-1 text-sm text-base-content/60">
				Live group tables from finished match results. Top two in each group qualify
				directly; the best eight third-placed teams join them in the Round of 32.
			</p>
		</header>

		<GroupStandingsView
			{payload}
			{loading}
			error={loadError}
			{lastUpdatedAt}
		/>
	</div>
{/if}

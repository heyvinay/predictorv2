<!--
  PostTournamentLanding — final-finished state. Mounted by the landing
  dispatcher when uxPhase === 'post_competition' (final fixture finished).

  Today: champion podium (top 3) + top 10 leaderboard list. The full
  retrospective (highlights, biggest climb, best phase, memorial strip)
  lands in a follow-up release — those need backend endpoints we don't
  have yet (/me/highlights doesn't exist in our fork).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { getLeaderboard } from '$api/leaderboard';
	import type { LeaderboardEntry } from '$types';
	import MissionChampionPodium from './mc/MissionChampionPodium.svelte';

	let leaderboard: LeaderboardEntry[] = [];
	let loaded = false;

	onMount(async () => {
		try {
			const resp = await getLeaderboard();
			leaderboard = resp.entries;
		} finally {
			loaded = true;
		}
	});

	$: top3 = leaderboard.slice(0, 3);
	$: rest = leaderboard.slice(3, 10);
</script>

<svelte:head>
	<title>Tournament Complete — Atlas World Cup 2026 Pools</title>
</svelte:head>

<section class="max-w-[1200px] mx-auto mobile-padding py-10 sm:py-14">
	<p class="text-xs font-mono uppercase tracking-[0.18em] text-primary mb-3">
		Tournament Complete
	</p>
	<h1 class="font-hero text-[clamp(36px,7vw,96px)] leading-[0.9] text-base-content mb-2">
		Final standings.
	</h1>
	<p class="text-base-content/70 max-w-prose">
		Thanks for playing. The full retrospective — highlights, biggest climbs,
		per-source breakdown — lands in the next release.
	</p>

	{#if !loaded}
		<p class="mt-8 text-base-content/55">Loading the final leaderboard…</p>
	{:else if top3.length > 0}
		<MissionChampionPodium {top3} />

		{#if rest.length > 0}
			<ol class="mt-8 stadium-card no-glow p-6 space-y-1">
				{#each rest as row, i (row.entry_id)}
					<li
						class="flex items-baseline justify-between gap-4 py-2 border-b border-base-300/40 last:border-0"
					>
						<span class="font-display font-extrabold text-xl text-base-content/72 w-10">
							{i + 4}
						</span>
						<span class="flex-1 font-display font-semibold">{row.entry_name}</span>
						<span class="text-base-content/55 text-sm hidden sm:inline">{row.user_name}</span>
						<span class="font-display font-extrabold text-lg tabular-nums">{row.total_points}</span>
					</li>
				{/each}
			</ol>
		{/if}
	{:else}
		<p class="mt-8 text-base-content/55">No entries to display.</p>
	{/if}
</section>

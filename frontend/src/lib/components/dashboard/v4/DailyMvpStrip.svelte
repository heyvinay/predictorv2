<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getDailyMvps } from '$lib/api/leaderboard';
	import type { DailyMvp } from '$lib/types/leaderboard';
	import MvpChip from './MvpChip.svelte';

	const dispatch = createEventDispatcher<{ open: { entry_id: string } }>();

	let mvps: DailyMvp[] = [];
	let loading = true;
	let failed = false;

	function todayIso(): string {
		return new Date().toISOString().slice(0, 10);
	}

	onMount(async () => {
		try {
			const data = await getDailyMvps();
			mvps = data.mvps;
		} catch {
			failed = true;
		} finally {
			loading = false;
		}
	});

	$: today = todayIso();
	// Grid sizes to however many days actually have an MVP so far (1-3,
	// early in the tournament) instead of always reserving 3 columns and
	// leaving dead cells. A lone entry also gets a width cap so it reads
	// as a normal card instead of stretching across the whole row.
	$: mvpCount = mvps.slice(0, 3).length;
	$: gridColsClass =
		mvpCount === 1 ? 'grid-cols-1 max-w-[220px]' : mvpCount === 2 ? 'grid-cols-2' : 'grid-cols-3';
</script>

{#if !loading && !failed && mvps.length > 0}
	<!--
		v2.181.0 — compacted to 3 chips in a 3-column grid (was 5 chips
		flex-wrapped). Lives in the dashboard's side column above the
		MiniLeaderboard now, not at the top of the page. Column count
		tracks the actual entry count (see gridColsClass) so early in the
		tournament — when there are only 1-2 days of MVP data — the grid
		doesn't leave empty cells.
	-->
	<section class="rounded-box border border-base-300 bg-base-200 p-3">
		<header class="mb-2 flex items-center gap-2">
			<h3 class="m-0 text-[10.5px] font-bold uppercase tracking-wide text-primary">Daily MVP · last 3 days</h3>
		</header>
		<div class="grid {gridColsClass} gap-2">
			{#each mvps.slice(0, 3) as mvp (mvp.captured_date)}
				<MvpChip
					{mvp}
					isToday={mvp.captured_date === today}
					on:open={e => dispatch('open', e.detail)}
				/>
			{/each}
		</div>
	</section>
{/if}

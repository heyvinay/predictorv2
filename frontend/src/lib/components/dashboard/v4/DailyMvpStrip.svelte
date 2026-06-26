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
</script>

{#if !loading && !failed && mvps.length > 0}
	<!--
		v2.181.0 — compacted to 3 chips in a 3-column grid (was 5 chips
		flex-wrapped). Lives in the dashboard's side column above the
		MiniLeaderboard now, not at the top of the page. The 3-col grid
		works the same on mobile and desktop — same chronological order
		(today + 2 prior days), no wrap to a second row.
	-->
	<section class="rounded-box border border-base-300 bg-base-200 p-3">
		<header class="mb-2 flex items-center gap-2">
			<h3 class="m-0 text-[10.5px] font-bold uppercase tracking-wide text-primary">Daily MVP · last 3 days</h3>
		</header>
		<div class="grid grid-cols-3 gap-2">
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

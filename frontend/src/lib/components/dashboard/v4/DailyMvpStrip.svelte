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
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Daily MVP — last 5 days</h3>
		</header>
		<div class="flex flex-wrap gap-2.5">
			{#each mvps as mvp (mvp.captured_date)}
				<MvpChip
					{mvp}
					isToday={mvp.captured_date === today}
					on:open={e => dispatch('open', e.detail)}
				/>
			{/each}
		</div>
	</section>
{/if}

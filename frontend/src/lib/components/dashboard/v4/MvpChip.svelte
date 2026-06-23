<script lang="ts">
	import type { DailyMvp } from '$lib/types/leaderboard';
	import { composeRankDelta } from '$lib/utils/leaderboardV4';
	import { createEventDispatcher } from 'svelte';

	export let mvp: DailyMvp;
	export let isToday: boolean = false;

	const dispatch = createEventDispatcher<{ open: { entry_id: string } }>();

	$: dateLabel = isToday
		? `Today · ${formatShort(mvp.captured_date)}`
		: formatShort(mvp.captured_date);

	function formatShort(iso: string): string {
		const d = new Date(iso + 'T00:00:00Z');
		return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric', timeZone: 'UTC' });
	}
</script>

<button
	type="button"
	class="flex-[1_1_200px] min-w-[180px] rounded-box border bg-base-100 p-3 text-left
		   hover:border-primary/50 transition-colors
		   {isToday ? 'border-primary/40 bg-primary/15' : 'border-base-300'}"
	on:click={() => dispatch('open', { entry_id: mvp.subject_entry_id })}
>
	<div class="text-[11px] font-bold tracking-wide uppercase text-base-content/40">{dateLabel}</div>
	<div class="mt-1 mb-0.5 text-sm font-bold">{mvp.user_name}</div>
	<div class="flex gap-3 text-xs text-base-content/55">
		<span><span class="text-success font-bold">+{mvp.day_points}</span> pts</span>
		<span class={mvp.rank_delta < 0 ? 'text-error font-bold' : 'text-primary font-bold'}>
			{composeRankDelta(mvp.rank_delta)}
		</span>
	</div>
</button>

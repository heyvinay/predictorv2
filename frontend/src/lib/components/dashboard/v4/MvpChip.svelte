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

<!--
	v2.181.0 — compacted from the original "200px-min, flex-wrap" sizing
	(v2.179.0) to fit a 3-column grid in the dashboard's narrow side
	column. Smaller padding + smaller font keeps each chip readable at
	~110-140px wide. Today's chip retains the gold-tinted accent.
-->
<button
	type="button"
	class="min-w-0 rounded-box border bg-base-100 p-2 text-left
		   hover:border-primary/50 transition-colors
		   {isToday ? 'border-primary/40 bg-primary/15' : 'border-base-300'}"
	on:click={() => dispatch('open', { entry_id: mvp.subject_entry_id })}
>
	<div class="text-[9.5px] font-bold tracking-wide uppercase text-base-content/40 truncate">{dateLabel}</div>
	<div class="mt-0.5 text-[12.5px] font-bold leading-tight truncate">{mvp.user_name}</div>
	<div class="mt-0.5 flex gap-2 text-[10.5px] text-base-content/55">
		<span><span class="text-success font-bold">+{mvp.day_points}</span> pts</span>
		<span class={mvp.rank_delta < 0 ? 'text-error font-bold' : 'text-primary font-bold'}>
			{composeRankDelta(mvp.rank_delta)}
		</span>
	</div>
</button>

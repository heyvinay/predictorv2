<script lang="ts">
	/** Movers since yesterday — two columns of the biggest daily rank
	 *  climbers and sliders (max 5 each), labelled via THE naming rule. */
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { moversOf } from '$lib/utils/dashboardV4';

	export let rows: LbEntryV4[];

	$: ({ climbing, sliding } = moversOf(rows, 5));
</script>

<section class="rounded-box border border-base-300/70 bg-base-200 p-3.5">
	<h2 class="font-display text-lg font-bold tracking-wide text-base-content">
		Movers · since yesterday
	</h2>
	<p class="mt-0.5 text-[11.5px] text-base-content/55">Daily snapshot vs the live table</p>

	<div class="mt-3 grid grid-cols-2 gap-4">
		<div class="flex min-w-0 flex-col gap-1.5">
			<span class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-success"
				>▲ Climbing</span
			>
			{#each climbing as m (m.entry_id)}
				<span class="flex items-baseline justify-between gap-2">
					<span class="truncate text-[12px] font-semibold text-base-content/85">{m.label}</span>
					<span class="flex-none font-display text-[12px] font-extrabold text-success"
						>+{m.move}</span
					>
				</span>
			{:else}
				<span class="text-[11px] text-base-content/40">No climbers today</span>
			{/each}
		</div>
		<div class="flex min-w-0 flex-col gap-1.5">
			<span class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-error"
				>▼ Sliding</span
			>
			{#each sliding as m (m.entry_id)}
				<span class="flex items-baseline justify-between gap-2">
					<span class="truncate text-[12px] font-semibold text-base-content/85">{m.label}</span>
					<span class="flex-none font-display text-[12px] font-extrabold text-error">{m.move}</span>
				</span>
			{:else}
				<span class="text-[11px] text-base-content/40">No sliders today</span>
			{/each}
		</div>
	</div>
</section>

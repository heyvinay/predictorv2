<script lang="ts">
	import { track } from '$lib/analytics';
	import type { PersonalWrapOut } from '$lib/types/wrapup';

	/** First (or only) personal wrap — kept as its own prop so callers with
	 *  a single entry don't need to build a one-item array. */
	export let personal: PersonalWrapOut;
	/** Every entry the signed-in owner holds (v2.214.0 multi-entry support).
	 *  Defaults to just `personal` so single-entry callers keep working
	 *  unchanged. When this has more than one item, a chip row lets the
	 *  viewer switch which entry's wrap is displayed. */
	export let allPersonal: PersonalWrapOut[] = [personal];
	export let poolSize: number;

	let selectedIdx = 0;
	// If the entry list changes (e.g. data reloads), keep the index in
	// bounds rather than pointing at a stale/missing entry.
	$: if (selectedIdx >= allPersonal.length) selectedIdx = 0;
	$: current = allPersonal[selectedIdx] ?? personal;

	function selectEntry(i: number) {
		selectedIdx = i;
		track('wrapup_entry_switched', { index: i });
	}

	function ordinal(n: number): string {
		const mod100 = n % 100;
		if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
		const suffix = ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';
		return `${n}${suffix}`;
	}
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">Your tournament — {current.entry_name}</h2>

	{#if allPersonal.length > 1}
		<div class="mb-1.5 mt-1 flex flex-wrap gap-1.5">
			{#each allPersonal as p, i (p.entry_id)}
				<button
					class="rounded-badge border px-2.5 py-0.5 text-[11px] font-semibold
						{i === selectedIdx
						? 'border-primary/50 bg-primary/15 text-primary'
						: 'border-base-300/60 text-base-content/55'}"
					on:click={() => selectEntry(i)}
				>{p.entry_name}</button>
			{/each}
		</div>
	{/if}

	<p class="text-[13px] text-base-content/55">
		{ordinal(current.final_rank)} of {poolSize}
		· <b class="text-base-content">{current.total_points} pts</b>
		· Group {current.group_points} / Knockout {current.knockout_points} / Bonus {current.bonus_points}
	</p>
	<p class="mt-0.5 text-xs text-base-content/40">
		Your final standing, and the moments that defined your five weeks — {current.percentile_label}.
	</p>

	<div class="mt-2.5 grid gap-2 min-[760px]:grid-cols-3">
		{#each current.superlatives as s (s.title)}
			<div class="grid gap-0.5 rounded-box border border-primary/30 bg-base-100 px-2.5 py-2">
				<span class="text-lg">{s.emoji}</span>
				<span class="font-display text-[13px] font-extrabold text-primary">{s.title}</span>
				<span class="text-xs text-base-content/55">{s.body}</span>
			</div>
		{/each}
	</div>
</div>

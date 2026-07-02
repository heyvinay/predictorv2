<script lang="ts">
	import type { GroupFilter } from '$lib/utils/groupTracker';

	export let active: GroupFilter;
	export let counts: Record<GroupFilter, number>;
	export let onSelect: (filter: GroupFilter) => void;

	const CHIPS: { key: GroupFilter; label: string; tone: 'good' | 'warn' | 'neutral' }[] = [
		{ key: 'all', label: 'All groups', tone: 'neutral' },
		{ key: 'locked', label: 'Locked', tone: 'good' },
		{ key: 'atRisk', label: 'At risk', tone: 'warn' },
		{ key: 'orderSwap', label: 'Order swap', tone: 'neutral' },
		{ key: 'upcoming', label: 'Upcoming', tone: 'neutral' }
	];

	function countClass(tone: 'good' | 'warn' | 'neutral', isActive: boolean): string {
		if (isActive) return 'bg-primary/20 text-primary';
		if (tone === 'good') return 'bg-success/20 text-success';
		if (tone === 'warn') return 'bg-warning/20 text-warning-text';
		return 'bg-base-300 text-base-content/70';
	}
</script>

<div class="mb-3 flex flex-wrap items-center gap-2" role="tablist" aria-label="Filter groups by state">
	<span class="text-[10px] font-semibold uppercase tracking-wide text-base-content/45">Show</span>
	{#each CHIPS as chip}
		{@const isActive = active === chip.key}
		<button
			type="button"
			class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors {isActive
				? 'border-primary/50 bg-primary/10 text-primary'
				: 'border-base-300 bg-base-200 text-base-content hover:border-base-content/20'}"
			on:click={() => onSelect(chip.key)}
		>
			{chip.label}
			<span class="rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums {countClass(chip.tone, isActive)}">
				{counts[chip.key]}
			</span>
		</button>
	{/each}
</div>

<script lang="ts">
	import type { CompareSummary } from '$lib/utils/compareEntries';

	export let summary: CompareSummary;
	export let aName: string;
	export let bName: string;

	const TILES: { key: keyof CompareSummary; label: string }[] = [
		{ key: 'total', label: 'Total gap' },
		{ key: 'group', label: 'Group stage' },
		{ key: 'knockout', label: 'Knockout' },
		{ key: 'bonus', label: 'Bonus' }
	];

	const round1 = (n: number) => Math.round(n * 10) / 10;
	const fmt = (n: number) => (n > 0 ? `+${round1(n)}` : `${round1(n)}`);
	const tone = (n: number) => (n > 0 ? 'text-success' : n < 0 ? 'text-error' : 'text-base-content/55');
</script>

<div>
	<p class="text-xs text-base-content/55 mb-2">{aName} vs {bName} — positive = {aName} ahead</p>
	<div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
		{#each TILES as t}
			<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
				<p class="text-[10px] uppercase tracking-wider text-base-content/40">{t.label}</p>
				<p class="font-display text-xl font-extrabold {tone(summary[t.key])}">{fmt(summary[t.key])}</p>
			</div>
		{/each}
	</div>
</div>

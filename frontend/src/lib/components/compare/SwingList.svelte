<script lang="ts">
	import type { Swing } from '$lib/utils/compareEntries';

	export let swings: Swing[];
	export let limit = 5;
	export let expandable = true;

	let expanded = false;
	$: visible = expanded ? swings : swings.slice(0, limit);

	const fmt = (n: number) => (n > 0 ? `+${Math.round(n * 10) / 10}` : `${Math.round(n * 10) / 10}`);
</script>

<div class="space-y-1.5">
	{#each visible as s (s.kind + s.label)}
		<div class="flex items-center justify-between gap-3 rounded-btn border border-base-300/60 bg-base-100 px-3 py-1.5">
			<div class="min-w-0">
				<p class="text-sm truncate">{s.label}</p>
				<p class="text-xs text-base-content/55 truncate">{s.why}</p>
			</div>
			<span
				class="flex-none rounded-badge px-2 py-0.5 font-display text-sm font-extrabold
					{s.delta > 0 ? 'bg-success/15 text-success' : 'bg-error/15 text-error'}"
			>{fmt(s.delta)}</span>
		</div>
	{/each}
	{#if expandable && swings.length > limit}
		<button class="btn btn-ghost btn-xs text-primary" on:click={() => (expanded = !expanded)}>
			{expanded ? 'Show top 5' : `Show all ${swings.length}`}
		</button>
	{/if}
</div>

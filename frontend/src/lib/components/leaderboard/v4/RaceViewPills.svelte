<script lang="ts">
	import type { RaceViewMode } from '$lib/types/leaderboard';
	import { createEventDispatcher } from 'svelte';

	export let mode: RaceViewMode;
	export let hasUserEntries: boolean = true;
	export let cohortCounts: { atlas: number; jmfa: number; guests: number } = { atlas: 0, jmfa: 0, guests: 0 };

	const dispatch = createEventDispatcher<{ change: { mode: RaceViewMode } }>();

	type PillSpec = { id: RaceViewMode; label: string; disabled?: boolean; tooltip?: string };

	$: PILLS = [
		{ id: 'around_me', label: 'Around me', disabled: !hasUserEntries, tooltip: hasUserEntries ? undefined : 'Sign up to centre this view on your entries' },
		{ id: 'top10', label: 'Top 10' },
		{ id: 'top25', label: 'Top 25' },
		{ id: 'atlas', label: `Atlas (${cohortCounts.atlas})` },
		{ id: 'jmfa', label: `JMFA (${cohortCounts.jmfa})` },
		{ id: 'guests', label: `Guests (${cohortCounts.guests})` },
	] satisfies PillSpec[];

	function pick(p: PillSpec) {
		if (p.disabled) return;
		mode = p.id;
		dispatch('change', { mode: p.id });
	}
</script>

<div class="flex gap-2 overflow-x-auto snap-x snap-mandatory pb-1 mb-3">
	{#each PILLS as p (p.id)}
		<button
			type="button"
			class="btn btn-sm rounded-full snap-start whitespace-nowrap {mode === p.id ? 'btn-active' : 'btn-ghost border border-base-300'}"
			class:opacity-40={p.disabled}
			disabled={p.disabled}
			title={p.tooltip ?? ''}
			on:click={() => pick(p)}
		>
			{p.label}
		</button>
	{/each}
</div>

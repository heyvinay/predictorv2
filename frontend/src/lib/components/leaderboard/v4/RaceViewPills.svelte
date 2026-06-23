<script lang="ts">
	import type { RaceViewMode } from '$lib/types/leaderboard';
	import { createEventDispatcher } from 'svelte';

	export let mode: RaceViewMode;
	export let hasUserEntries: boolean = true;

	const dispatch = createEventDispatcher<{ change: { mode: RaceViewMode } }>();

	type PillSpec = { id: RaceViewMode; label: string; disabled?: boolean; tooltip?: string };

	$: PILLS = [
		{
			id: 'around_me',
			label: 'Around me',
			disabled: !hasUserEntries,
			tooltip: hasUserEntries ? undefined : 'Sign up to centre this view on your entries'
		},
		{ id: 'top15', label: 'Top 15' }
	] satisfies PillSpec[];

	function pick(p: PillSpec) {
		if (p.disabled) return;
		mode = p.id;
		dispatch('change', { mode: p.id });
	}
</script>

<div class="mb-3 flex gap-2 pb-1">
	{#each PILLS as p (p.id)}
		<button
			type="button"
			class="btn btn-sm whitespace-nowrap rounded-full {mode === p.id
				? 'btn-active'
				: 'btn-ghost border border-base-300'}"
			class:opacity-40={p.disabled}
			disabled={p.disabled}
			title={p.tooltip ?? ''}
			on:click={() => pick(p)}
		>
			{p.label}
		</button>
	{/each}
</div>

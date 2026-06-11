<script lang="ts">
	/** Standings card: sticky uppercase column header + compact rows.
	 *  Final column exists only during the knockout stage — the grid
	 *  template reflows entirely (no empty column, spec §Decisions).
	 *  <880px hides Group/Knockout (Total stays). */
	import type { LbEntryV4, LbStage } from '$lib/types/leaderboard';
	import StandingRow from './StandingRow.svelte';

	export let rows: LbEntryV4[];
	export let stage: LbStage;
	export let userId: string | null | undefined;
	export let onOpen: (row: LbEntryV4) => void;

	// Mobile (<880px): # · entry · champ · (final) · total.
	// Desktop adds Group + Knockout numeric columns.
	const GRID_KO =
		'grid-cols-[60px_minmax(0,1.4fr)_96px_52px_70px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_56px_80px_90px_80px]';
	const GRID_GROUP =
		'grid-cols-[60px_minmax(0,1.4fr)_96px_70px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_80px_90px_80px]';

	$: gridClass = stage === 'knockout' ? GRID_KO : GRID_GROUP;

	const HEAD_CLASS =
		'text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55';
</script>

<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
	<div
		class="sticky top-0 z-10 grid items-center gap-3 bg-base-300/40 px-4 py-2 backdrop-blur {gridClass}"
	>
		<span class={HEAD_CLASS}>#</span>
		<span class={HEAD_CLASS}>Entry</span>
		<span class={HEAD_CLASS}>Champ</span>
		{#if stage === 'knockout'}
			<span class="{HEAD_CLASS} text-center" title="Finalist picks still alive">Final</span>
		{/if}
		<span
			class="{HEAD_CLASS} hidden text-right min-[880px]:block"
			title="Group-stage match points + group bonus questions">Group</span
		>
		<span
			class="{HEAD_CLASS} hidden text-right min-[880px]:block"
			title="Bracket points + knockout bonus questions">Knockout</span
		>
		<span class="{HEAD_CLASS} text-right">Total</span>
	</div>

	{#each rows as row (row.entry_id)}
		<StandingRow {row} {stage} isOwn={row.user_id === userId} {gridClass} {onOpen} />
	{:else}
		<div class="border-t border-base-300/40 px-4 py-8 text-center text-sm text-base-content/55">
			No entries in this pool
		</div>
	{/each}
</div>

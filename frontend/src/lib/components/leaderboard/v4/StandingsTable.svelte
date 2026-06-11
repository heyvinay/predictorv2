<script lang="ts">
	/** Standings card: sticky uppercase column header + compact rows.
	 *  Final column exists only during the knockout stage — the grid
	 *  template reflows entirely (no empty column, spec §Decisions).
	 *  <880px hides Group/Knockout (Total stays).
	 *
	 *  Sortable columns (v2.168.0): Entry / Group / Knockout / Total.
	 *  Default = total desc with alphabetical ties; clicking a header
	 *  toggles direction, switching columns starts at that column's
	 *  natural direction (names A→Z, numbers high→low). Server ranks
	 *  in the # column are global positions and never recomputed. */
	import { browser } from '$app/environment';
	import type { LbEntryV4, LbStage } from '$lib/types/leaderboard';
	import type { LbSort, LbSortKey } from '$lib/utils/leaderboardV4';
	import { DEFAULT_LB_SORT, sortRows } from '$lib/utils/leaderboardV4';
	import StandingRow from './StandingRow.svelte';

	export let rows: LbEntryV4[];
	export let stage: LbStage;
	export let userId: string | null | undefined;
	/** Users with >1 entries (from the UNFILTERED board — naming must not
	 *  change when a pool filter hides one of someone's entries). */
	export let multiOwners: Set<string>;
	/** entry_id → points-over-time array, for the sparkline column.
	 *  Empty map ⇒ all rows render a dash placeholder. */
	export let trajectoriesByEntry: Map<string, number[]> = new Map();
	export let onOpen: (row: LbEntryV4) => void;

	// ── Sort state, persisted across visits ──
	const SORT_KEY = 'predictor:lb:sort';
	const NATURAL_DIR: Record<LbSortKey, 'asc' | 'desc'> = {
		entry: 'asc',
		group: 'desc',
		knockout: 'desc',
		total: 'desc'
	};

	function readSort(): LbSort {
		if (!browser) return DEFAULT_LB_SORT;
		try {
			const raw = JSON.parse(localStorage.getItem(SORT_KEY) ?? 'null');
			if (raw && raw.key in NATURAL_DIR && (raw.dir === 'asc' || raw.dir === 'desc')) {
				return raw as LbSort;
			}
		} catch {
			/* corrupted value → default */
		}
		return DEFAULT_LB_SORT;
	}

	let sort: LbSort = readSort();

	function toggleSort(key: LbSortKey) {
		sort =
			sort.key === key
				? { key, dir: sort.dir === 'asc' ? 'desc' : 'asc' }
				: { key, dir: NATURAL_DIR[key] };
		if (browser) localStorage.setItem(SORT_KEY, JSON.stringify(sort));
	}

	function arrowFor(key: LbSortKey): string {
		if (sort.key !== key) return '';
		return sort.dir === 'asc' ? '▲' : '▼';
	}

	$: sortedRows = sortRows(rows, sort, multiOwners);

	// Mobile (<880px): # · entry · champ · (final) · total · chevron.
	// Desktop adds Group + Knockout numeric columns AND a 64px Trend
	// column (sparkline) sitting between Knockout and Total. The
	// trailing 16px column is the click-affordance chevron.
	const GRID_KO =
		'grid-cols-[60px_minmax(0,1.4fr)_96px_52px_70px_16px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_56px_80px_90px_64px_80px_16px]';
	const GRID_GROUP =
		'grid-cols-[60px_minmax(0,1.4fr)_96px_70px_16px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_80px_90px_64px_80px_16px]';

	$: gridClass = stage === 'knockout' ? GRID_KO : GRID_GROUP;

	const HEAD_CLASS =
		'text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55';
</script>

<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
	<div
		class="sticky top-0 z-10 grid items-center gap-3 bg-base-300/40 px-4 py-2 backdrop-blur {gridClass}"
	>
		<span class={HEAD_CLASS}>#</span>
		<button
			type="button"
			class="{HEAD_CLASS} text-left transition-colors hover:text-primary {sort.key === 'entry'
				? 'text-primary'
				: ''}"
			on:click={() => toggleSort('entry')}>Entry {arrowFor('entry')}</button
		>
		<span class={HEAD_CLASS}>Champ</span>
		{#if stage === 'knockout'}
			<span class="{HEAD_CLASS} text-center" title="Finalist picks still alive">Final</span>
		{/if}
		<button
			type="button"
			class="{HEAD_CLASS} hidden text-right transition-colors hover:text-primary min-[880px]:block {sort.key ===
			'group'
				? 'text-primary'
				: ''}"
			title="Group-stage match points + group bonus questions"
			on:click={() => toggleSort('group')}>Group {arrowFor('group')}</button
		>
		<button
			type="button"
			class="{HEAD_CLASS} hidden text-right transition-colors hover:text-primary min-[880px]:block {sort.key ===
			'knockout'
				? 'text-primary'
				: ''}"
			title="Bracket points + knockout bonus questions"
			on:click={() => toggleSort('knockout')}>Knockout {arrowFor('knockout')}</button
		>
		<span
			class="{HEAD_CLASS} hidden text-center min-[880px]:block"
			title="Points-over-time, last 14 days">Trend</span
		>
		<button
			type="button"
			class="{HEAD_CLASS} text-right transition-colors hover:text-primary {sort.key === 'total'
				? 'text-primary'
				: ''}"
			on:click={() => toggleSort('total')}>Total {arrowFor('total')}</button
		>
		<span></span>
	</div>

	{#each sortedRows as row (row.entry_id)}
		<StandingRow
			{row}
			{stage}
			isOwn={row.user_id === userId}
			{gridClass}
			{multiOwners}
			trajectory={trajectoriesByEntry.get(row.entry_id) ?? []}
			{onOpen}
		/>
	{:else}
		<div class="border-t border-base-300/40 px-4 py-8 text-center text-sm text-base-content/55">
			No entries match — try another pool or clear the search
		</div>
	{/each}
</div>

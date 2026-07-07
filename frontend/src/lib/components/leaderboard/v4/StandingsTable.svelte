<script lang="ts">
	/** Standings card: sticky uppercase column header + compact rows.
	 *  Final column exists only during the knockout stage — the grid
	 *  template reflows entirely (no empty column, spec §Decisions).
	 *  <880px hides Champ/Group/Knockout (Total stays).
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
	/** entry_id → rank-over-time array, for the sparkline column.
	 *  Empty map ⇒ all rows render a dash placeholder. */
	export let trajectoriesByEntry: Map<string, number[]> = new Map();
	/** True when the board carries a live KO projection (armed gates +
	 *  a knockout match live). Preserves incoming row order under the
	 *  default sort; any explicit column sort still wins. */
	export let live = false;
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

	function ariaSortFor(key: LbSortKey, s: LbSort): 'ascending' | 'descending' | 'none' {
		if (s.key !== key) return 'none';
		return s.dir === 'asc' ? 'ascending' : 'descending';
	}

	// When live and the user hasn't chosen an explicit non-default sort,
	// preserve the incoming order — the page has already sorted `rows` by
	// projected_position for the live board. Any explicit column sort
	// (name/group/knockout, or re-clicking Total) falls through to the
	// normal banked sort; live projection only owns the DEFAULT view.
	$: isDefaultSort = sort.key === DEFAULT_LB_SORT.key && sort.dir === DEFAULT_LB_SORT.dir;
	$: sortedRows = live && isDefaultSort ? rows : sortRows(rows, sort, multiOwners);

	// Pin own entries at the top (matching the dashboard mini-leaderboard)
	// AND keep them in their natural rank position in the full list, so
	// users can see immediate neighbours at a glance. The pinned section
	// uses isOwn={true} for the gold ring + chip; the in-place rows render
	// with isOwn={false} — the "Your entries · pinned" header band above
	// is the explicit cue, no per-row marker needed. Global ranks survive
	// (rendered from row.position), so the pinned entry's "#117" matches
	// its real position in the un-pinned standings below.
	$: pinnedRows = userId ? sortedRows.filter((r) => r.user_id === userId) : [];
	$: otherRows = sortedRows;
	$: hasPinned = pinnedRows.length > 0;

	const SECTION_BAND_CLASS =
		'border-t border-base-300/40 bg-base-300/30 px-3 py-1 text-[9.5px] font-extrabold uppercase tracking-[0.16em] text-base-content/65 min-[880px]:px-4';

	// Mobile (<880px): # · entry · (final) · total · chevron. Champ is
	// desktop-only — its 96px starved the entry-name column on phones;
	// the pick is still one tap away in the entry drawer.
	// Desktop adds Champ + Group + Knockout numeric columns AND a 64px
	// Trend column (sparkline) sitting between Knockout and Total. The
	// trailing 16px column is the click-affordance chevron.
	const GRID_KO =
		'grid-cols-[48px_minmax(0,1.4fr)_52px_70px_16px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_56px_80px_90px_64px_80px_16px]';
	const GRID_GROUP =
		'grid-cols-[48px_minmax(0,1.4fr)_70px_16px] min-[880px]:grid-cols-[70px_minmax(0,1.6fr)_104px_80px_90px_64px_80px_16px]';

	$: gridClass = stage === 'knockout' ? GRID_KO : GRID_GROUP;

	// Sort buttons inherit this class; explicit focus-visible outline so
	// keyboard users see what they're about to activate (the default
	// DaisyUI button outline is suppressed by surrounding styles here).
	const HEAD_CLASS =
		'text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary focus-visible:rounded-sm';
</script>

<!-- ARIA table semantics on the CSS grid (review P1): screen readers get
     row/column navigation without converting to <table> and risking the
     responsive grid layout. Sortable headers carry aria-sort; the row
     buttons below are role="row" (still real <button>s — Enter/click
     open the drawer). -->
<div
	class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200"
	role="table"
	aria-label="Tournament standings"
>
	<div
		class="sticky top-0 z-10 grid items-center gap-2 bg-base-300/40 px-3 py-2 backdrop-blur min-[880px]:gap-3 min-[880px]:px-4 {gridClass}"
		role="row"
	>
		<span class={HEAD_CLASS} role="columnheader" aria-label="Rank">#</span>
		<button
			type="button"
			role="columnheader"
			aria-sort={ariaSortFor('entry', sort)}
			class="{HEAD_CLASS} text-left transition-colors hover:text-primary {sort.key === 'entry'
				? 'text-primary'
				: ''}"
			on:click={() => toggleSort('entry')}>Entry {arrowFor('entry')}</button
		>
		<span class="{HEAD_CLASS} hidden min-[880px]:block" role="columnheader">Champ</span>
		{#if stage === 'knockout'}
			<span class="{HEAD_CLASS} text-center" role="columnheader" title="Finalist picks still alive"
				>Final</span
			>
		{/if}
		<button
			type="button"
			role="columnheader"
			aria-sort={ariaSortFor('group', sort)}
			class="{HEAD_CLASS} hidden text-right transition-colors hover:text-primary min-[880px]:block {sort.key ===
			'group'
				? 'text-primary'
				: ''}"
			title="Group-stage match points + group bonus questions"
			on:click={() => toggleSort('group')}>Group {arrowFor('group')}</button
		>
		<button
			type="button"
			role="columnheader"
			aria-sort={ariaSortFor('knockout', sort)}
			class="{HEAD_CLASS} hidden text-right transition-colors hover:text-primary min-[880px]:block {sort.key ===
			'knockout'
				? 'text-primary'
				: ''}"
			title="Bracket points + knockout bonus questions"
			on:click={() => toggleSort('knockout')}>Knockout {arrowFor('knockout')}</button
		>
		<span
			class="{HEAD_CLASS} hidden text-center min-[880px]:block"
			role="columnheader"
			title="Rank-over-time, last 14 days — up means climbing the standings">Trend</span
		>
		<button
			type="button"
			role="columnheader"
			aria-sort={ariaSortFor('total', sort)}
			class="{HEAD_CLASS} text-right transition-colors hover:text-primary {sort.key === 'total'
				? 'text-primary'
				: ''}"
			on:click={() => toggleSort('total')}>Total {arrowFor('total')}</button
		>
		<span role="columnheader" aria-label="Open entry details"></span>
	</div>

	{#if hasPinned}
		<div class={SECTION_BAND_CLASS} role="rowgroup" aria-label="Your entries">
			Your {pinnedRows.length === 1 ? 'entry' : 'entries'} · pinned
		</div>
		{#each pinnedRows as row (row.entry_id)}
			<StandingRow
				{row}
				{stage}
				isOwn={true}
				{gridClass}
				{multiOwners}
				trajectory={trajectoriesByEntry.get(row.entry_id) ?? []}
				{live}
				{onOpen}
			/>
		{/each}
		<div class={SECTION_BAND_CLASS} role="rowgroup" aria-label="All entries">All entries</div>
	{/if}

	{#each otherRows as row (row.entry_id)}
		<StandingRow
			{row}
			{stage}
			isOwn={userId != null && row.user_id === userId}
			{gridClass}
			{multiOwners}
			trajectory={trajectoriesByEntry.get(row.entry_id) ?? []}
			{live}
			{onOpen}
		/>
	{:else}
		{#if !hasPinned}
			<div class="border-t border-base-300/40 px-4 py-8 text-center text-sm text-base-content/55">
				No entries match — try another pool or clear the search
			</div>
		{/if}
	{/each}
</div>

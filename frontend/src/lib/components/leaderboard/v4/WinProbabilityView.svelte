<script lang="ts">
	/**
	 * Win Probability tab (admin-gated) — P(win the pool) / P(top-3) /
	 * expected rank per entry, simulated by enumerating every remaining
	 * knockout bracket completion. Team trophy-odds ride along as a
	 * byproduct of the same simulation.
	 *
	 * Fetch state is owned by the PARENT page (+page.svelte), not this
	 * component — switching tabs destroys/recreates this component, and
	 * the whole point of the manual "Run simulation" button is that
	 * coming back to the tab shows the last result (with its timestamp),
	 * not a silent auto-refetch or a blank slate.
	 */
	import { slide } from 'svelte/transition';
	import { currentTime } from '$stores/phase';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { TeamStageOdds, WinProbabilityResponse } from '$lib/types/winProbability';
	import { relativeAgo } from '$lib/utils/relativeTime';
	import { rowDisplayName } from '$lib/utils/leaderboardV4';
	import { joinWinProbabilityRows } from '$lib/utils/winProbability';
	import FlagCode from './FlagCode.svelte';
	import WinProbabilityExplainer from './WinProbabilityExplainer.svelte';
	import WinProbEntryCard from './WinProbEntryCard.svelte';
	import YouTag from './YouTag.svelte';

	export let rows: LbEntryV4[];
	export let multiOwners: Set<string>;
	export let userId: string | null | undefined;
	export let data: WinProbabilityResponse | null;
	export let loading: boolean;
	export let failed: boolean;
	/** Most-recently-FINISHED fixture, formatted e.g. "POR 0–1 ESP" — same
	 *  value the Standings header's "last result" line uses, passed down
	 *  from the page rather than recomputed here. */
	export let lastFinished: string | null;
	export let onRun: () => void;
	/** Live-projection active — makes the expanded card read projected
	 *  rank/points instead of banked ones, same as the standings surfaces. */
	export let live = false;

	// Clicking a row expands it in place to reveal that entry's conditional
	// win-probability card ("what has to happen for you to win") — a single
	// open row at a time, toggled off by clicking the open row again.
	let expanded: string | null = null;
	function toggle(entryId: string) {
		expanded = expanded === entryId ? null : entryId;
	}

	// Fixed-width CHAMP (104px) / FINAL (56px) columns match
	// StandingsTable's own GRID_KO exactly, so the champion-pick flag and
	// finalist dots line up at the same x-position as the Standings tab —
	// a CSS grid, not flexbox, is what makes columns width-independent of
	// each row's entry-name length. T3/ER/WIN% get their own fixed
	// columns too (in that order), matching a header row above the rows.
	// Champ/Final hide below 880px, same breakpoint Standings uses. A
	// trailing ODDS% column is inserted only when the API actually
	// priced something — two full grid-template literals (not built by
	// concatenation) so Tailwind's static class scanner sees both.
	const ROW_GRID =
		'grid-cols-[28px_minmax(0,1.6fr)_50px_44px_60px] min-[880px]:grid-cols-[28px_minmax(0,1.6fr)_104px_56px_50px_44px_60px]';
	const ROW_GRID_WITH_ODDS =
		'grid-cols-[28px_minmax(0,1.6fr)_50px_44px_60px_60px] min-[880px]:grid-cols-[28px_minmax(0,1.6fr)_104px_56px_50px_44px_60px_60px]';

	$: hasOdds = !!data?.odds_weighted;
	$: gridClass = hasOdds ? ROW_GRID_WITH_ODDS : ROW_GRID;
	$: joinedRaw = data ? joinWinProbabilityRows(rows, data.entries, data.odds_weighted?.entries) : [];

	// Sortable stat columns. ER's "best" direction is ascending (lower rank
	// wins) so it gets a different default than the other three, which are
	// all "higher is better" — clicking a header the first time should
	// always show the best rows first, not require a second click to flip.
	type SortKey = 'p_top3' | 'expected_rank' | 'p_win' | 'odds_p_win';
	const DEFAULT_DIR: Record<SortKey, 'asc' | 'desc'> = {
		p_top3: 'desc',
		expected_rank: 'asc',
		p_win: 'desc',
		odds_p_win: 'desc'
	};
	let sortKey: SortKey = 'p_win';
	let sortDir: 'asc' | 'desc' = 'desc';

	function toggleSort(key: SortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'desc' ? 'asc' : 'desc';
		} else {
			sortKey = key;
			sortDir = DEFAULT_DIR[key];
		}
	}

	// A plain helper called from the template (aria-sort={ariaSort(key)})
	// would never re-run on click: Svelte's template dependency tracking
	// only sees the identifiers written directly in the template
	// expression, not what a called function's body reads internally —
	// so `sortKey`/`sortDir` have to appear literally in this statement
	// for the attribute to actually update. The visible ▲/▼ arrow uses
	// the same `{#if sortKey === '...'}` pattern inline in the template,
	// which is why it already worked before this fix.
	$: sortAria = {
		p_top3: sortKey === 'p_top3' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none',
		expected_rank:
			sortKey === 'expected_rank' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none',
		p_win: sortKey === 'p_win' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none',
		odds_p_win:
			sortKey === 'odds_p_win' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'
	} as const;

	// Rows with no value for the active sort key (odds_p_win when a match
	// isn't priced for that entry) sink to the bottom regardless of
	// direction — "no data" isn't a value to rank by in either direction.
	$: joined = [...joinedRaw].sort((a, b) => {
		const av = a[sortKey];
		const bv = b[sortKey];
		if (av === undefined && bv === undefined) return 0;
		if (av === undefined) return 1;
		if (bv === undefined) return -1;
		return sortDir === 'asc' ? av - bv : bv - av;
	});
	$: topTeams = data
		? [...data.teams]
				.sort((a, b) => (b.stage_odds.winner ?? 0) - (a.stage_odds.winner ?? 0))
				.slice(0, 8)
		: [];
	$: topTeamsOdds = data?.odds_weighted
		? [...data.odds_weighted.teams]
				.sort((a, b) => (b.stage_odds.winner ?? 0) - (a.stage_odds.winner ?? 0))
				.slice(0, 8)
		: [];
	$: unavailable = data?.meta.mode === 'unavailable';

	function pct(v: number): string {
		return `${(v * 100).toFixed(v >= 0.1 ? 1 : 2)}%`;
	}

	function teamOdds(t: TeamStageOdds): number {
		return t.stage_odds.winner ?? 0;
	}
</script>

{#if loading}
	<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
		<div class="bg-base-300/40 px-4 py-2">
			<div class="h-3 w-56 animate-pulse rounded bg-base-300"></div>
		</div>
		{#each Array(6) as _}
			<div class="flex items-center gap-4 border-t border-base-300/40 px-4 py-2.5">
				<div class="h-4 w-6 animate-pulse rounded bg-base-300"></div>
				<div class="h-4 flex-1 animate-pulse rounded bg-base-300"></div>
				<div class="h-4 w-24 animate-pulse rounded bg-base-300"></div>
			</div>
		{/each}
	</div>
{:else if failed || unavailable}
	<div class="rounded-xl border border-error/40 bg-error/10 px-5 py-8 text-center">
		<p class="mb-3 text-sm text-base-content/80">
			{failed
				? "Win probability isn't available right now."
				: "The simulator hit a snag computing odds — showing nothing rather than a stale guess."}
		</p>
		<button class="btn btn-outline btn-sm" on:click={onRun}>Try again</button>
	</div>
{:else if !data}
	<div class="rounded-xl border border-base-300/60 bg-base-200 px-5 py-10 text-center">
		<p class="mb-1 font-display text-base font-bold">Who wins the pool?</p>
		<p class="mb-4 text-sm text-base-content/55">
			Simulates every possible outcome of the remaining knockout matches to work out each
			entry's odds of winning — plus every team's odds of lifting the trophy.
		</p>
		<button class="btn btn-primary btn-sm" on:click={onRun}>Run simulation</button>
	</div>
{:else}
	<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
		<span class="font-mono text-xs text-base-content/55">
			{data.meta.scenario_count.toLocaleString()} scenarios · {data.meta.unresolved_matches} match{data
				.meta.unresolved_matches === 1
				? ''
				: 'es'} left to play
			{#if lastFinished}
				· last result: <b class="text-base-content/70">{lastFinished}</b>
			{/if}
		</span>
		<span class="flex items-center gap-2 text-xs text-base-content/55">
			{#if data.odds_coverage.priceable > 0}
				<span
					class="rounded-badge bg-base-300/50 px-1.5 py-0.5 font-mono text-[10px]"
					title="Live betting odds priced {data.odds_coverage.priced} of {data.odds_coverage
						.priceable} upcoming match(es) with two known teams"
					>odds {data.odds_coverage.priced}/{data.odds_coverage.priceable}</span
				>
			{/if}
			<span>Last run {relativeAgo(data.meta.computed_at, $currentTime.getTime())}</span>
			<button class="btn btn-ghost btn-xs" on:click={onRun}>Re-run</button>
		</span>
	</div>

	<div class="mb-2">
		<WinProbabilityExplainer {hasOdds} />
	</div>

	<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
		<div
			class="grid items-center gap-2 border-b border-base-300/40 bg-base-300/40 px-3 py-2 min-[880px]:gap-3 min-[880px]:px-4 {gridClass}"
			role="row"
		>
			<span role="columnheader" aria-label="Rank"></span>
			<span
				role="columnheader"
				class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>Entry</span
			>
			<span
				role="columnheader"
				class="hidden text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55 min-[880px]:block"
				title="Who this entry picked to win the whole tournament">Champ</span
			>
			<span
				role="columnheader"
				class="hidden text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55 min-[880px]:block"
				title="How many of this entry's two finalist picks are still alive">Final</span
			>
			<span
				role="columnheader"
				aria-sort={sortAria.p_top3}
				class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				<button
					class="inline-flex items-center gap-0.5 hover:text-base-content/80"
					title="Probability this entry finishes in the top 3 — click to sort"
					on:click={() => toggleSort('p_top3')}
				>
					T3{#if sortKey === 'p_top3'}<span aria-hidden="true"
							>{sortDir === 'asc' ? '▲' : '▼'}</span
						>{/if}
				</button>
			</span>
			<span
				role="columnheader"
				aria-sort={sortAria.expected_rank}
				class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				<button
					class="inline-flex items-center gap-0.5 hover:text-base-content/80"
					title="Expected rank — this entry's average finishing position, weighted by how likely each simulated outcome is. Lower is better. Click to sort."
					on:click={() => toggleSort('expected_rank')}
				>
					ER{#if sortKey === 'expected_rank'}<span aria-hidden="true"
							>{sortDir === 'asc' ? '▲' : '▼'}</span
						>{/if}
				</button>
			</span>
			<span
				role="columnheader"
				aria-sort={sortAria.p_win}
				class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				<button
					class="inline-flex items-center gap-0.5 hover:text-base-content/80"
					title="Probability this entry finishes 1st in the pool, averaged across every simulated outcome of the remaining knockout matches — click to sort"
					on:click={() => toggleSort('p_win')}
				>
					Win%{#if sortKey === 'p_win'}<span aria-hidden="true"
							>{sortDir === 'asc' ? '▲' : '▼'}</span
						>{/if}
				</button>
			</span>
			{#if hasOdds}
				<span
					role="columnheader"
					aria-sort={sortAria.odds_p_win}
					class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>
					<button
						class="inline-flex items-center gap-0.5 hover:text-base-content/80"
						title="The same Win% but weighted by live betting odds for the next unresolved match(es), instead of a flat 50/50 — click to sort"
						on:click={() => toggleSort('odds_p_win')}
					>
						Odds%{#if sortKey === 'odds_p_win'}<span aria-hidden="true"
								>{sortDir === 'asc' ? '▲' : '▼'}</span
							>{/if}
					</button>
				</span>
			{/if}
		</div>
		{#each joined as j, i (j.row.entry_id)}
			{@const isOwn = j.row.user_id === userId}
			{@const finalists = j.row.finalist_picks ?? []}
			{@const finAlive = j.row.finalists_alive ?? 0}
			{@const isExpanded = expanded === j.row.entry_id}
			<button
				role="row"
				aria-expanded={isExpanded}
				class="grid w-full items-center gap-2 border-t border-base-300/40 px-3 py-2 text-left first:border-t-0 hover:bg-base-content/5 min-[880px]:gap-3 min-[880px]:px-4 {gridClass} {isExpanded
					? 'bg-base-content/5'
					: ''} {isOwn
					? 'bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-[inset_3px_0_0_theme(colors.primary)]'
					: ''}"
				on:click={() => toggle(j.row.entry_id)}
			>
				<span role="cell" class="text-right font-mono text-xs text-base-content/55">{i + 1}</span>

				<span role="cell" class="flex min-w-0 items-center gap-1.5 text-sm font-bold">
					<span class="truncate">{rowDisplayName(j.row, multiOwners)}</span>
					{#if isOwn}<YouTag />{/if}
				</span>

				<span role="cell" class="hidden min-[880px]:flex" title="Champion pick">
					{#if j.row.champion_pick}
						<FlagCode team={j.row.champion_pick} alive={j.row.champion_alive ?? true} dot />
					{:else}
						<span class="text-xs text-base-content/30">—</span>
					{/if}
				</span>

				<span
					role="cell"
					class="hidden justify-center gap-1 min-[880px]:flex"
					title="{finAlive} of {finalists.length || 2} finalist picks still alive"
				>
					{#each [0, 1] as slot}
						<span
							class="grid h-3.5 w-3.5 place-items-center rounded-full text-[8px] font-extrabold leading-none {slot <
							finAlive
								? 'bg-success text-success-content shadow-[0_0_6px_theme(colors.success/50%)]'
								: slot < finalists.length
								? 'bg-base-300/80 text-base-content/55'
								: 'bg-base-300/40 text-base-content/30'}"
							aria-hidden="true"
							>{slot < finAlive ? '✓' : slot < finalists.length ? '✗' : '·'}</span
						>
					{/each}
				</span>

				<span
					role="cell"
					class="text-right font-mono text-xs tabular-nums text-base-content/55"
					title="P(finishes in the top 3)"
					>{pct(j.p_top3)}</span
				>
				<span
					role="cell"
					class="text-right font-mono text-xs tabular-nums text-base-content/55"
					title="Expected rank — average finishing position across all simulated outcomes"
					>{j.expected_rank.toFixed(1)}</span
				>
				<span
					role="cell"
					class="text-right font-mono text-sm font-extrabold tabular-nums"
					title="P(finishes 1st) — probability-weighted across every simulated outcome"
					>{pct(j.p_win)}</span
				>
				{#if hasOdds}
					<span
						role="cell"
						class="text-right font-mono text-xs tabular-nums text-base-content/55"
						title="P(finishes 1st) weighted by live betting odds instead of a flat 50/50"
						>{j.odds_p_win !== undefined ? pct(j.odds_p_win) : '—'}</span
					>
				{/if}
			</button>
			{#if isExpanded}
				<div
					class="border-t border-base-300/40 bg-base-300/20 px-3 py-3 min-[880px]:px-4"
					transition:slide={{ duration: 200 }}
				>
					<WinProbEntryCard entry={j} {multiOwners} {isOwn} {live} />
				</div>
			{/if}
		{:else}
			<p class="px-4 py-6 text-center text-sm text-base-content/55">No eligible entries yet.</p>
		{/each}
	</div>

	{#if topTeams.length}
		<div class="mt-4 rounded-xl border border-base-300/60 bg-base-200 px-4 py-3">
			<p class="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-base-content/55">
				Trophy odds
			</p>
			<div class="flex flex-wrap gap-2">
				{#each topTeams as t (t.team)}
					<span
						class="inline-flex items-center gap-1.5 rounded-badge bg-base-300/50 px-2.5 py-1 text-xs"
					>
						<FlagCode team={t.team} size="sm" />
						<span class="font-mono tabular-nums text-base-content/55">{pct(teamOdds(t))}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}

	{#if topTeamsOdds.length}
		<div class="mt-2 rounded-xl border border-base-300/60 bg-base-200 px-4 py-3">
			<p class="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-base-content/55">
				Trophy odds — odds-weighted
			</p>
			<div class="flex flex-wrap gap-2">
				{#each topTeamsOdds as t (t.team)}
					<span
						class="inline-flex items-center gap-1.5 rounded-badge bg-base-300/50 px-2.5 py-1 text-xs"
					>
						<FlagCode team={t.team} size="sm" />
						<span class="font-mono tabular-nums text-base-content/55">{pct(teamOdds(t))}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}
{/if}

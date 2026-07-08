<script lang="ts">
	/**
	 * Win Probability tab (admin-gated) — P(win the pool) per entry, plus a
	 * Projected Total (expected final points), simulated by enumerating
	 * every remaining knockout bracket completion. Team trophy-odds ride
	 * along as a byproduct of the same simulation.
	 *
	 * Both figures always read from the "effective" model
	 * (`joinWinProbabilityRows`): the odds-weighted view when a live
	 * betting market has priced the next unresolved match, else the
	 * uniform coin-toss run — so Prob% is never blank.
	 *
	 * Fetch state is owned by the PARENT page (+page.svelte), not this
	 * component — switching tabs destroys/recreates this component, but
	 * the result stays cached on the page so returning to the tab shows
	 * the same data instead of a refetch flash. The page auto-fetches on
	 * first open; this component never triggers a fetch itself except via
	 * the error state's "Try again".
	 */
	import { slide } from 'svelte/transition';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { TeamStageOdds, WinProbabilityResponse } from '$lib/types/winProbability';
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
	export let onRun: () => void;
	/** Opens the entry's full prediction drawer from the right — the entry
	 *  name is a dedicated link, separate from the row's own click target
	 *  (which expands the inline conditional card). */
	export let onOpen: (row: LbEntryV4) => void;
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
	// each row's entry-name length. PROB%/PROJ get their own fixed columns
	// too (in that order), matching a header row above the rows. Champ/
	// Final hide below 880px, same breakpoint Standings uses. There's a
	// single column set now — Prob% is always populated (odds-weighted or
	// coin-toss fallback), so there's no longer a variant grid for "no
	// market priced".
	const ROW_GRID =
		'grid-cols-[28px_minmax(0,1.6fr)_60px_64px] min-[880px]:grid-cols-[28px_minmax(0,1.6fr)_104px_56px_60px_64px]';

	$: joinedRaw = data ? joinWinProbabilityRows(rows, data) : [];

	// Both remaining numeric columns are "higher is better", so both
	// default to descending — clicking a header the first time always
	// shows the best rows first.
	type SortKey = 'p_win' | 'projected_points';
	const DEFAULT_DIR: Record<SortKey, 'asc' | 'desc'> = {
		p_win: 'desc',
		projected_points: 'desc'
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
	// for the attribute to actually update.
	$: sortAria = {
		p_win: sortKey === 'p_win' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none',
		projected_points:
			sortKey === 'projected_points' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'
	} as const;

	$: joined = [...joinedRaw].sort((a, b) =>
		sortDir === 'asc' ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]
	);
	/** Whether Prob%/Proj are odds-weighted (a market priced the next
	 *  match) or the coin-toss fallback — drives the explainer copy. */
	$: marketBased = data?.odds_weighted != null;
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
	<!-- Pre-fetch instant, before the page's auto-load reactive sets
	     `loading`. Same skeleton as the loading state — never a "Run
	     simulation" prompt or a blank flash. -->
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
{:else}
	<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
		<div
			class="grid items-center gap-2 border-b border-base-300/40 bg-base-300/40 px-3 py-2 min-[880px]:gap-3 min-[880px]:px-4 {ROW_GRID}"
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
				aria-sort={sortAria.p_win}
				class="flex items-center justify-end gap-0.5 text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				<button
					class="inline-flex items-center gap-0.5 hover:text-base-content/80"
					title="Probability this entry finishes 1st in the pool — weighted by live betting odds when a market has priced the next match, otherwise a flat 50/50 coin-toss. Click to sort."
					on:click={() => toggleSort('p_win')}
				>
					Prob%{#if sortKey === 'p_win'}<span aria-hidden="true"
							>{sortDir === 'asc' ? '▲' : '▼'}</span
						>{/if}
				</button>
				<WinProbabilityExplainer {marketBased} />
			</span>
			<span
				role="columnheader"
				aria-sort={sortAria.projected_points}
				class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				<button
					class="inline-flex items-center gap-0.5 hover:text-base-content/80"
					title="Projected final points — expected total under the same model as Prob%. Click to sort."
					on:click={() => toggleSort('projected_points')}
				>
					Proj{#if sortKey === 'projected_points'}<span aria-hidden="true"
							>{sortDir === 'asc' ? '▲' : '▼'}</span
						>{/if}
				</button>
			</span>
		</div>
		{#each joined as j, i (j.row.entry_id)}
			{@const isOwn = j.row.user_id === userId}
			{@const finalists = j.row.finalist_picks ?? []}
			{@const finAlive = j.row.finalists_alive ?? 0}
			{@const isExpanded = expanded === j.row.entry_id}
			{@const displayName = rowDisplayName(j.row, multiOwners)}
			<!-- Clicking anywhere in the row is a mouse-only convenience for
			     expanding the card — the caret button below is the real,
			     keyboard-operable expand control (and the name is its own
			     focusable link), so this non-interactive-role div doesn't
			     need its own tabindex/keydown handler. -->
			<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
			<!-- svelte-ignore a11y-click-events-have-key-events -->
			<!-- svelte-ignore a11y-interactive-supports-focus -->
			<div
				role="row"
				class="grid w-full cursor-pointer items-center gap-2 border-t border-base-300/40 px-3 py-2 text-left first:border-t-0 hover:bg-base-content/5 min-[880px]:gap-3 min-[880px]:px-4 {ROW_GRID} {isExpanded
					? 'bg-base-content/5'
					: ''} {isOwn
					? 'bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-[inset_3px_0_0_theme(colors.primary)]'
					: ''}"
				on:click={() => toggle(j.row.entry_id)}
			>
				<span role="cell" class="text-right font-mono text-xs text-base-content/55">{i + 1}</span>

				<span role="cell" class="flex min-w-0 items-center gap-1.5 text-sm font-bold">
					<button
						type="button"
						class="truncate text-left decoration-primary/50 decoration-dotted underline-offset-2 hover:text-primary hover:underline"
						title="Open {displayName}'s full prediction entry"
						on:click|stopPropagation={() => onOpen(j.row)}
					>
						{displayName}
					</button>
					{#if isOwn}<YouTag />{/if}
					<button
						type="button"
						aria-expanded={isExpanded}
						aria-label="{isExpanded ? 'Collapse' : 'Expand'} {displayName}'s win-probability breakdown"
						class="ml-auto flex-none px-0.5 text-[11px] leading-none text-base-content/40 transition-transform hover:text-primary {isExpanded
							? 'rotate-90 text-primary'
							: ''}"
						on:click|stopPropagation={() => toggle(j.row.entry_id)}
					>
						▸
					</button>
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
					class="text-right font-mono text-sm font-extrabold tabular-nums"
					title={marketBased
						? 'P(finishes 1st) weighted by live betting odds for the next unresolved match'
						: 'P(finishes 1st) — flat 50/50 coin-toss model (no market priced yet)'}
					>{pct(j.p_win)}</span
				>
				<span
					role="cell"
					class="text-right font-mono text-xs tabular-nums text-base-content/70"
					title="Projected final points under the same model as Prob%"
					>{j.projected_points.toFixed(1)}</span
				>
			</div>
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

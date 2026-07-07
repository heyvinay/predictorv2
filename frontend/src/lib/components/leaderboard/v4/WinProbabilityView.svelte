<script lang="ts">
	/**
	 * Win Probability tab (admin-gated) — P(win the pool) / P(top-3) /
	 * expected rank per entry, simulated by enumerating every remaining
	 * knockout bracket completion. Team trophy-odds ride along as a
	 * byproduct of the same simulation.
	 *
	 * Self-fetches its own data (getWinProbability) — `rows`/`multiOwners`
	 * arrive as props from the page's existing leaderboard load, purely
	 * for identity (rowDisplayName), the same split PoolDistribution.svelte
	 * uses for its own self-fetched widget data.
	 */
	import { onMount } from 'svelte';
	import { getWinProbability } from '$lib/api/leaderboard';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { TeamStageOdds, WinProbabilityResponse } from '$lib/types/winProbability';
	import { rowDisplayName } from '$lib/utils/leaderboardV4';
	import { joinWinProbabilityRows } from '$lib/utils/winProbability';

	export let rows: LbEntryV4[];
	export let multiOwners: Set<string>;
	export let onOpen: (row: LbEntryV4) => void;

	let data: WinProbabilityResponse | null = null;
	let loading = true;
	let failed = false;

	onMount(async () => {
		try {
			data = await getWinProbability();
		} catch {
			failed = true;
		} finally {
			loading = false;
		}
	});

	$: joined = data ? joinWinProbabilityRows(rows, data.entries) : [];
	$: topTeams = data
		? [...data.teams]
				.sort((a, b) => (b.stage_odds.winner ?? 0) - (a.stage_odds.winner ?? 0))
				.slice(0, 8)
		: [];

	function pct(v: number): string {
		return `${(v * 100).toFixed(v >= 0.1 ? 1 : 2)}%`;
	}

	function teamOdds(t: TeamStageOdds): number {
		return t.stage_odds.winner ?? 0;
	}
</script>

{#if loading}
	<div class="rounded-xl border border-base-300/60 bg-base-200 px-5 py-10 text-center">
		<div class="mx-auto h-5 w-40 animate-pulse rounded bg-base-300"></div>
	</div>
{:else if failed || !data}
	<div class="rounded-xl border border-error/40 bg-error/10 px-5 py-6 text-center">
		<p class="text-sm text-base-content/80">Win probability isn't available right now.</p>
	</div>
{:else if data.meta.mode === 'unavailable'}
	<div class="rounded-xl border border-warning/30 bg-warning/10 px-5 py-6 text-center">
		<p class="text-sm text-base-content/80">
			The simulator hit a snag computing odds — showing nothing rather than a stale guess.
		</p>
	</div>
{:else}
	<div class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/55">
		<span>Who wins the pool?</span>
		<span class="font-mono">
			{data.meta.scenario_count.toLocaleString()} scenarios · {data.meta.unresolved_matches} match{data
				.meta.unresolved_matches === 1
				? ''
				: 'es'} left to play
		</span>
	</div>

	<div class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200">
		{#each joined as j, i (j.row.entry_id)}
			<button
				class="flex w-full items-center gap-3 border-t border-base-300/40 px-4 py-2.5 text-left first:border-t-0 hover:bg-base-300/30"
				on:click={() => onOpen(j.row)}
			>
				<span class="w-5 shrink-0 text-right font-mono text-xs text-base-content/55">{i + 1}</span>
				<span class="min-w-0 flex-1 truncate text-sm">{rowDisplayName(j.row, multiOwners)}</span>
				<span class="hidden shrink-0 font-mono text-xs text-base-content/55 sm:inline"
					>top-3 {pct(j.p_top3)}</span
				>
				<span class="hidden shrink-0 font-mono text-xs text-base-content/55 sm:inline"
					>E[rank] {j.expected_rank.toFixed(1)}</span
				>
				<span class="flex w-28 shrink-0 items-center gap-2">
					<span class="h-2 flex-1 overflow-hidden rounded-full bg-base-300/60">
						<span
							class="block h-full rounded-full bg-gradient-to-r from-primary to-success"
							style="width: {Math.max(1, j.p_win * 100)}%"
						></span>
					</span>
					<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums">{pct(j.p_win)}</span
					>
				</span>
			</button>
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
						<span>{t.team}</span>
						<span class="font-mono tabular-nums text-base-content/55">{pct(teamOdds(t))}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}
{/if}

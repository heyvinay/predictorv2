<script lang="ts">
	/**
	 * Consensus Bracket — teams × knockout-stages matrix. Each cell is the
	 * % of eligible entries who picked that team to reach that stage (gold
	 * heatmap, cumulative so it only pales left→right). Each team's row
	 * carries a ring on the stage it ACTUALLY reached (green = still in,
	 * red ✕ = knocked out there); group-stage exits get an "OUT · Groups"
	 * tag and no ring. Live Polymarket title odds sit in blue next to each
	 * team when the gated endpoint returns them.
	 *
	 * Two independent fetches: consensus-bracket (public) and
	 * champion-market-odds (gated — a 403 just hides the blue odds, the
	 * gold matrix always renders). Live-polled so it re-derives after games.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { getChampionMarketOdds, getConsensusBracket } from '$lib/api/leaderboard';
	import type { ConsensusTeamRow } from '$lib/types/leaderboard';
	import { getFlagUrl } from '$lib/utils/flags';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import InsightCard from './InsightCard.svelte';

	const STAGES = [
		{ key: 'round_of_32', label: 'R32' },
		{ key: 'round_of_16', label: 'R16' },
		{ key: 'quarter_final', label: 'QF' },
		{ key: 'semi_final', label: 'SF' },
		{ key: 'final', label: 'Final' },
		{ key: 'winner', label: 'Champ' }
	];
	const STAGE_IDX: Record<string, number> = Object.fromEntries(
		STAGES.map((s, i) => [s.key, i])
	);

	let rows: ConsensusTeamRow[] = [];
	let eligible = 0;
	let marketByTeam: Record<string, number> = {};
	let loaded = false;
	let stopPoll: (() => void) | undefined;

	async function refresh() {
		try {
			const res = await getConsensusBracket();
			rows = res.rows;
			eligible = res.eligible_count;
		} catch {
			rows = [];
			eligible = 0;
		}
		try {
			const odds = await getChampionMarketOdds();
			marketByTeam = Object.fromEntries(odds.odds.map((o) => [o.team, o.market_odds]));
		} catch {
			marketByTeam = {}; // 403 (flag off) → no blue column
		}
		loaded = true;
	}

	onMount(async () => {
		await refresh();
		stopPoll = startLivePoll(refresh, 60_000);
	});
	onDestroy(() => stopPoll?.());

	$: hasMarket = Object.keys(marketByTeam).length > 0;

	function pct(row: ConsensusTeamRow, key: string): number {
		return eligible > 0 ? (row.picks_by_stage[key] ?? 0) / eligible : 0;
	}
	function alpha(p: number): number {
		return p <= 0 ? 0 : Math.min(0.6, 0.06 + p * 0.58);
	}
	function actualIdx(row: ConsensusTeamRow): number {
		return row.actual_stage ? (STAGE_IDX[row.actual_stage] ?? -1) : -1;
	}

	// Still-in teams first (by live market odds desc, falling back to the
	// pool's own champion-pick % when the market column is off), then
	// eliminated teams — most-recently-knocked-out first. `actualIdx` is a
	// stage-progression proxy for "when": a team eliminated at the
	// semi-final necessarily went out later than one eliminated at R32, so
	// sorting eliminated teams by actualIdx descending reads as "last
	// knocked out at the top" without needing an elimination timestamp.
	// Group-stage exits (actualIdx -1) naturally sink to the very bottom.
	$: sortedRows = [...rows].sort((a, b) => {
		if (a.alive !== b.alive) return a.alive ? -1 : 1;
		if (a.alive) {
			const ma = marketByTeam[a.team];
			const mb = marketByTeam[b.team];
			if (hasMarket && ma != null && mb != null && ma !== mb) return mb - ma;
			return pct(b, 'winner') - pct(a, 'winner');
		}
		const ia = actualIdx(a);
		const ib = actualIdx(b);
		if (ia !== ib) return ib - ia;
		return pct(b, 'winner') - pct(a, 'winner');
	});
</script>

{#if loaded && rows.length > 0}
	<div class="min-[860px]:col-span-2">
		<InsightCard
			title="Consensus Bracket"
			sub={hasMarket
				? `How far the pool picked each team to go — % of ${eligible} entries per stage; blue is the live Polymarket title market`
				: `How far the pool picked each team to go — % of ${eligible} entries per stage`}
			wide
		>
			<div class="overflow-x-auto">
				<table class="w-full min-w-[420px] border-collapse text-center [font-variant-numeric:tabular-nums]">
					<thead>
						<tr>
							<th
								rowspan="2"
								class="sticky left-0 z-10 bg-base-200 pb-2 pr-3 text-left align-bottom text-[9.5px] font-extrabold uppercase tracking-[0.06em] text-base-content/40"
							>
								Team
								{#if hasMarket}
									<span class="block normal-case text-[9px] font-semibold tracking-normal text-[#3B82F6]"
										>(Polymarket odds)</span
									>
								{/if}
							</th>
							<th
								colspan={STAGES.length}
								class="border-b border-base-300/40 pb-1 text-[9px] font-extrabold uppercase tracking-[0.1em] text-base-content/35"
							>
								Pool picks
							</th>
						</tr>
						<tr>
							{#each STAGES as s (s.key)}
								<th
									class="pb-2 pt-1.5 text-[9.5px] font-extrabold uppercase tracking-[0.06em] {s.key ===
									'winner'
										? 'text-primary'
										: 'text-base-content/40'}"
								>
									{s.label}
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each sortedRows as row (row.team)}
							<tr>
								<td class="sticky left-0 z-10 whitespace-nowrap bg-base-200 py-0.5 pr-3 text-left">
									<span class="inline-flex items-center gap-1.5">
										{#if getFlagUrl(row.team)}
											<img
												src={getFlagUrl(row.team)}
												alt=""
												class="h-3 w-4 flex-none rounded-sm object-cover ring-1 ring-black/30 {row.alive
													? ''
													: 'opacity-45 grayscale'}"
												loading="lazy"
											/>
										{/if}
										<span
											class="hidden font-display text-[11.5px] font-extrabold tracking-[0.02em] min-[700px]:inline {row.alive
												? 'text-base-content'
												: 'text-base-content/30'}">{displayTeamName(row.team)}</span
										>
										<span
											class="font-display text-[11.5px] font-extrabold tracking-[0.06em] min-[700px]:hidden {row.alive
												? 'text-base-content'
												: 'text-base-content/30'}">{teamCode(row.team)}</span
										>
										{#if row.actual_stage === null}
											<span class="text-[8px] font-extrabold uppercase tracking-wide text-error">OUT · Groups</span>
										{/if}
										{#if hasMarket}
											<span class="font-mono text-[10px] font-semibold text-[#3B82F6]">
												{#if marketByTeam[row.team] != null}
													({Math.round(marketByTeam[row.team] * 100)}%)
												{:else}
													<span class="text-base-content/25">(—)</span>
												{/if}
											</span>
										{/if}
									</span>
								</td>
								{#each STAGES as s, i (s.key)}
									{@const p = pct(row, s.key)}
									<td class="p-0.5">
										<span
											class="relative block rounded-md border py-1 text-[11px] font-bold {i === actualIdx(row)
												? row.alive
													? 'border-2 border-success'
													: 'border-2 border-error'
												: 'border-base-content/10'} {p <= 0 ? 'text-base-content/40' : ''}"
											style="background: hsl(var(--p) / {alpha(p)})"
										>
											{Math.round(p * 100)}%
											{#if i === actualIdx(row)}
												<span
													class="absolute -right-1.5 -top-1.5 grid h-3.5 w-3.5 place-items-center rounded-full text-[9px] font-extrabold leading-none text-white {row.alive
														? 'bg-success'
														: 'bg-error'}"
												>
													{row.alive ? '●' : '✕'}
												</span>
											{/if}
										</span>
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<svelte:fragment slot="foot">
				Gold = share of the pool; the <span class="text-success">green ●</span> / <span
					class="text-error">red ✕</span
				> marks where each team actually ended up.
			</svelte:fragment>
		</InsightCard>
	</div>
{/if}

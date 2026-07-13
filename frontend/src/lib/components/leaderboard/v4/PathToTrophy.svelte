<script lang="ts">
	/**
	 * Path to the Trophy — every remaining bracket completion, rendered as a
	 * merged truth-table instead of a per-champion sentence. A sentence has
	 * to compress a champion's win condition into one clean AND-clause;
	 * when the real condition isn't that simple (wins on one match's result
	 * regardless of another, except for one specific combination), a
	 * sentence generator either overclaims or quietly drops a winning
	 * branch — both bugs this replaced. The table sidesteps the whole
	 * class: rows are the raw scenarios, and a champion cell spanning
	 * multiple rows means exactly what it looks like — that match's result
	 * doesn't change who wins there. See outcomeGrid.ts for the merge
	 * logic (pure, unit-tested, no sentence generation at all).
	 *
	 * Self-fetches the PUBLIC trophy-scenarios endpoint (deliberately not
	 * gated like the Win Probability tab) and live-polls so it re-derives
	 * after each game finishes. `rows` is a prop purely for entry-name
	 * resolution — the scenarios themselves come from the fetch.
	 *
	 * These are PROJECTIONS — the disclaimer copy says so.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { getTrophyScenarios } from '$lib/api/leaderboard';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { buildOutcomeGrid, type OutcomeGrid } from '$lib/utils/outcomeGrid';
	import { stageLabel } from '$lib/utils/pathToTrophy';
	import { teamCode } from '$lib/utils/teamCodes';
	import FlagCode from './FlagCode.svelte';
	import InsightCard from './InsightCard.svelte';
	import YouTag from './YouTag.svelte';

	interface Contender {
		entryId: string;
		weight: number;
	}

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined = null;

	let grid: OutcomeGrid = { columns: [], rows: [], totalWeight: 0 };
	let loaded = false;
	let stopPoll: (() => void) | undefined;
	let spotlight: string | null = null;

	$: multiOwners = multiEntryUserIds(rows);
	$: rowById = new Map(rows.map((r) => [r.entry_id, r]));

	async function refresh() {
		try {
			const res = await getTrophyScenarios();
			// Nothing left to decide (or pre-deadline / too many to enumerate): hide.
			if (!res.scenarios || res.scenarios.length <= 1) {
				grid = { columns: [], rows: [], totalWeight: 0 };
			} else {
				grid = buildOutcomeGrid(res.scenarios, res.match_meta);
			}
		} catch {
			grid = { columns: [], rows: [], totalWeight: 0 }; // network error → hide the card
		} finally {
			loaded = true;
		}
	}

	onMount(async () => {
		await refresh();
		stopPoll = startLivePoll(refresh, 60_000);
	});
	onDestroy(() => stopPoll?.());

	function nameFor(entryId: string): string {
		const row = rowById.get(entryId);
		return row ? rowDisplayName(row, multiOwners) : entryId;
	}
	function isOwn(entryIds: string[]): boolean {
		return !!userId && entryIds.some((id) => rowById.get(id)?.user_id === userId);
	}
	function positionFor(entryId: string): number | null {
		return rowById.get(entryId)?.position ?? null;
	}
	function pct(weight: number): number {
		return grid.totalWeight > 0 ? Math.round((weight / grid.totalWeight) * 100) : 0;
	}
	function fixtureLabel(col: OutcomeGrid['columns'][number]): string {
		return col.homeTeam && col.awayTeam ? `${teamCode(col.homeTeam)} v ${teamCode(col.awayTeam)}` : 'winner';
	}
	function varyingText(stages: string[]): string {
		if (stages.length === 0) return '';
		if (stages.length === grid.columns.length) return 'regardless of the rest';
		return `regardless of the ${stages.map(stageLabel).join(' and ')}`;
	}

	// Contender strip: aggregate each entry's total share across every
	// owning champion cell (a tie can put the same entry in more than one
	// cell), sorted most-likely first.
	$: contenders = (() => {
		const totals = new Map<string, number>();
		for (const r of grid.rows) {
			if (r.champion.rowSpan === 0) continue;
			for (const id of r.champion.entryIds) {
				totals.set(id, (totals.get(id) ?? 0) + r.champion.weight);
			}
		}
		return [...totals.entries()]
			.map(([entryId, weight]): Contender => ({ entryId, weight }))
			.sort((a, b) => b.weight - a.weight);
	})();
	$: leaderId = contenders[0]?.entryId ?? null;

	function toggleSpotlight(entryId: string) {
		spotlight = spotlight === entryId ? null : entryId;
	}
</script>

{#if loaded && grid.rows.length > 0}
	<div class="min-[860px]:col-span-2">
		<InsightCard
			title="Path to the Trophy"
			sub="Every way the remaining matches can go, and who lifts the pool trophy in each — computed automatically, may contain errors"
			wide
		>
			<div class="mb-3 flex flex-wrap gap-1.5">
				{#each contenders as c (c.entryId)}
					<button
						type="button"
						class="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-bold transition-colors {spotlight ===
						c.entryId
							? 'border-primary bg-primary/10'
							: 'border-base-300/60 bg-base-300/30 hover:border-primary/40'}"
						on:click={() => toggleSpotlight(c.entryId)}
					>
						{#if c.entryId === leaderId}
							<span
								class="grid h-4 w-4 flex-none place-items-center rounded-full bg-primary text-[9px] leading-none text-primary-content"
								>&#127942;</span
							>
						{:else if positionFor(c.entryId) !== null}
							<span
								class="grid h-4 w-4 flex-none place-items-center rounded-full bg-base-300 font-display text-[8.5px] font-extrabold text-base-content/55"
								>#{positionFor(c.entryId)}</span
							>
						{/if}
						<span class="max-w-[9rem] truncate">{nameFor(c.entryId)}</span>
						{#if isOwn([c.entryId])}<YouTag />{/if}
						<span class="font-mono {c.entryId === leaderId ? 'text-primary' : 'text-base-content/70'}"
							>{pct(c.weight)}%</span
						>
					</button>
				{/each}
			</div>

			<div class="overflow-x-auto">
				<table class="w-full min-w-[480px] border-collapse text-center [font-variant-numeric:tabular-nums]">
					<thead>
						<tr>
							{#each grid.columns as col (col.matchNumber)}
								<th
									class="border-b border-base-300/40 pb-2 text-[9.5px] font-extrabold capitalize tracking-[0.06em] text-base-content/40"
								>
									{stageLabel(col.stage)}
									<span class="block normal-case tracking-normal text-base-content/30">{fixtureLabel(col)}</span>
								</th>
							{/each}
							<th
								class="border-b border-base-300/40 pb-2 pl-3 text-left text-[9.5px] font-extrabold tracking-[0.06em] text-base-content/40"
							>
								Pool champion
							</th>
						</tr>
					</thead>
					<tbody>
						{#each grid.rows as row, i (i)}
							<tr>
								{#each row.cells as cell, ci (ci)}
									{#if cell.rowSpan > 0}
										<td rowspan={cell.rowSpan} class="border border-base-300/40 p-1.5 align-middle">
											<FlagCode team={cell.team} size="sm" />
										</td>
									{/if}
								{/each}
								{#if row.champion.rowSpan > 0}
									{@const lead = row.champion.entryIds.includes(leaderId ?? '')}
									{@const own = isOwn(row.champion.entryIds)}
									{@const dimmed = spotlight !== null && !row.champion.entryIds.includes(spotlight)}
									{@const spotlit = spotlight !== null && row.champion.entryIds.includes(spotlight)}
									<td
										rowspan={row.champion.rowSpan}
										class="border border-base-300/40 px-3 py-1.5 text-left align-middle transition-opacity {lead
											? 'bg-primary/[0.06] shadow-[inset_2px_0_0_theme(colors.primary)]'
											: own
												? 'bg-primary/[0.05]'
												: ''} {dimmed ? 'opacity-25' : ''} {spotlit ? 'ring-1 ring-inset ring-primary/50' : ''}"
									>
										<div class="flex items-center justify-between gap-2">
											<span class="min-w-0 truncate text-[12.5px] font-bold {lead ? 'text-primary' : ''}">
												{row.champion.entryIds.map(nameFor).join(' & ')}
											</span>
											<span class="flex-none items-center gap-1 whitespace-nowrap">
												{#if own}<YouTag />{/if}
												<b class="font-mono text-[12.5px] font-extrabold {lead ? 'text-primary' : 'text-base-content/70'}"
													>{pct(row.champion.weight)}%</b
												>
											</span>
										</div>
										{#if row.champion.varyingStages.length > 0}
											<span class="mt-0.5 block text-[10px] text-base-content/45"
												>{varyingText(row.champion.varyingStages)}</span
											>
										{/if}
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<svelte:fragment slot="foot">
				A name spanning more than one row wins either way — that match's result doesn't change it for them. %
				reflects live odds. Simulated from current picks — a fun projection, not a certainty.
			</svelte:fragment>
		</InsightCard>
	</div>
{/if}

<script lang="ts">
	/**
	 * Path to the Trophy — for every remaining bracket completion, who wins
	 * the pool. Grouped by champion, each with the match results that must
	 * happen for them (derived structurally in pathToTrophy.ts, never
	 * hand-written). Self-fetches the win-probability response (gated: a 403
	 * or a <2-scenario response simply hides the card) and live-polls so it
	 * re-derives after each game finishes. `rows` is a prop (like the other
	 * cards) purely for entry-name resolution — the scenarios themselves
	 * come from the fetch.
	 *
	 * These are PROJECTIONS — the disclaimer copy says so.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { getWinProbability } from '$lib/api/leaderboard';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { groupScenariosByChampion, stageLabel, type PathGroup } from '$lib/utils/pathToTrophy';
	import InsightCard from './InsightCard.svelte';
	import YouTag from './YouTag.svelte';

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined = null;

	let groups: PathGroup[] = [];
	let loaded = false;
	let stopPoll: (() => void) | undefined;

	$: multiOwners = multiEntryUserIds(rows);
	$: rowById = new Map(rows.map((r) => [r.entry_id, r]));

	async function refresh() {
		try {
			const res = await getWinProbability();
			// Nothing left to decide (or too many scenarios / gated-off): hide.
			if (!res.scenarios || res.scenarios.length <= 1) {
				groups = [];
			} else {
				groups = groupScenariosByChampion(res.scenarios, res.match_meta);
			}
		} catch {
			groups = []; // 403 (flag off) or error → hide the card
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
	function isOwn(entryId: string): boolean {
		return !!userId && rowById.get(entryId)?.user_id === userId;
	}
	function positionFor(entryId: string): number | null {
		return rowById.get(entryId)?.position ?? null;
	}

	function clause(fm: PathGroup['fixedMatches'][number]): string {
		return fm.stage === 'final'
			? `${fm.winningTeam} win the final`
			: `${fm.winningTeam} win their ${stageLabel(fm.stage)}`;
	}
	function condition(g: PathGroup): string {
		if (g.winsUnconditionally) return 'Champion no matter how the rest plays out';
		const clauses = g.fixedMatches.map(clause);
		const joined =
			clauses.length <= 1
				? clauses.join('')
				: `${clauses.slice(0, -1).join(', ')} and ${clauses[clauses.length - 1]}`;
		return g.scenarioCount === 1 ? `Champion only if ${joined}` : `Champion whenever ${joined}`;
	}
	function pct(g: PathGroup): number {
		return Math.round(g.totalWeight * 100);
	}
</script>

{#if loaded && groups.length > 0}
	<div class="min-[860px]:col-span-2">
		<InsightCard
			title="Path to the Trophy"
			sub="A projection of who wins the pool under each remaining outcome — computed automatically, may contain errors"
			wide
		>
			<div class="flex flex-col gap-1">
				{#each groups as g (g.entryId)}
					<div
						class="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2.5 rounded-lg px-1.5 py-1 {isOwn(
							g.entryId
						)
							? 'bg-primary/[0.07] shadow-[inset_2px_0_0_theme(colors.primary)]'
							: ''}"
					>
						<div class="min-w-0">
							<span class="flex items-center gap-1.5 text-xs font-semibold">
								{#if positionFor(g.entryId) !== null}
									<span class="font-display text-[11px] font-extrabold text-base-content/45"
										>#{positionFor(g.entryId)}</span
									>
								{/if}
								<span class="truncate">{nameFor(g.entryId)}</span>
								{#if isOwn(g.entryId)}<YouTag />{/if}
							</span>
							<span class="mt-0.5 block text-[11px] leading-snug text-base-content/55">
								{condition(g)}
							</span>
						</div>
						<b class="whitespace-nowrap font-mono text-[13px] font-extrabold text-primary"
							>{pct(g)}%</b
						>
					</div>
				{/each}
			</div>
			<svelte:fragment slot="foot">
				Simulated from current picks and live odds — a fun projection, not a certainty.
			</svelte:fragment>
		</InsightCard>
	</div>
{/if}

<script lang="ts">
	/**
	 * Path to the Trophy — for every remaining bracket completion, who wins
	 * the pool. Grouped by champion, each with the match results that must
	 * happen for them (derived structurally in pathToTrophy.ts, never
	 * hand-written). Self-fetches the PUBLIC trophy-scenarios endpoint
	 * (deliberately not gated like the Win Probability tab — a <2-scenario
	 * or pre-deadline empty response simply hides the card) and live-polls
	 * so it re-derives after each game finishes. `rows` is a prop (like the
	 * other cards) purely for entry-name resolution — the scenarios
	 * themselves come from the fetch.
	 *
	 * These are PROJECTIONS — the disclaimer copy says so.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { getTrophyScenarios } from '$lib/api/leaderboard';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import { startLivePoll } from '$lib/utils/livePoll';
	import { groupScenariosByChampion, stageLabel, type PathGroup } from '$lib/utils/pathToTrophy';
	import FlagCode from './FlagCode.svelte';
	import InsightCard from './InsightCard.svelte';
	import YouTag from './YouTag.svelte';

	type ConditionPart = { kind: 'team'; team: string } | { kind: 'text'; text: string };

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined = null;

	let groups: PathGroup[] = [];
	let loaded = false;
	let stopPoll: (() => void) | undefined;

	$: multiOwners = multiEntryUserIds(rows);
	$: rowById = new Map(rows.map((r) => [r.entry_id, r]));

	async function refresh() {
		try {
			const res = await getTrophyScenarios();
			// Nothing left to decide (or pre-deadline / too many to enumerate): hide.
			if (!res.scenarios || res.scenarios.length <= 1) {
				groups = [];
			} else {
				groups = groupScenariosByChampion(res.scenarios, res.match_meta);
			}
		} catch {
			groups = []; // network error → hide the card
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

	// Structured parts (not a flat string) so the template can interleave
	// <FlagCode> chips with the surrounding text — flags make the sentence
	// scannable at a glance instead of a wall of team names, and letting
	// this wrap across lines (no truncate/nowrap anywhere) is what keeps
	// a 3-clause condition from ever getting clipped.
	function conditionParts(g: PathGroup): ConditionPart[] {
		if (g.winsUnconditionally) {
			return [{ kind: 'text', text: 'Champion no matter how the rest plays out' }];
		}
		const n = g.fixedMatches.length;
		const parts: ConditionPart[] = [
			{ kind: 'text', text: g.scenarioCount === 1 ? 'Champion only if ' : 'Champion whenever ' }
		];
		g.fixedMatches.forEach((fm, i) => {
			if (i > 0) parts.push({ kind: 'text', text: i === n - 1 ? ' and ' : ', ' });
			parts.push({ kind: 'team', team: fm.winningTeam });
			parts.push({
				kind: 'text',
				text: fm.stage === 'final' ? ' win the final' : ` win their ${stageLabel(fm.stage)}`
			});
		});
		return parts;
	}
	function pct(g: PathGroup): number {
		return Math.round(g.totalWeight * 100);
	}
	$: maxPct = groups.length ? Math.max(...groups.map(pct)) : 1;
</script>

{#if loaded && groups.length > 0}
	<div class="min-[860px]:col-span-2">
		<InsightCard
			title="Path to the Trophy"
			sub="A projection of who wins the pool under each remaining outcome — computed automatically, may contain errors"
			wide
		>
			<div class="flex flex-col gap-1.5">
				{#each groups as g, i (g.entryId)}
					<div
						class="rounded-xl px-2.5 py-2 {i === 0
							? 'border border-primary/35 bg-primary/[0.06] shadow-[0_0_16px_-4px_theme(colors.primary/40%)]'
							: 'border border-transparent'} {isOwn(g.entryId) && i !== 0
							? 'bg-primary/[0.07] shadow-[inset_2px_0_0_theme(colors.primary)]'
							: ''}"
					>
						<div class="flex items-center gap-2">
							{#if i === 0}
								<span
									class="grid h-5 w-5 flex-none place-items-center rounded-full bg-primary text-[11px] leading-none text-primary-content"
									title="Most likely outcome"
									>&#127942;</span
								>
							{:else if positionFor(g.entryId) !== null}
								<span
									class="grid h-5 w-5 flex-none place-items-center rounded-full bg-base-300 font-display text-[10px] font-extrabold text-base-content/55"
									>#{positionFor(g.entryId)}</span
								>
							{/if}
							<span class="min-w-0 flex-1 truncate text-[13px] font-bold">
								{nameFor(g.entryId)}
							</span>
							{#if isOwn(g.entryId)}<YouTag />{/if}
							<b class="whitespace-nowrap font-mono text-sm font-extrabold {i === 0 ? 'text-primary' : 'text-base-content/80'}"
								>{pct(g)}%</b
							>
						</div>
						<div class="mt-1 h-1 w-full overflow-hidden rounded-full bg-base-300/50">
							<span
								class="block h-full rounded-full {i === 0 ? 'bg-primary' : 'bg-primary/40'}"
								style="width:{(pct(g) / maxPct) * 100}%"
							></span>
						</div>
						<p class="mt-1.5 text-[11.5px] leading-relaxed text-base-content/60">
							{#each conditionParts(g) as part}
								{#if part.kind === 'team'}
									<FlagCode team={part.team} size="sm" />
								{:else}
									{part.text}
								{/if}
							{/each}
						</p>
					</div>
				{/each}
			</div>
			<svelte:fragment slot="foot">
				Simulated from current picks and live odds — a fun projection, not a certainty.
			</svelte:fragment>
		</InsightCard>
	</div>
{/if}

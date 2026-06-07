<!--
  19-pill points-by-source strip per mockup section 4.4:
    12 group cells (A–L) + 1 group-stage bonus pill + vertical divider
    + 5 locked knockout cells (R32/R16/QF/SF/F) + 1 locked knockout-bonus

  Group cells derive client-side via computeGroupTotals from fixtures +
  active entry's predictions. Bonus pill reads bonus_question_points
  from the active entry's leaderboard breakdown. Knockouts are all
  locked/awaiting in this version (we don't yet derive per-stage KO
  scoring — defer to backend exposure).
-->
<script lang="ts">
	import { fixtures } from '$stores/fixtures';
	import { activeBreakdown } from '$stores/missionDerived';
	import { computeGroupTotals, type GroupKey } from '$lib/utils/groupPoints';
	import type { MatchPrediction } from '$types';

	/** The active entry's match predictions (passed in so we don't have
	 *  two components racing to fetch the same data). */
	export let predictions: MatchPrediction[] = [];

	const GROUPS: GroupKey[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];
	const KO_ROUNDS = ['R32', 'R16', 'QF', 'SF', 'F'];

	$: groupTotals = computeGroupTotals($fixtures, predictions);
	$: groupTotalSum = Object.values(groupTotals).reduce((a, b) => a + b, 0);
	$: bonusPoints = $activeBreakdown?.bonus_question_points ?? 0;
</script>

<section class="stadium-card no-glow p-5 mb-4">
	<div class="flex items-center justify-between mb-3">
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55">
			Points by source
		</span>
		<a href="/results" class="text-xs font-semibold text-primary hover:underline">
			Full results →
		</a>
	</div>

	<div class="overflow-x-auto">
		<div
			class="grid items-stretch gap-y-2"
			style="grid-template-columns: repeat(13, minmax(36px,1fr)) 1px repeat(6, minmax(36px,1fr)); column-gap: 7px;"
		>
			<!-- Phase captions -->
			<div
				class="text-[9.5px] font-extrabold uppercase tracking-[0.14em] text-base-content/55"
				style="grid-column: 1 / 14; grid-row: 1;"
			>
				Group stage · {groupTotalSum} pts
			</div>
			<div
				class="text-[9.5px] font-extrabold uppercase tracking-[0.14em] text-base-content/55"
				style="grid-column: 15 / 21; grid-row: 1;"
			>
				Knockouts · awaiting
			</div>

			<!-- Vertical divider -->
			<div
				style="grid-column: 14; grid-row: 1 / 3; width: 1px; justify-self: center; background: rgba(42,53,82,0.65);"
			></div>

			<!-- Group A-L pills -->
			{#each GROUPS as g, i}
				{@const v = groupTotals[g]}
				{@const live = v > 0}
				<div
					class="rounded-btn flex flex-col items-center justify-center gap-1 py-2 border"
					style:grid-column={String(i + 1)}
					style:grid-row="2"
					style:height="56px"
					style:background={live ? 'rgba(212,175,55,0.16)' : 'rgba(42,53,82,0.20)'}
					style:border-color={live ? 'rgba(212,175,55,0.30)' : 'transparent'}
				>
					<span
						class="font-display text-[11px]"
						style:color={live ? 'var(--p, #D4AF37)' : 'rgba(226,232,240,0.55)'}
					>
						{g}
					</span>
					<span
						class="font-display text-base leading-none"
						style:color={live ? 'var(--bc, #E2E8F0)' : 'rgba(226,232,240,0.30)'}
					>
						{v}
					</span>
				</div>
			{/each}

			<!-- Group-stage bonus pill (col 13) -->
			<div
				class="rounded-btn flex flex-col items-center justify-center gap-1 py-2 border"
				style="grid-column: 13; grid-row: 2; height: 56px; background: rgba(5,150,105,0.18); border-color: rgba(5,150,105,0.38);"
				title="Group-stage bonus"
			>
				<span class="text-xs leading-none" style="color: #34d399;">✦</span>
				<span class="font-display text-sm leading-none" style="color: #34d399;">
					+{bonusPoints}
				</span>
			</div>

			<!-- Knockout pills (cols 15-19) — all locked -->
			{#each KO_ROUNDS as r, i}
				<div
					class="rounded-btn flex flex-col items-center justify-center gap-1 py-2"
					style:grid-column={String(15 + i)}
					style:grid-row="2"
					style:height="56px"
					style:background="rgba(42,53,82,0.16)"
					style:border="1px dashed rgba(42,53,82,0.6)"
					title="{r} · locked"
				>
					<span class="font-display text-[11px] text-base-content/55">{r}</span>
					<span class="text-xs text-base-content/30">🔒</span>
				</div>
			{/each}

			<!-- Knockout bonus pill (col 20) — locked -->
			<div
				class="rounded-btn flex flex-col items-center justify-center gap-1 py-2"
				style="grid-column: 20; grid-row: 2; height: 56px; background: rgba(42,53,82,0.16); border: 1px dashed rgba(42,53,82,0.6);"
				title="Knockout bonus · locked"
			>
				<span class="text-xs leading-none text-base-content/55">✦</span>
				<span class="text-xs text-base-content/30">🔒</span>
			</div>
		</div>
	</div>
</section>

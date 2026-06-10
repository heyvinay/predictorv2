<script lang="ts">
	/** Slim gold-tinted info strip explaining the active round's scoring.
	 *  EVERY number templates from scoring-rules (spec C.1) — a yml change
	 *  updates this copy with no code edit. KO copy re-anchors the banking
	 *  causation per spec C.2. Vocabulary: Result / Exact — never "Outcome". */
	import type { RoundId, ScoringRules } from '$lib/types/results';
	import { ROUND_LABELS, NEXT_ROUND, isKnockoutRound } from '$lib/utils/resultsRounds';
	import { stagePointsForRound } from '$lib/utils/koPoints';

	export let roundId: RoundId;
	export let rules: ScoringRules;
	/** "19 Jul" — the final's date, for the Winner copy. '' hides the clause. */
	export let finalDate = '';

	$: exactTotal = rules.match.correct_outcome + rules.match.exact_score;
	$: resultPts = rules.match.correct_outcome;
	$: winnerPts = rules.advancement.winner;
	$: roundLabel = ROUND_LABELS[roundId];
	$: stagePts = isKnockoutRound(roundId) ? stagePointsForRound(rules.advancement, roundId) : 0;
	$: nextId = NEXT_ROUND[roundId] ?? null;
	$: nextLabel = nextId ? ROUND_LABELS[nextId] : null;
	$: prevLabel =
		roundId === 'r32'
			? 'the group stage'
			: roundId === 'r16'
			? 'the Round of 32'
			: roundId === 'qf'
			? 'the Round of 16'
			: roundId === 'sf'
			? 'the Quarter-Finals'
			: roundId === 'f'
			? 'the Semi-Finals'
			: '';
</script>

<div
	class="mt-4 flex items-start gap-2.5 rounded-btn border border-primary/25 bg-primary/10 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-base-content/80"
>
	<span class="text-primary" aria-hidden="true">ⓘ</span>
	{#if roundId === 'summary'}
		<span>
			<b>Summary</b> — points across every round of the tournament for the selected entry.
			<b>Group stage</b> rounds award <b>+{exactTotal} exact / +{resultPts} result</b> plus a
			<b>rarity bonus</b>; <b>knockout</b> rounds award stage-specific points per bracket pick
			that reaches the round. Tap any row to jump to that round.
		</span>
	{:else if roundId === 'winner'}
		<span>
			<b>How Winner scoring works:</b> you earn
			<b>+{winnerPts} if your champion pick lifts the trophy</b>. Points are awarded when the
			final whistle blows{finalDate ? ` on ${finalDate}` : ''}. No rarity bonus.
		</span>
	{:else if isKnockoutRound(roundId)}
		<span>
			<b>How {roundLabel} scoring works:</b> you earn
			<b>+{stagePts} for each team in your bracket that reaches this round</b>.
			<b>
				These points are banked from your bracket pick — you earned them when each team
				finished {prevLabel}. The match score below decides who walks to
				{nextLabel ?? 'the trophy'}, not these points.
			</b>
			No rarity bonus in the knockouts.
		</span>
	{:else}
		<span>
			<b>How {roundLabel} scoring works:</b> <b>+{exactTotal}</b> for the exact score,
			<b>+{resultPts}</b> for the correct result — plus a <b>rarity bonus</b> on top when your
			correct pick was one few others made.
		</span>
	{/if}
</div>

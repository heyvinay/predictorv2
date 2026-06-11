<script lang="ts">
	/** Small ℹ button anchored to the 'Points' table header; clicking it
	 *  pops a card showing the round-scoring rules — the same copy that
	 *  used to live in the always-on RoundExplainer banner. Numbers come
	 *  from scoring-rules so a YAML change updates this copy too. */
	import type { RoundId, ScoringRules } from '$lib/types/results';
	import { ROUND_LABELS, NEXT_ROUND, isKnockoutRound } from '$lib/utils/resultsRounds';
	import { stagePointsForRound } from '$lib/utils/koPoints';

	export let roundId: RoundId;
	export let rules: ScoringRules;

	let open = false;
	let containerEl: HTMLSpanElement;

	$: exactTotal = rules.match.correct_outcome + rules.match.exact_score;
	$: resultPts = rules.match.correct_outcome;
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

	function onWindowClick(e: MouseEvent) {
		if (!open || !containerEl) return;
		if (!containerEl.contains(e.target as Node)) open = false;
	}
	function onKey(e: KeyboardEvent) {
		if (open && e.key === 'Escape') open = false;
	}
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<span bind:this={containerEl} class="relative inline-flex">
	<button
		type="button"
		class="grid h-4 w-4 place-items-center rounded-full text-[11px] text-base-content/55 transition-colors hover:bg-primary/15 hover:text-primary"
		aria-label="How {roundLabel} scoring works"
		aria-expanded={open}
		on:click|stopPropagation={() => (open = !open)}>ⓘ</button
	>

	{#if open}
		<div
			class="absolute right-0 top-[calc(100%+6px)] z-30 w-[280px] rounded-box border border-primary/30 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed tracking-normal text-base-content/85 shadow-card"
			role="dialog"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">
				How {roundLabel} scoring works
			</div>
			{#if isKnockoutRound(roundId)}
				<p>
					You earn <b>+{stagePts}</b> for each team in your bracket that reaches this round.
				</p>
				<p class="mt-1.5">
					These points are <b>banked from your bracket pick</b> — you earned them when each
					team finished {prevLabel}. The match score below decides who walks to
					{nextLabel ?? 'the trophy'}, not these points. No rarity bonus in the knockouts.
				</p>
			{:else}
				<p>
					<b>+{exactTotal}</b> for the exact score, <b>+{resultPts}</b> for the correct
					result — plus a <b>rarity bonus</b> on top when your correct pick was one few
					others made.
				</p>
			{/if}
		</div>
	{/if}
</span>

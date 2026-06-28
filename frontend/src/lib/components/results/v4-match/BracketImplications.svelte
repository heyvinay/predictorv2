<script lang="ts">
	/** Bracket Implications — per outcome, count of entries with the same
	 *  team still threaded through later stages of their bracket.
	 *
	 *  Quantifies the ripple. A R32 match isn't just N points — it's the
	 *  gate that keeps N entries' QF picks alive. Makes a "boring" group-
	 *  stage match feel like stakes. */
	import type { Fixture } from '$types';
	import type {
		KoImplicationSide,
		KoMatchDetailResponse,
		ScoringRules
	} from '$lib/types/results';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;
	export let scoringRules: ScoringRules | null;

	// "alive at later stage" rows depend on what stage this fixture is —
	// no point showing alive_r16 on a quarter-final detail page.
	const STAGE_ORDER = [
		'round_of_32',
		'round_of_16',
		'quarter_final',
		'semi_final',
		'final',
		'winner'
	] as const;
	type Stage = (typeof STAGE_ORDER)[number];

	const STAGE_FIELD: Record<Exclude<Stage, 'round_of_32'>, keyof KoImplicationSide> = {
		round_of_16: 'alive_r16',
		quarter_final: 'alive_qf',
		semi_final: 'alive_sf',
		final: 'alive_final',
		winner: 'alive_winner'
	};

	const STAGE_LABEL: Record<Stage, string> = {
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'Final',
		winner: 'Champion'
	};

	$: thisStage = fixture.stage as Stage;
	$: futureStages = (() => {
		const idx = STAGE_ORDER.indexOf(thisStage);
		if (idx < 0) return [] as Stage[];
		return STAGE_ORDER.slice(idx + 1) as Stage[];
	})();

	$: outcomePoints = scoringRules?.advancement[thisStage] as number | undefined;

	function readField(side: KoImplicationSide, stage: Stage): number {
		if (stage === 'round_of_32') return side.r32_outcome;
		return side[STAGE_FIELD[stage as Exclude<Stage, 'round_of_32'>]] as number;
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">What's riding on this match</span>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
			>bracket ripple</span
		>
	</div>

	<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
		{#each [{ side: bundle.implications.home, label: bundle.home_team, color: 'amber' }, { side: bundle.implications.away, label: bundle.away_team, color: 'emerald' }] as outcome}
			<div
				class="rounded-btn border border-base-300/50 bg-base-300/15 p-3 {outcome.color === 'amber'
					? 'border-l-[3px] border-l-amber-400'
					: 'border-l-[3px] border-l-emerald-400'}"
			>
				<div class="mb-2 text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55">
					If <strong class="text-base-content"><TeamName name={outcome.label} /></strong> advances
				</div>

				<!-- Immediate outcome -->
				<div class="flex items-center justify-between border-b border-base-300/30 py-1.5">
					<span class="text-[12px] text-base-content/70">Outcome banks for</span>
					<span class="font-display text-[16px] font-bold text-primary"
						>{outcome.side.r32_outcome}
						<span class="text-[10.5px] font-semibold text-base-content/55"
							>{outcome.side.r32_outcome === 1 ? 'entry' : 'entries'}{outcomePoints !== undefined
								? ` · +${outcomePoints}`
								: ''}</span
						></span
					>
				</div>

				<!-- Future stages alive count -->
				{#each futureStages as fs}
					<div class="flex items-center justify-between border-b border-base-300/30 py-1.5 last:border-b-0">
						<span class="text-[12px] text-base-content/70">
							{#if fs === 'winner'}
								Still alive as Champion
							{:else}
								Still alive in {STAGE_LABEL[fs]}
							{/if}
						</span>
						<span
							class="font-display text-[15px] font-bold {readField(outcome.side, fs) > 0
								? 'text-base-content'
								: 'text-base-content/30'}">{readField(outcome.side, fs)}</span
						>
					</div>
				{/each}
			</div>
		{/each}
	</div>
</div>

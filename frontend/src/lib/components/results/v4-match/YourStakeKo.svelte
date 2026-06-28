<script lang="ts">
	/** Your Stake — the personal headline card for a knockout fixture.
	 *
	 *  Answers "do I care about this match?" within two seconds:
	 *   - which side you picked to advance (pill + flag)
	 *   - points-at-stake on this specific fixture (scoring.advancement[stage])
	 *   - bracket-path strip showing the downstream stages where the same
	 *     team is alive in your bracket — lights up the chain of future
	 *     points that depend on this one outcome
	 *
	 *  Falls back to a neutral "no pick on file" state if the user's
	 *  bracket isn't loaded yet or doesn't contain either team. */
	import type { Fixture } from '$types';
	import type { BracketPrediction } from '$types';
	import type { KoMatchDetailResponse, ScoringRules } from '$lib/types/results';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;
	export let bracket: BracketPrediction | null;
	export let scoringRules: ScoringRules | null;
	export let mode: 'played' | 'upcoming';

	// Stage order from the current fixture's stage onward — these are
	// the steps the path strip walks through.
	const KO_STAGE_ORDER = [
		'round_of_32',
		'round_of_16',
		'quarter_final',
		'semi_final',
		'final',
		'winner'
	] as const;
	type KoStage = (typeof KO_STAGE_ORDER)[number];

	const STAGE_LABEL: Record<KoStage, string> = {
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'F',
		winner: 'W'
	};

	// Resolve the user's pick for THIS fixture: whichever side appears in
	// their R32 (or R16/QF/SF/F if this is a later round) advancement list.
	$: thisStage = fixture.stage as KoStage;
	$: bracketListForStage = (() => {
		if (!bracket) return [] as string[];
		switch (thisStage) {
			case 'round_of_32':
				return bracket.round_of_32 ?? [];
			case 'round_of_16':
				return bracket.round_of_16 ?? [];
			case 'quarter_final':
				return bracket.quarter_finals ?? [];
			case 'semi_final':
				return bracket.semi_finals ?? [];
			case 'final':
				return bracket.final ?? [];
			default:
				return [] as string[];
		}
	})();

	$: pick = (() => {
		const home = bundle.home_team;
		const away = bundle.away_team;
		if (bracketListForStage.includes(home)) return home;
		if (bracketListForStage.includes(away)) return away;
		return null;
	})();

	$: stagePoints = (() => {
		if (!scoringRules) return null;
		const val = scoringRules.advancement[thisStage];
		return typeof val === 'number' ? val : null;
	})();

	// Bracket path: for each KO stage AFTER thisStage, does the user have
	// the same `pick` team listed? Lit cell = same team; dim cell = future
	// stages they haven't bet this team on.
	function teamInStage(team: string, stage: KoStage): boolean {
		if (!bracket) return false;
		switch (stage) {
			case 'round_of_32':
				return (bracket.round_of_32 ?? []).includes(team);
			case 'round_of_16':
				return (bracket.round_of_16 ?? []).includes(team);
			case 'quarter_final':
				return (bracket.quarter_finals ?? []).includes(team);
			case 'semi_final':
				return (bracket.semi_finals ?? []).includes(team);
			case 'final':
				return (bracket.final ?? []).includes(team);
			case 'winner':
				return bracket.winner === team;
			default:
				return false;
		}
	}

	$: futureStages = (() => {
		const idx = KO_STAGE_ORDER.indexOf(thisStage);
		if (idx < 0) return [] as KoStage[];
		return KO_STAGE_ORDER.slice(idx + 1);
	})();

	$: pathCells = pick
		? futureStages.map((s) => ({
				stage: s,
				label: STAGE_LABEL[s],
				alive: teamInStage(pick, s)
			}))
		: [];

	// Maximum cumulative payout if `pick` keeps winning through every stage
	// the user has them at. Helps the user feel the chain, not just one cell.
	$: chainPoints = (() => {
		if (!pick || !scoringRules) return null;
		const stages: KoStage[] = [thisStage, ...futureStages];
		return stages
			.filter((s) => teamInStage(pick!, s))
			.reduce((sum, s) => sum + ((scoringRules!.advancement[s] as number) ?? 0), 0);
	})();
</script>

<div
	class="relative overflow-hidden rounded-box border border-primary/40 bg-base-200 p-4 shadow-card"
>
	<!-- Gold rail on the left to mark this as the headline card -->
	<div class="absolute left-0 top-3 bottom-3 w-[3px] rounded-full bg-primary"></div>

	<div class="mb-3 flex items-center justify-between gap-2 pl-1">
		<h3 class="font-display text-[15px] font-extrabold tracking-tight">Your stake</h3>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55">
			{mode === 'played' ? 'Match decided' : 'Match upcoming'}
		</span>
	</div>

	{#if !bracket}
		<!-- Bracket hasn't hydrated yet — the rest of the page can read but
		     this card waits for the user's picks. -->
		<div class="text-[12.5px] text-base-content/55">Loading your bracket…</div>
	{:else if !pick}
		<!-- Defensive: bracket exists but neither team is in the user's
		     advancement list for this stage. Should be impossible for a
		     completed bracket, but better than rendering an empty hero. -->
		<div class="text-[12.5px] text-base-content/55">
			Neither <TeamName name={bundle.home_team} /> nor <TeamName name={bundle.away_team} /> is in
			your bracket for this round.
		</div>
	{:else}
		<div class="mb-3 flex flex-wrap items-center gap-2 pl-1 text-[12.5px]">
			<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
				>You picked</span
			>
			<span class="inline-flex items-center gap-2 rounded-full bg-primary/20 px-3 py-1 font-bold text-primary">
				{#if hasFlag(pick)}
					<img src={getFlagUrl(pick, 'sm')} alt="" class="h-3 w-[18px] rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<TeamName name={pick} />
				<span class="text-[10.5px] font-semibold opacity-70">to advance</span>
			</span>
		</div>

		<!-- Points band — what THIS match pays out if your pick is right. -->
		{#if stagePoints !== null}
			<div
				class="mb-3 flex items-center justify-between rounded-btn bg-base-300/30 px-3 py-2.5"
			>
				<span class="text-[12.5px] text-base-content/70">
					{#if mode === 'played'}If <TeamName name={pick} forceCode /> advanced, this banks{:else}If <TeamName name={pick} forceCode /> advances, this match pays{/if}
				</span>
				<span class="font-display text-[20px] font-extrabold text-success">+{stagePoints}</span>
			</div>
		{/if}

		<!-- Bracket-path strip — downstream stages where the same team is
		     alive in your bracket. Empty when you're on the Final. -->
		{#if pathCells.length > 0}
			<div class="rounded-btn bg-base-300/20 px-3 py-3">
				<div
					class="mb-2 text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
				>
					Your {teamCode(pick)} path through the bracket
				</div>
				<div class="flex items-center gap-1.5">
					{#each pathCells as cell, i (cell.stage)}
						<div
							class="flex flex-1 flex-col items-center rounded-btn border px-1.5 py-1.5 text-center text-[10.5px] {cell.alive
								? 'border-primary/40 bg-primary/15 font-bold text-primary'
								: 'border-base-300/40 text-base-content/45'}"
						>
							<span class="text-[11px] font-extrabold">{cell.label}</span>
							<span class="text-[9.5px] opacity-80">
								{cell.alive ? 'picked' : '—'}
							</span>
						</div>
						{#if i < pathCells.length - 1}
							<span class="text-[10px] text-base-content/30">→</span>
						{/if}
					{/each}
				</div>

				{#if chainPoints !== null && chainPoints > (stagePoints ?? 0)}
					<div class="mt-2 text-[11.5px] text-base-content/65">
						If <TeamName name={pick} forceCode /> keeps winning, max chain payout:
						<strong class="text-primary">+{chainPoints} pts</strong>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<script lang="ts">
	/** Your Stake — the personal headline card for a knockout fixture (v2.184.x rewrite).
	 *
	 *  Three cases per fixture:
	 *
	 *  1. NEITHER — neither team is in your "bank stage" picks (the list
	 *     of teams you've predicted to advance OUT of this round). No
	 *     stake on this match's advancement credit.
	 *
	 *  2. ONE — one side is in your bank-stage list. Standard "I have a
	 *     pick" case. Surfaces the chain of further stages where the
	 *     same team carries deeper stakes.
	 *
	 *  3. BOTH — both teams are in your bank-stage list (Q1, Q2). You
	 *     bank the advancement credit either way — outcome-immune at THIS
	 *     stage. The page now flags this with a GUARANTEED banner and
	 *     renders both team paths side-by-side so the deeper-stake
	 *     asymmetry is visible (Q2 — "one team I have at QF, other only at
	 *     R16").
	 *
	 *  Bank stage = the stage that the winner of THIS fixture advances TO.
	 *  For an R32 fixture, that's round_of_16 — i.e., the relevant pick
	 *  list is `bracket.round_of_16`. A previous version checked
	 *  `bracket.round_of_32` (= group qualifiers list), which is the
	 *  user's prediction at submission time about who reaches R32, not
	 *  who wins R32. That bug is fixed here.
	 */
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

	// Bracket-pick stages — increasing depth. Each maps to an advancement
	// point payout in scoring config + a list in BracketPrediction.
	const BRACKET_STAGES = [
		'round_of_16',
		'quarter_final',
		'semi_final',
		'final',
		'winner'
	] as const;
	type BracketStage = (typeof BRACKET_STAGES)[number];

	const STAGE_LABEL: Record<BracketStage, string> = {
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'F',
		winner: 'W'
	};

	// Long-form labels for the explicit framing sentence (Q11 — give
	// cold readers an anchor like "Your R16 pick: Brazil" instead of
	// asking them to infer the bank stage from the path strip).
	const STAGE_NAME: Record<BracketStage, string> = {
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-final',
		semi_final: 'Semi-final',
		final: 'Final',
		winner: 'Champion'
	};

	// Map a fixture's stage to the bracket stage its winner advances INTO
	// (the "bank stage" — points pay out when team reaches it).
	const BANK_STAGE_FOR_FIXTURE: Record<string, BracketStage> = {
		round_of_32: 'round_of_16',
		round_of_16: 'quarter_final',
		quarter_final: 'semi_final',
		semi_final: 'final',
		final: 'winner'
	};

	$: bankStage = (BANK_STAGE_FOR_FIXTURE[fixture.stage] ?? 'round_of_16') as BracketStage;

	function teamInStage(b: BracketPrediction | null, team: string, stage: BracketStage): boolean {
		if (!b) return false;
		switch (stage) {
			case 'round_of_16':
				return (b.round_of_16 ?? []).includes(team);
			case 'quarter_final':
				return (b.quarter_finals ?? []).includes(team);
			case 'semi_final':
				return (b.semi_finals ?? []).includes(team);
			case 'final':
				return (b.final ?? []).includes(team);
			case 'winner':
				return b.winner === team;
		}
	}

	interface SideStake {
		team: string;
		isStaked: boolean; // in user's bank-stage pick list?
		stagedAt: BracketStage[]; // every stage where team appears in bracket
		deepestStage: BracketStage | null;
		chainPoints: number; // sum of advancement points across stagedAt
		bankPoints: number; // points awarded for THIS fixture's advancement
	}

	function analyzeSide(team: string): SideStake {
		const stagedAt: BracketStage[] = bracket
			? BRACKET_STAGES.filter((s) => teamInStage(bracket, team, s))
			: [];
		const deepestStage = stagedAt.length > 0 ? stagedAt[stagedAt.length - 1] : null;
		const chainPoints =
			scoringRules && bracket
				? stagedAt.reduce((sum, s) => sum + ((scoringRules!.advancement[s] as number) ?? 0), 0)
				: 0;
		const bankPoints = (scoringRules?.advancement[bankStage] as number) ?? 0;
		return {
			team,
			isStaked: stagedAt.includes(bankStage),
			stagedAt,
			deepestStage,
			chainPoints,
			bankPoints
		};
	}

	$: homeStake = analyzeSide(bundle.home_team);
	$: awayStake = analyzeSide(bundle.away_team);

	$: stakeCase = (() => {
		if (!bracket) return 'loading' as const;
		if (homeStake.isStaked && awayStake.isStaked) return 'both' as const;
		if (homeStake.isStaked || awayStake.isStaked) return 'one' as const;
		return 'none' as const;
	})();

	$: bankPoints = (scoringRules?.advancement[bankStage] as number) ?? 0;

	// For ONE case: which side is the user staked on (used in the explicit
	// framing sentence and the single-card layout).
	$: stakedSide = homeStake.isStaked ? homeStake : awayStake;

	// Helper for template expressions — Svelte template parses {...} as JS
	// (NOT TS), so `as number` casts inside the template fail to compile.
	// Keep the cast inside this script function and call it from the markup.
	function stagePoints(stage: BracketStage): number {
		const v = scoringRules?.advancement[stage];
		return typeof v === 'number' ? v : 0;
	}

	// Stages to render in the path strip (everything from the bank stage onward).
	$: pathStages = (() => {
		const idx = BRACKET_STAGES.indexOf(bankStage);
		return idx < 0 ? [] : (BRACKET_STAGES.slice(idx) as BracketStage[]);
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

	{#if stakeCase === 'loading'}
		<div class="pl-1 text-[12.5px] text-base-content/55">Loading your bracket…</div>
	{:else if stakeCase === 'none'}
		<div class="pl-1 text-[12.5px] text-base-content/55">
			Neither <TeamName name={bundle.home_team} /> nor <TeamName name={bundle.away_team} /> is in your
			bracket for this round — no advancement credit at stake for you on this fixture.
		</div>
	{:else}
		<!-- Explicit framing sentence (Q11/Q12) — names the user's pick(s)
		     and the bank-stage payout in one short sentence above the path
		     strip, so a cold reader doesn't need to decode the visual. -->
		{#if stakeCase === 'one'}
			<div class="mb-3 pl-1 text-[12.5px] text-base-content/85">
				Your <strong class="text-primary">{STAGE_NAME[bankStage]}</strong> pick:
				<strong><TeamName name={stakedSide.team} /></strong>. Banks
				<strong class="text-success">+{bankPoints}</strong>
				{mode === 'played' ? 'if' : 'when'}
				{teamCode(stakedSide.team)} advances.
			</div>
		{:else}
			<div class="mb-3 pl-1 text-[12.5px] text-base-content/85">
				You picked <strong><TeamName name={bundle.home_team} /></strong> AND
				<strong><TeamName name={bundle.away_team} /></strong> to advance to
				<strong class="text-primary">{STAGE_NAME[bankStage]}</strong> — either side wins
				you the credit.
			</div>
		{/if}

		<!-- BOTH case banner — outcome-immune advancement credit. Only renders
		     when both teams sit in the user's bank-stage pick list. -->
		{#if stakeCase === 'both'}
			<div
				class="mb-3 flex items-center justify-between rounded-btn border border-success/40 bg-success/15 px-3 py-2.5"
			>
				<div class="flex items-center gap-2 text-[12px] font-bold text-success">
					<span class="text-[14px]" aria-hidden="true">✓</span>
					<span class="uppercase tracking-[0.12em]">Guaranteed</span>
					<span class="font-normal normal-case opacity-90"
						>— you bank this round either way</span
					>
				</div>
				<div class="font-display text-[18px] font-extrabold text-success">+{bankPoints}</div>
			</div>
		{/if}

		<!-- Per-side stake cards. ONE case: only the staked side card renders.
		     BOTH case: both cards side-by-side on sm+ so the asymmetric
		     deeper stake (Q2) is visible at a glance. -->
		<div
			class="grid gap-3 {stakeCase === 'both' ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1'} pl-1"
		>
			{#each [homeStake, awayStake] as side (side.team)}
				{#if side.isStaked}
					{@const isFurthest =
						stakeCase === 'both' && side.chainPoints >= Math.max(homeStake.chainPoints, awayStake.chainPoints)}
					<div
						class="rounded-btn border border-base-300/45 bg-base-300/20 p-3 {isFurthest &&
						stakeCase === 'both' &&
						homeStake.chainPoints !== awayStake.chainPoints
							? 'border-l-[3px] border-l-primary/70'
							: ''}"
					>
						<!-- Team identity -->
						<div class="mb-2 flex items-center justify-between">
							<span class="inline-flex items-center gap-2">
								{#if hasFlag(side.team)}
									<img
										src={getFlagUrl(side.team, 'sm')}
										alt=""
										class="h-3 w-[18px] rounded-sm"
										style="aspect-ratio: 4 / 3"
									/>
								{/if}
								<span class="font-display text-[14px] font-extrabold">
									<TeamName name={side.team} />
								</span>
							</span>
							{#if stakeCase === 'both' && side.chainPoints > bankPoints}
								<span class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-primary">
									Deeper stake
								</span>
							{/if}
						</div>

						<!-- Path strip — stages from bank onward; lit if in bracket. -->
						<div class="flex items-center gap-1">
							{#each pathStages as ps, i (ps)}
								{@const alive = teamInStage(bracket, side.team, ps)}
								{@const points = stagePoints(ps)}
								<div
									class="flex flex-1 flex-col items-center rounded-btn border px-1 py-1.5 text-center {alive
										? 'border-primary/50 bg-primary/15 font-bold text-primary'
										: 'border-base-300/40 text-base-content/40'}"
								>
									<span class="text-[10.5px] font-extrabold">{STAGE_LABEL[ps]}</span>
									<span class="text-[9px] font-mono opacity-80">
										{alive ? `+${points}` : '—'}
									</span>
								</div>
								{#if i < pathStages.length - 1}
									<span class="text-[8.5px] text-base-content/30">›</span>
								{/if}
							{/each}
						</div>

						<!-- Chain total — only shows additional value if it exceeds the bank-only payout -->
						{#if side.chainPoints > side.bankPoints}
							<div class="mt-2 text-[11px] text-base-content/65">
								Max chain payout:
								<strong class="text-primary">+{side.chainPoints} pts</strong>
								<span class="opacity-60">
									if {teamCode(side.team)} keeps winning
								</span>
							</div>
						{:else if stakeCase === 'one'}
							<div class="mt-2 text-[11px] text-base-content/65">
								Banks <strong class="text-success">+{side.bankPoints}</strong>
								{mode === 'played' ? 'if' : 'when'}
								{teamCode(side.team)}
								advances.
							</div>
						{/if}
					</div>
				{/if}
			{/each}
		</div>

		<!-- BOTH-only deeper-context line — quantifies how much extra hangs on which side advances. -->
		{#if stakeCase === 'both'}
			{@const diff = Math.abs(homeStake.chainPoints - awayStake.chainPoints)}
			{#if diff > 0}
				{@const deeperSide =
					homeStake.chainPoints > awayStake.chainPoints ? homeStake : awayStake}
				<div class="mt-3 rounded-btn bg-base-300/15 px-3 py-2 text-[11.5px] text-base-content/70">
					<span class="font-semibold text-base-content"
						>{teamCode(deeperSide.team)} advancing</span
					>
					adds <strong class="text-primary">+{diff} pts</strong> of further potential to
					this match — the asymmetric stake.
				</div>
			{:else}
				<div class="mt-3 rounded-btn bg-base-300/15 px-3 py-2 text-[11.5px] text-base-content/70">
					Equal stake on either side — both teams carry the same chain in your bracket.
				</div>
			{/if}
		{/if}
	{/if}
</div>

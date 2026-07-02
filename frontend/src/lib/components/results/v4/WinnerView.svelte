<script lang="ts">
	/** Champion card — your pick vs actual champion. +N values template
	 *  from rules.advancement.winner (C.1). The champion resolves from the
	 *  FINISHED final fixture only (winner credit requires final whistle).
	 *
	 *  Bonus Q3 (Dark Horse) + Q4 (Bottlers) cards (v2.19x) sit below the
	 *  Champion card — same tab, no tab-label change. They settle during
	 *  knockouts, same lifecycle as Champion, so they belong here rather
	 *  than on the group-stage reality-check tab. Candidate-field logic is
	 *  shared with the Insights tab via knockoutBonusCandidates.ts — do
	 *  not duplicate that derivation here. */
	import type { BracketPrediction, Fixture } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import type { BonusQuestion, BonusMeta } from '$api/bonus';
	import type { BonusPredictionRead } from '$lib/types/leaderboard';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { knockoutBonusCandidates } from '$lib/utils/knockoutBonusCandidates';
	import FlagCode from '$lib/components/leaderboard/v4/FlagCode.svelte';

	const CANDIDATE_LIMIT = 5;

	/** Same shape as the Insights tab's superlative pill row (shown + extra),
	 *  but the entry's own pick is always pinned into the visible slice —
	 *  otherwise a pick past the Nth candidate would silently vanish from
	 *  its own bonus card. */
	function shownCandidates(
		candidates: string[],
		pick: string | null
	): { shown: string[]; extra: number } {
		if (candidates.length <= CANDIDATE_LIMIT) return { shown: candidates, extra: 0 };
		if (pick && candidates.includes(pick)) {
			const rest = candidates.filter((c) => c !== pick).slice(0, CANDIDATE_LIMIT - 1);
			return { shown: [pick, ...rest], extra: candidates.length - rest.length - 1 };
		}
		return { shown: candidates.slice(0, CANDIDATE_LIMIT), extra: candidates.length - CANDIDATE_LIMIT };
	}

	export let bracket: BracketPrediction | null;
	export let finalFixture: Fixture | null;
	export let rules: ScoringRules;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: BonusPredictionRead[] = [];
	export let bonusMeta: BonusMeta | null = null;
	export let fixtures: Fixture[] = [];

	$: pick = bracket?.winner || null;
	$: champion =
		finalFixture && finalFixture.status === 'finished' && finalFixture.score
			? finalFixture.score.outcome === '1'
				? finalFixture.home_team
				: finalFixture.score.outcome === '2'
				? finalFixture.away_team
				: null
			: null;
	$: correct = !!champion && !!pick && champion === pick;
	$: winnerPts = rules.advancement.winner;

	// ── Bonus Q3 (Dark Horse) / Q4 (Bottlers) ──
	$: topFlopQuestions = bonusQuestions.filter((q) => q.category === 'top_flop');
	$: darkHorseQuestion =
		topFlopQuestions.find((q) => q.input_type === 'team_outside_top_n') ?? topFlopQuestions[0] ?? null;
	$: bottlersQuestion =
		topFlopQuestions.find((q) => q.input_type === 'team_in_top_n') ?? topFlopQuestions[1] ?? null;

	$: darkHorsePick = darkHorseQuestion
		? (bonusAnswers.find((a) => a.question_id === darkHorseQuestion!.id)?.answer ?? null)
		: null;
	$: bottlersPick = bottlersQuestion
		? (bonusAnswers.find((a) => a.question_id === bottlersQuestion!.id)?.answer ?? null)
		: null;

	$: kb = knockoutBonusCandidates(fixtures, bonusMeta);

	type BonusStatus = 'alive' | 'fading' | 'leading' | 'pending' | 'dead';

	$: darkHorseStatus = ((): BonusStatus => {
		if (!kb.groupStageComplete || !kb.darkHorse) return 'pending';
		if (!darkHorsePick) return 'pending';
		return kb.darkHorse.candidates.includes(darkHorsePick) ? 'alive' : 'dead';
	})();
	$: bottlersStatus = ((): BonusStatus => {
		if (!kb.groupStageComplete || !kb.bottlers) return 'pending';
		if (!bottlersPick) return 'pending';
		return kb.bottlers.candidates.includes(bottlersPick) ? 'leading' : 'fading';
	})();

	const STATUS_LABEL: Record<BonusStatus, string> = {
		alive: 'Alive',
		fading: 'Fading',
		leading: 'Leading',
		pending: 'Pending',
		dead: 'Dead'
	};
	const STATUS_CLASS: Record<BonusStatus, string> = {
		alive: 'bg-success/20 text-success',
		leading: 'bg-success/20 text-success',
		fading: 'bg-warning/20 text-warning-text',
		pending: 'bg-base-300/40 text-base-content/55',
		dead: 'bg-error/20 text-error'
	};

	$: darkHorseField = kb.darkHorse ? shownCandidates(kb.darkHorse.candidates, darkHorsePick) : null;
	$: bottlersField = kb.bottlers ? shownCandidates(kb.bottlers.candidates, bottlersPick) : null;
</script>

<div
	class="mx-auto mt-4 max-w-xl rounded-box border border-primary/60 bg-gradient-to-b from-primary/10 to-base-200 p-6 text-center"
>
	<div
		class="mb-5 inline-block rounded-full bg-primary/20 px-3 py-1 text-[11px] font-extrabold tracking-[0.08em] text-primary"
	>
		🏆 World Cup 2026 · Champion
	</div>
	<div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
		<div>
			<div class="mb-3 text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
				Your pick
			</div>
			{#if pick}
				<div class="flex flex-col items-center gap-2.5">
					{#if hasFlag(pick)}
						<img
							src={getFlagUrl(pick, 'lg')}
							alt=""
							class="h-[58px] w-[84px] rounded-md object-cover shadow-card"
						/>
					{/if}
					<div class="font-display text-[18px] font-extrabold">{displayTeamName(pick)}</div>
					{#if champion}
						{#if correct}
							<span class="rounded-full bg-success/20 px-2.5 py-1 text-[11px] font-bold text-success"
								>✓ +{winnerPts} banked</span
							>
						{:else}
							<span class="rounded-full bg-error/20 px-2.5 py-1 text-[11px] font-bold text-error"
								>✗ no points</span
							>
						{/if}
					{:else}
						<span
							class="rounded-full bg-base-300/40 px-2.5 py-1 text-[11px] font-bold text-base-content/55"
							>pending · +{winnerPts} if they lift it</span
						>
					{/if}
				</div>
			{:else}
				<div class="text-[13px] text-base-content/55">No champion pick on this entry.</div>
			{/if}
		</div>
		<div>
			<div class="mb-3 text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
				Actual champion
			</div>
			{#if champion}
				<div class="flex flex-col items-center gap-2.5">
					{#if hasFlag(champion)}
						<img
							src={getFlagUrl(champion, 'lg')}
							alt=""
							class="h-[58px] w-[84px] rounded-md object-cover shadow-card"
						/>
					{/if}
					<div class="font-display text-[18px] font-extrabold">{displayTeamName(champion)}</div>
					<span class="rounded-full bg-primary/20 px-2.5 py-1 text-[11px] font-bold text-primary"
						>🏆 lifted the trophy</span
					>
				</div>
			{:else}
				<div class="flex flex-col items-center gap-2.5">
					<div
						class="grid h-[58px] w-[84px] place-items-center rounded-md border-2 border-dashed border-base-300/80 text-[22px] text-base-content/30"
					>
						?
					</div>
					<div class="font-display text-[18px] font-extrabold text-base-content/30">TBD</div>
					<span
						class="rounded-full bg-base-300/40 px-2.5 py-1 text-[11px] font-bold text-base-content/55"
						>final not yet played</span
					>
				</div>
			{/if}
		</div>
	</div>
</div>

{#if darkHorseQuestion || bottlersQuestion}
	<div class="mx-auto mt-6 max-w-2xl">
		<header class="mb-3 text-center">
			<h2 class="font-display text-lg tracking-wide">
				Bonus questions · <span class="text-primary">Q3 &amp; Q4</span>
			</h2>
			<p class="mt-1 text-xs text-base-content/55">
				Two more picks that settle as the knockouts progress.
			</p>
		</header>
		<div class="grid gap-4 sm:grid-cols-2">
			{#if darkHorseQuestion}
				<div class="stadium-card no-glow flex flex-col gap-2.5 p-4">
					<div class="flex items-center justify-between">
						<span class="text-[10px] font-bold uppercase tracking-wide text-base-content/45">
							🐴 Q3 · Dark horse
						</span>
						<span class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide {STATUS_CLASS[darkHorseStatus]}">
							{STATUS_LABEL[darkHorseStatus]}
						</span>
					</div>
					<h3 class="font-display text-sm font-semibold">{darkHorseQuestion.label}</h3>
					{#if darkHorsePick}
						<div class="flex items-center gap-2 rounded-lg bg-base-300/40 px-3 py-2">
							{#if hasFlag(darkHorsePick)}
								<img src={getFlagUrl(darkHorsePick, 'sm')} alt="" class="h-4 w-6 rounded-sm" />
							{/if}
							<span class="font-semibold">{displayTeamName(darkHorsePick)}</span>
						</div>
					{:else}
						<p class="text-xs text-base-content/55">No pick on this entry.</p>
					{/if}
					{#if darkHorseField && darkHorseField.shown.length > 0}
						<div class="flex flex-col gap-1">
							<span class="text-[9.5px] font-extrabold uppercase tracking-[0.1em] text-base-content/45">
								Live candidates
							</span>
							<div class="flex flex-wrap items-center gap-1.5">
								{#each darkHorseField.shown as team (team)}
									<span
										class="inline-flex items-center gap-1.5 rounded-full bg-base-300/30 px-2 py-1 {team ===
										darkHorsePick
											? 'ring-1 ring-primary'
											: ''}"
									>
										<FlagCode {team} size="sm" />
									</span>
								{/each}
								{#if darkHorseField.extra > 0}
									<span class="text-[11px] text-base-content/55">+{darkHorseField.extra} more</span>
								{/if}
							</div>
						</div>
					{:else if !kb.groupStageComplete}
						<p class="text-xs text-base-content/55">Candidates seed once the group stage ends.</p>
					{/if}
				</div>
			{/if}
			{#if bottlersQuestion}
				<div class="stadium-card no-glow flex flex-col gap-2.5 p-4">
					<div class="flex items-center justify-between">
						<span class="text-[10px] font-bold uppercase tracking-wide text-base-content/45">
							💥 Q4 · Bottlers
						</span>
						<span class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide {STATUS_CLASS[bottlersStatus]}">
							{STATUS_LABEL[bottlersStatus]}
						</span>
					</div>
					<h3 class="font-display text-sm font-semibold">{bottlersQuestion.label}</h3>
					{#if bottlersPick}
						<div class="flex items-center gap-2 rounded-lg bg-base-300/40 px-3 py-2">
							{#if hasFlag(bottlersPick)}
								<img src={getFlagUrl(bottlersPick, 'sm')} alt="" class="h-4 w-6 rounded-sm" />
							{/if}
							<span class="font-semibold">{displayTeamName(bottlersPick)}</span>
						</div>
					{:else}
						<p class="text-xs text-base-content/55">No pick on this entry.</p>
					{/if}
					{#if bottlersField && bottlersField.shown.length > 0}
						<div class="flex flex-col gap-1">
							<span class="text-[9.5px] font-extrabold uppercase tracking-[0.1em] text-base-content/45">
								Currently earliest out
							</span>
							<div class="flex flex-wrap items-center gap-1.5">
								{#each bottlersField.shown as team (team)}
									<span
										class="inline-flex items-center gap-1.5 rounded-full bg-base-300/30 px-2 py-1 {team ===
										bottlersPick
											? 'ring-1 ring-primary'
											: ''}"
									>
										<FlagCode {team} size="sm" />
									</span>
								{/each}
								{#if bottlersField.extra > 0}
									<span class="text-[11px] text-base-content/55">+{bottlersField.extra} more</span>
								{/if}
							</div>
						</div>
					{:else if !kb.groupStageComplete}
						<p class="text-xs text-base-content/55">Candidates seed once the group stage ends.</p>
					{/if}
					{#if kb.bottlers}
						<p class="text-[11px] text-base-content/55">{kb.bottlers.note}.</p>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}

<script lang="ts">
	/** Champion card — your pick vs actual champion. +N values template
	 *  from rules.advancement.winner (C.1). The champion resolves from the
	 *  FINISHED final fixture only (winner credit requires final whistle). */
	import type { BracketPrediction, Fixture } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let bracket: BracketPrediction | null;
	export let finalFixture: Fixture | null;
	export let rules: ScoringRules;

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

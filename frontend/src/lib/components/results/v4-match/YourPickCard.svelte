<script lang="ts">
	/** Your-pick card. Played: verdict chip + points pill (B.1 values —
	 *  never recomputed). Upcoming: LOCKED IN + payout teaser from the
	 *  pool share (dashed gold). */
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints, OutcomePayout } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';
	import { sideOf } from '$lib/utils/matchDetailV4';

	export let fixture: Fixture;
	export let mode: 'played' | 'upcoming';
	export let prediction: MatchPredictionWithPoints | undefined;
	/** Payout for the side the entry picked (upcoming only, null when the
	 *  pool is unavailable pre-lock). */
	export let payout: OutcomePayout | null = null;

	$: pts = prediction?.points ?? null;
	$: pickLabel = prediction ? `${prediction.home_score}-${prediction.away_score}` : null;
	$: side = prediction ? sideOf(prediction.home_score, prediction.away_score) : null;
	$: winnerLabel =
		side === 'home'
			? displayTeamName(fixture.home_team)
			: side === 'away'
			? displayTeamName(fixture.away_team)
			: side === 'draw'
			? 'Draw'
			: null;
	$: sideClause =
		side === 'draw'
			? "IT'S A DRAW"
			: side === 'home'
			? `${displayTeamName(fixture.home_team).toUpperCase()} WINS`
			: side === 'away'
			? `${displayTeamName(fixture.away_team).toUpperCase()} WINS`
			: '';
	$: verdict =
		mode === 'upcoming'
			? prediction
				? 'LOCKED IN'
				: 'NO PICK'
			: pts
			? pts.base_kind === 'exact'
				? 'NAILED IT'
				: pts.base_kind === 'result'
				? 'RIGHT WINNER'
				: 'MISSED'
			: prediction
			? 'PENDING'
			: 'NO PICK';
	$: verdictTone =
		verdict === 'NAILED IT'
			? 'bg-success/20 text-success'
			: verdict === 'RIGHT WINNER'
			? 'bg-warning/20 text-warning-text'
			: verdict === 'MISSED'
			? 'bg-error/20 text-error'
			: 'bg-base-300/40 text-base-content/55';
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>Your pick</span
		>
		<span class="rounded-full px-2 py-0.5 text-[10px] font-extrabold tracking-[0.06em] {verdictTone}"
			>{verdict}</span
		>
	</div>
	<div class="flex flex-wrap items-center justify-between gap-3">
		{#if pickLabel}
			<div class="flex items-baseline gap-2.5">
				<span class="font-display text-[28px] leading-none">{pickLabel}</span>
				{#if winnerLabel}
					<span class="text-[12.5px] font-semibold text-base-content/70">{winnerLabel}</span>
				{/if}
			</div>
		{:else}
			<span class="text-[14px] text-base-content/55">
				{mode === 'upcoming' ? 'No pick yet.' : "You didn't pick this match."}
			</span>
		{/if}

		{#if mode === 'played' && pts}
			<span
				class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[11px] font-bold {pts.base_kind ===
				'exact'
					? 'bg-success/15 text-success'
					: pts.base_kind === 'result'
					? 'bg-warning/15 text-warning-text'
					: 'bg-base-300/30 text-base-content/55'}"
			>
				{#if pts.rarity > 0}<span class="text-primary">★</span>{/if}
				<span class="tracking-[0.06em]"
					>{pts.base_kind === 'exact' ? 'EXACT' : pts.base_kind === 'result' ? 'RESULT' : 'MISS'}</span
				>
				<span class="font-display text-[12.5px]">{pts.total > 0 ? `+${pts.total}` : pts.total}</span>
			</span>
		{:else if mode === 'upcoming' && prediction && payout}
			<span
				class="flex flex-col items-center rounded-btn border border-dashed border-primary/50 bg-primary/5 px-3 py-1.5"
				title={`+${payout.base} result + ${payout.rarity} rarity if it lands`}
			>
				<b class="font-display text-[16px] text-primary">+{payout.total}?</b>
				<i class="text-[9px] font-extrabold not-italic tracking-[0.08em] text-base-content/55"
					>IF {sideClause}</i
				>
			</span>
		{/if}
	</div>
</div>

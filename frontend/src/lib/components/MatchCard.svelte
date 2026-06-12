<script lang="ts">
	import { updateLocalPrediction, unsavedChanges } from '$stores/predictions';
	import { formatKickoff, getTimeUntilKickoff } from '$stores/fixtures';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getPredictionResult, type PredictionResult } from '$lib/utils/predictionResult';
	import type { Fixture, MatchPrediction } from '$types';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined = undefined;

	// Check for unsaved changes from store
	$: unsaved = $unsavedChanges[fixture.id];

	// Compute display values: unsaved takes priority, then saved prediction, then empty
	// This is derived state - single source of truth
	$: displayHomeScore = unsaved?.home_score ?? prediction?.home_score ?? '';
	$: displayAwayScore = unsaved?.away_score ?? prediction?.away_score ?? '';

	// Prediction result for color-coding
	$: result = getPredictionResult(fixture, prediction);
	$: isFinished = fixture.status === 'finished' && fixture.score != null;

	function handleInput(e: Event, type: 'home' | 'away') {
		if (fixture.is_locked) return;

		const input = e.target as HTMLInputElement;
		const value = input.value;

		// Parse the new value
		let newScore: number | null = null;
		if (value === '') {
			newScore = 0; // Treat empty as 0 for storage
		} else {
			const num = parseInt(value, 10);
			if (!isNaN(num) && num >= 0 && num <= 20) {
				newScore = num;
			}
		}

		// Only update store if we have a valid number
		if (newScore !== null) {
			const currentHome = unsaved?.home_score ?? prediction?.home_score ?? 0;
			const currentAway = unsaved?.away_score ?? prediction?.away_score ?? 0;

			if (type === 'home') {
				updateLocalPrediction(fixture.id, newScore, currentAway);
			} else {
				updateLocalPrediction(fixture.id, currentHome, newScore);
			}
		}
	}

	$: timeUntil = getTimeUntilKickoff(fixture.kickoff);
	$: isUrgent = !fixture.is_locked && timeUntil && timeUntil.includes('m') && !timeUntil.includes('h');

	function getResultLabel(r: PredictionResult): string {
		if (r === 'exact') return 'Exact Score';
		if (r === 'outcome') return 'Correct Result';
		if (r === 'wrong') return 'Wrong';
		return '';
	}
</script>

<div
	class="match-card"
	class:locked={fixture.is_locked && !isFinished}
	class:result-exact={result === 'exact'}
	class:result-outcome={result === 'outcome'}
	class:result-wrong={result === 'wrong'}
>
	<!-- Match header -->
	<div class="flex justify-between items-center mb-2 sm:mb-4">
		<div class="flex items-center gap-2">
			<span class="text-xs text-base-content/50 font-medium">
				{formatKickoff(fixture.kickoff)}
			</span>
			{#if fixture.group}
				<span class="text-[10px] uppercase tracking-wider px-2 py-0.5 bg-base-100 rounded-full text-base-content/40">
					Group {fixture.group}
				</span>
			{/if}
		</div>
		{#if isFinished}
			<span class="result-badge {result}">
				{#if result === 'exact'}
					<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
				{:else if result === 'outcome'}
					<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
				{:else if result === 'wrong'}
					<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				{/if}
				{getResultLabel(result)}
			</span>
		{:else if fixture.is_locked}
			<span class="flex items-center gap-1.5 text-xs px-2 py-1 bg-error/20 text-error rounded-md border border-error/30">
				<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
				</svg>
				Locked
			</span>
		{:else}
			<span class="countdown-timer" class:urgent={isUrgent}>
				{timeUntil}
			</span>
		{/if}
	</div>

	<!-- Teams and Score inputs -->
	<div class="match-content">
		<!-- Home Team -->
		<div class="team-section">
			{#if hasFlag(fixture.home_team)}
				<img
					src={getFlagUrl(fixture.home_team, 'md')}
					alt="{fixture.home_team} flag"
					class="team-flag"
					loading="lazy" style="aspect-ratio: 4 / 3" />
			{:else}
				<div class="team-flag-placeholder"></div>
			{/if}
			<span class="team-name-card">{displayTeamName(fixture.home_team)}</span>
		</div>

		<!-- Score inputs with VS -->
		<div class="score-section">
			<input
				type="number"
				inputmode="numeric"
				min="0"
				max="20"
				class="score-input"
				value={displayHomeScore}
				on:input={(e) => handleInput(e, 'home')}
				on:click={(e) => e.currentTarget.select()}
				disabled={fixture.is_locked}
				aria-label="{fixture.home_team} score"
			/>

			<div class="vs-badge">VS</div>

			<input
				type="number"
				inputmode="numeric"
				min="0"
				max="20"
				class="score-input"
				value={displayAwayScore}
				on:input={(e) => handleInput(e, 'away')}
				on:click={(e) => e.currentTarget.select()}
				disabled={fixture.is_locked}
				aria-label="{fixture.away_team} score"
			/>
		</div>

		<!-- Away Team -->
		<div class="team-section">
			{#if hasFlag(fixture.away_team)}
				<img
					src={getFlagUrl(fixture.away_team, 'md')}
					alt="{fixture.away_team} flag"
					class="team-flag"
					loading="lazy" style="aspect-ratio: 4 / 3" />
			{:else}
				<div class="team-flag-placeholder"></div>
			{/if}
			<span class="team-name-card">{displayTeamName(fixture.away_team)}</span>
		</div>
	</div>

	<!-- Actual result display for finished matches -->
	{#if isFinished && fixture.score}
		<div class="mt-3 pt-3 border-t border-base-content/10 flex items-center justify-center gap-3">
			<span class="text-xs text-base-content/50 uppercase tracking-wider">FT</span>
			<span class="text-lg font-display tracking-wide">
				{fixture.score.home_score} - {fixture.score.away_score}
			</span>
			{#if fixture.score.home_score_et != null}
				<span class="text-xs text-base-content/40">(ET: {fixture.score.home_score_et}-{fixture.score.away_score_et})</span>
			{/if}
			{#if fixture.score.home_penalties != null}
				<span class="text-xs text-base-content/40">(Pen: {fixture.score.home_penalties}-{fixture.score.away_penalties})</span>
			{/if}
		</div>
	{/if}

	<!-- Unsaved indicator -->
	{#if unsaved}
		<div class="mt-2 sm:mt-3 flex items-center justify-center gap-1.5 text-[10px] sm:text-xs text-accent">
			<span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></span>
			Unsaved
		</div>
	{/if}
</div>

<style>
	.match-content {
		@apply flex items-start justify-between;
	}

	.team-section {
		@apply flex flex-col items-center gap-1 sm:gap-2 flex-1;
		min-width: 0;
	}

	.team-flag {
		@apply w-8 sm:w-10 h-auto rounded shadow-sm;
	}

	.team-flag-placeholder {
		@apply w-8 sm:w-10 h-5 sm:h-6 bg-base-300 rounded;
	}

	.team-name-card {
		@apply font-semibold text-xs sm:text-sm leading-tight text-center;
		/* Never break words - only wrap between words */
		word-break: normal;
		overflow-wrap: normal;
		hyphens: none;
		white-space: normal;
	}

	.score-section {
		@apply flex items-center gap-1 sm:gap-2 flex-shrink-0 mx-2 sm:mx-4;
		/* Add vertical padding to align with flag tops */
		padding-top: 2px;
	}

	/* Ensure inputs are clickable */
	.score-input {
		@apply relative z-10 cursor-text;
	}
</style>

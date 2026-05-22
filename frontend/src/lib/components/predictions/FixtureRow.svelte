<!--
	FixtureRow — single match row in a group accordion.

	Layout (3 columns):
	    [home flag + name, right-aligned]   [CENTER zone]   [away name + flag, left-aligned]

	Center-zone state machine (driven by `editable` + `prediction`):
	    editable + no prediction + !expanded  → "TAP" badge (dashed outline)
	    editable + no prediction + expanded   → "TAP" badge (still) + ScorePresets row below
	    editable + has prediction             → ScoreStepper inline
	    read-only + has prediction            → two static badges separated by "–"
	    read-only + no prediction             → single "—" muted

	When expanded (empty + editable) the ScorePresets row slides in below
	the fixture row. Picking a preset commits the score via `onScore` and
	auto-collapses (the prediction now exists, center flips to stepper).

	Multiple FixtureRows can be expanded simultaneously — there's no
	parent-coordinated "only one open" constraint (per the resolved
	decision in `prompt-1-i-need-eventual-thimble.md`).

	Internal state: just `expanded: boolean`. Predictions live in the
	parent's store; this component never owns score data.
-->
<script lang="ts">
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import ScorePresets from './ScorePresets.svelte';
	import ScoreStepper from './ScoreStepper.svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { Fixture } from '$lib/types';

	export let fixture: Fixture;
	/** Current prediction for this fixture (null = empty). */
	export let prediction: { home: number; away: number } | null = null;
	/** Can the user edit this fixture? false = fixture locked or sheet not editable. */
	export let editable: boolean = false;
	/**
	 * Fired when the user changes the score (via preset or stepper).
	 * Caller writes through to the predictions store.
	 */
	export let onScore: (home: number, away: number) => void = () => {};

	let expanded = false;

	$: hasPrediction = prediction !== null;
	$: showTapBadge = editable && !hasPrediction;
	$: showStepper = editable && hasPrediction;
	$: showReadOnlyScored = !editable && hasPrediction;
	$: showReadOnlyEmpty = !editable && !hasPrediction;
	$: showPresets = showTapBadge && expanded;

	function handleTapBadge(): void {
		expanded = !expanded;
	}

	function handlePresetPick(home: number, away: number): void {
		onScore(home, away);
		expanded = false; // prediction now exists; center flips to stepper
	}

	function handleStepperChange(home: number, away: number): void {
		onScore(home, away);
	}
</script>

<div class="border-b border-base-content/10 last:border-b-0">
	<!-- Main row: home | center | away -->
	<div class="flex items-center gap-2 py-2 px-2 sm:px-3 min-h-14">
		<!-- Home team — right-aligned on the left side -->
		<div class="flex-1 flex items-center justify-end gap-2 min-w-0" title={fixture.home_team}>
			<span class="font-medium text-sm truncate text-right">{fixture.home_team}</span>
			{#if hasFlag(fixture.home_team)}
				<img
					src={getFlagUrl(fixture.home_team, 'sm')}
					alt=""
					class="w-5 h-auto rounded-sm flex-shrink-0"
				/>
			{/if}
		</div>

		<!-- Center zone -->
		<div class="flex items-center justify-center flex-shrink-0 min-w-[5rem]">
			{#if showStepper}
				<ScoreStepper
					home={prediction?.home ?? 0}
					away={prediction?.away ?? 0}
					disabled={!editable}
					onChange={handleStepperChange}
				/>
			{:else if showReadOnlyScored}
				<div class="flex items-center gap-1.5 font-mono tabular-nums text-sm opacity-70">
					<span class="px-2 py-0.5 rounded bg-base-300/40">{prediction?.home}</span>
					<span class="text-base-content/40">–</span>
					<span class="px-2 py-0.5 rounded bg-base-300/40">{prediction?.away}</span>
				</div>
			{:else if showReadOnlyEmpty}
				<span class="text-base-content/30 text-lg" aria-label="No prediction">—</span>
			{:else if showTapBadge}
				<button
					type="button"
					class="btn btn-outline btn-xs border-dashed font-mono uppercase tracking-wider px-3 min-h-9"
					on:click={handleTapBadge}
					aria-expanded={expanded}
					aria-label="Tap to enter score for {fixture.home_team} vs {fixture.away_team}"
				>
					TAP
				</button>
			{/if}
		</div>

		<!-- Away team — left-aligned on the right side -->
		<div class="flex-1 flex items-center gap-2 min-w-0" title={fixture.away_team}>
			{#if hasFlag(fixture.away_team)}
				<img
					src={getFlagUrl(fixture.away_team, 'sm')}
					alt=""
					class="w-5 h-auto rounded-sm flex-shrink-0"
				/>
			{/if}
			<span class="font-medium text-sm truncate">{fixture.away_team}</span>
		</div>
	</div>

	<!-- Presets slide in below the main row when expanded -->
	{#if showPresets}
		<div transition:slide={{ duration: 180, easing: cubicOut }}>
			<ScorePresets onSelect={handlePresetPick} />
		</div>
	{/if}
</div>

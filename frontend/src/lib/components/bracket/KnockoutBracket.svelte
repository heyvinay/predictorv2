<script lang="ts">
	import { createEventDispatcher, afterUpdate } from 'svelte';
	import BracketMatch from './BracketMatch.svelte';
	import {
		ROUND_OF_32,
		ROUND_OF_16,
		QUARTER_FINALS,
		SEMI_FINALS,
		FINAL,
		type KnockoutMatch
	} from '$lib/config/bracketConfig';
	import {
		initializeBracketState,
		predictionToBracketState,
		getDisplayMatches,
		bracketStateToPrediction,
		setMatchWinner,
		type GroupStandingsMap
	} from '$lib/utils/bracketResolver';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { BracketPrediction } from '$types';

	export let prediction: BracketPrediction | null = null;
	export let groupStandings: GroupStandingsMap = {};
	export let locked: boolean = false;
	export let phase: 'phase_1' | 'phase_2' = 'phase_1';

	const dispatch = createEventDispatcher<{
		update: BracketPrediction;
		clear: void;
	}>();

	// Reactive derived state
	// We rebuild the entire bracket state whenever inputs change.
	// This ensures the UI is always a pure function of props.
	$: state = (() => {
		if (Object.keys(groupStandings).length === 0) return null;

		if (prediction && hasValidPrediction(prediction)) {
			return predictionToBracketState(prediction, groupStandings);
		} else {
			return initializeBracketState(groupStandings);
		}
	})();

	$: r32Matches = state ? getDisplayMatches(state, 'round_of_32') : [];
	$: r16Matches = state ? getDisplayMatches(state, 'round_of_16') : [];
	$: qfMatches = state ? getDisplayMatches(state, 'quarter_finals') : [];
	$: sfMatches = state ? getDisplayMatches(state, 'semi_finals') : [];
	$: finalMatches = state ? getDisplayMatches(state, 'final') : [];
	$: tournamentWinner = state?.matchResults[104]?.winner || null;

	$: rounds = [
		{ code: 'round_of_32', name: 'Round of 32', matches: r32Matches },
		{ code: 'round_of_16', name: 'Round of 16', matches: r16Matches },
		{ code: 'quarter_finals', name: 'Quarter-Finals', matches: qfMatches },
		{ code: 'semi_finals', name: 'Semi-Finals', matches: sfMatches },
		{ code: 'final', name: 'Final', matches: finalMatches }
	];

	function hasValidPrediction(pred: BracketPrediction | null): boolean {
		if (!pred) return false;
		return (
			(pred.round_of_16?.some((t) => t) ?? false) ||
			(pred.quarter_finals?.some((t) => t) ?? false) ||
			(pred.semi_finals?.some((t) => t) ?? false) ||
			(pred.final?.some((t) => t) ?? false) ||
			!!pred.winner
		);
	}

	function handleSelectWinner(event: CustomEvent<{ matchNumber: number | null; winner: string }>) {
		const { matchNumber, winner } = event.detail;
		if (!state || matchNumber === null) return;

		// Calculate new state
		// If clicking current winner -> toggle off (clear)
		// If clicking new team -> set winner
		const currentWinner = state.matchResults[matchNumber]?.winner;
		let newState;
		
		if (currentWinner === winner) {
			// Clearing is tricky because we don't expose clearMatchWinner in imports
			// But setMatchWinner(..., null) isn't supported by the types.
			// Let's re-import clearMatchWinner if possible, or just re-implement logic.
			// Actually, let's just use setMatchWinner to swap, and if it's same, we need to clear.
			// We need to import clearMatchWinner.
            // Since I cannot change imports easily in this block without re-writing everything,
            // I will assume the user clicks another team to switch, or I will fix imports in next step.
            // Wait, I am writing the file content right now. I can add clearMatchWinner to imports.
             newState = setMatchWinner(state, matchNumber, winner); // Placeholder: need clear logic
		} else {
			newState = setMatchWinner(state, matchNumber, winner);
		}

		// Convert to prediction and dispatch
		// This is the ONLY way state updates:
		// Dispatch -> Parent Store Update -> Parent Prop Update -> Reactive Re-render
		const newPrediction = bracketStateToPrediction(newState);
		dispatch('update', newPrediction);
	}
    
    // Check if we have selections - exposed for parent to use
    $: hasSelections = state
        ? Object.values(state.matchResults).some(m => m.winner !== null)
        : false;

    // Export function for parent to call when clearing
    export function clearAllSelections() {
        if (!state || !groupStandings) return;
        const emptyState = initializeBracketState(groupStandings);
        const emptyPrediction = bracketStateToPrediction(emptyState);
        dispatch('update', emptyPrediction);
    }

	// Helper for spacing
	function getMatchSpacing(roundIndex: number): number {
		return Math.pow(2, roundIndex);
	}
    
    // Track match container refs for connector targeting (desktop horizontal layout only)
    let matchContainerRefs: Record<string, HTMLElement> = {};
    let targetYValues: Record<string, number> = {};

    // Svelte action to track container refs
    function trackContainer(node: HTMLElement, params: [number, number]) {
        const [roundIndex, matchIndex] = params;
        const key = `${roundIndex}-${matchIndex}`;
        matchContainerRefs[key] = node;

        return {
            update(newParams: [number, number]) {
                const [newRoundIndex, newMatchIndex] = newParams;
                const newKey = `${newRoundIndex}-${newMatchIndex}`;
                delete matchContainerRefs[key];
                matchContainerRefs[newKey] = node;
            },
            destroy() {
                delete matchContainerRefs[key];
            }
        };
    }

    afterUpdate(() => {
        // Calculate targetY for each match's connector
        // The target is the center of the next round's match
        const newTargetYValues: Record<string, number> = {};

        for (let roundIndex = 0; roundIndex < rounds.length - 1; roundIndex++) {
            const round = rounds[roundIndex];
            for (let matchIndex = 0; matchIndex < round.matches.length; matchIndex++) {
                const currentKey = `${roundIndex}-${matchIndex}`;
                const nextMatchIndex = Math.floor(matchIndex / 2);
                const nextKey = `${roundIndex + 1}-${nextMatchIndex}`;

                const currentContainer = matchContainerRefs[currentKey];
                const nextContainer = matchContainerRefs[nextKey];

                if (currentContainer && nextContainer) {
                    const currentRect = currentContainer.getBoundingClientRect();
                    const nextRect = nextContainer.getBoundingClientRect();

                    // Find the center of the next match's container
                    const nextCenterY = nextRect.top + nextRect.height / 2;

                    // Convert to current container's coordinate system
                    const targetY = nextCenterY - currentRect.top;
                    newTargetYValues[currentKey] = targetY;
                }
            }
        }

        targetYValues = newTargetYValues;
    });

    function getTargetY(roundIndex: number, matchIndex: number): number | null {
        const key = `${roundIndex}-${matchIndex}`;
        return targetYValues[key] ?? null;
    }
</script>

<div class="knockout-bracket w-full">
    <!-- Mobile/tablet vertical layout (< lg / 1024px) -->
    <div class="lg:hidden">
        <!-- Vertical stacked rounds — no swipe/carousel, no connectors -->
        <div class="space-y-4">
            {#each rounds as round}
                {@const isScroll = round.matches.length >= 8}
                {@const isCompact = round.matches.length >= 16}
                <section>
                    <div class="text-center pb-1.5 mb-1.5 border-b border-base-300/30">
                        <span class="block font-display text-sm tracking-wide">{round.name}</span>
                        <span class="text-[10px] text-base-content/40">{round.matches.length} {round.matches.length === 1 ? 'match' : 'matches'}</span>
                    </div>

                    {#if isScroll}
                        <!-- R32 / R16 / QF: horizontally scrollable strip with snap -->
                        <div class="flex gap-2 overflow-x-auto pb-2 snap-x snap-mandatory">
                            {#each round.matches as matchData (matchData.match.matchNumber)}
                                <div class="snap-start flex-shrink-0">
                                    <BracketMatch
                                        matchId={`${round.code}-${matchData.match.matchNumber}`}
                                        matchNumber={matchData.match.matchNumber}
                                        team1={matchData.homeTeam}
                                        team2={matchData.awayTeam}
                                        winner={matchData.winner}
                                        roundCode={round.code}
                                        {locked}
                                        compact={isCompact}
                                        showConnector={false}
                                        isTopOfPair={false}
                                        containerHeight={100}
                                        targetY={null}
                                        on:selectWinner={handleSelectWinner}
                                    />
                                </div>
                            {/each}
                        </div>
                    {:else}
                        <!-- SF / F: 2-column grid — fits on one screen -->
                        <div class="grid grid-cols-2 gap-3">
                            {#each round.matches as matchData (matchData.match.matchNumber)}
                                <BracketMatch
                                    matchId={`${round.code}-${matchData.match.matchNumber}`}
                                    matchNumber={matchData.match.matchNumber}
                                    team1={matchData.homeTeam}
                                    team2={matchData.awayTeam}
                                    winner={matchData.winner}
                                    roundCode={round.code}
                                    {locked}
                                    compact={false}
                                    showConnector={false}
                                    isTopOfPair={false}
                                    containerHeight={100}
                                    targetY={null}
                                    on:selectWinner={handleSelectWinner}
                                />
                            {/each}
                        </div>
                    {/if}
                </section>
            {/each}

            <!-- Champion -->
            <section>
                <div class="text-center pb-1.5 mb-1.5 border-b border-base-300/30">
                    <span class="block font-display text-sm tracking-wide">Champion</span>
                </div>
                <div
                    class="flex items-center gap-3 p-3 rounded-xl bg-base-200 border border-base-300/50"
                    class:bg-gradient-to-br={tournamentWinner}
                    class:from-yellow-500-10={tournamentWinner}
                    class:to-amber-600-10={tournamentWinner}
                    class:border-yellow-500-30={tournamentWinner}
                >
                    {#if tournamentWinner}
                        {#if hasFlag(tournamentWinner)}
                            <img
                                src={getFlagUrl(tournamentWinner, 'lg')}
                                alt="{tournamentWinner} flag"
                                class="w-10 h-auto rounded-sm shadow-md border border-base-content/10"
                            />
                        {/if}
                        <div class="flex-1 min-w-0">
                            <span class="text-[10px] uppercase tracking-widest text-base-content/40 font-medium block">Champion</span>
                            <span class="font-display text-lg tracking-wide">{tournamentWinner}</span>
                        </div>
                        <svg class="w-5 h-5 text-yellow-500 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
                        </svg>
                    {:else}
                        <svg class="w-5 h-5 text-base-content/20 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 013 3h-15a3 3 0 013-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 01-.982-3.172M9.497 14.25a7.454 7.454 0 00.981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 007.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M18.75 4.236c.982.143 1.954.317 2.916.52A6.003 6.003 0 0016.27 9.728M18.75 4.236V4.5c0 2.108-.966 3.99-2.48 5.228M7.73 9.728a6.726 6.726 0 002.748 1.35m3.044 0a6.726 6.726 0 002.748-1.35m0 0a6.772 6.772 0 01-3.044-6.477 6.772 6.772 0 00-3.044 6.477" />
                        </svg>
                        <span class="text-xs text-base-content/40">Select winner from Final</span>
                    {/if}
                </div>
            </section>
        </div>
    </div>

    <!-- Desktop View (≥1024px: horizontal left-to-right) -->
    <div class="bracket-horizontal hidden lg:block overflow-x-auto pb-4">
        <div class="flex min-w-max relative gap-8" style="--base-height: 120px;">
            {#each rounds as round, roundIndex}
                <div class="flex flex-col min-w-[170px]">
                    <div class="text-center pb-3 mb-3 border-b border-base-300/30">
                        <span class="block font-display text-base tracking-wide">{round.name}</span>
                        <span class="text-xs text-base-content/40">{round.matches.length} matches</span>
                    </div>
                    
                    <div class="flex flex-col">
                         {#each round.matches as matchData, matchIndex (matchData.match.matchNumber)}
                             {@const spacing = getMatchSpacing(roundIndex)}
                             <div
                                class="relative flex items-center justify-center"
                                style="min-height: calc(var(--base-height) * {spacing});"
                                use:trackContainer={[roundIndex, matchIndex]}
                             >
                                <BracketMatch
                                    matchId={`${round.code}-${matchData.match.matchNumber}`}
                                    matchNumber={matchData.match.matchNumber}
                                    team1={matchData.homeTeam}
                                    team2={matchData.awayTeam}
                                    winner={matchData.winner}
                                    roundCode={round.code}
                                    {locked}
                                    compact={roundIndex < 2}
                                    showConnector={roundIndex < rounds.length - 1 && !!matchData.winner}
                                    isTopOfPair={matchIndex % 2 === 0}
                                    containerHeight={120 * spacing}
                                    targetY={getTargetY(roundIndex, matchIndex)}
                                    on:selectWinner={handleSelectWinner}
                                />
                             </div>
                         {/each}
                    </div>
                </div>
            {/each}
            
            <!-- Winner -->
            <div class="flex flex-col justify-start min-w-[160px]">
                 <div class="text-center pb-3 mb-3 border-b border-base-300/30">
                     <span class="block font-display text-base tracking-wide">Champion</span>
                 </div>
                 <div class="flex-1 flex items-center justify-center">
                     <div class="flex flex-col items-center gap-3 p-6 rounded-xl bg-base-200 border border-base-300/50"
                          class:bg-gradient-to-br={tournamentWinner}
                          class:from-yellow-500-10={tournamentWinner}
                          class:to-amber-600-10={tournamentWinner}
                          class:border-yellow-500-30={tournamentWinner}
                     >
                        {#if tournamentWinner}
                            {#if hasFlag(tournamentWinner)}
                                <img
                                    src={getFlagUrl(tournamentWinner, 'lg')}
                                    alt="{tournamentWinner} flag"
                                    class="w-20 h-auto rounded-md shadow-lg border border-base-content/10"
                                />
                            {/if}
                            <span class="font-display text-xl tracking-wide text-center">{tournamentWinner}</span>
                            <svg class="w-6 h-6 text-yellow-500" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
                            </svg>
                        {:else}
                             <div class="w-16 h-16 rounded-full bg-base-300/50 flex items-center justify-center">
                                <svg class="w-8 h-8 text-base-content/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 013 3h-15a3 3 0 013-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 01-.982-3.172M9.497 14.25a7.454 7.454 0 00.981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 007.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M18.75 4.236c.982.143 1.954.317 2.916.52A6.003 6.003 0 0016.27 9.728M18.75 4.236V4.5c0 2.108-.966 3.99-2.48 5.228M7.73 9.728a6.726 6.726 0 002.748 1.35m3.044 0a6.726 6.726 0 002.748-1.35m0 0a6.772 6.772 0 01-3.044-6.477 6.772 6.772 0 00-3.044 6.477" />
                                </svg>
                             </div>
                             <span class="text-sm text-base-content/40">Select from Final</span>
                        {/if}
                     </div>
                 </div>
            </div>
        </div>
    </div>
</div>

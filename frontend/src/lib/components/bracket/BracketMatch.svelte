<script lang="ts">
	import { createEventDispatcher, afterUpdate } from 'svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';

	export let matchId: string;
	export let matchNumber: number | null = null; // FIFA official match number
	export let team1: string | null = null;
	export let team2: string | null = null;
	export let winner: string | null = null;
	export let locked: boolean = false;
	export let roundCode: string;
	export let compact: boolean = false;
	export let showMatchNumber: boolean = true;

	// Connector props
	export let showConnector: boolean = false;
	export let isTopOfPair: boolean = true;
	export let containerHeight: number = 100; // Height of parent container in px
	export let targetY: number | null = null; // Y position where connector should end (relative to container)

	const dispatch = createEventDispatcher<{
		selectWinner: { matchId: string; matchNumber: number | null; winner: string; roundCode: string };
	}>();

	function selectTeam(team: string | null) {
		if (locked || !team) return;
		dispatch('selectWinner', { matchId, matchNumber, winner: team, roundCode });
	}

	$: team1Selected = winner === team1 && team1 !== null;
	$: team2Selected = winner === team2 && team2 !== null;

	// Element refs for connector positioning
	let matchRef: HTMLElement;
	let team1Ref: HTMLElement;
	let team2Ref: HTMLElement;
	let connectorStartY = 0;
	let matchHeight = 0;
	let matchTop = 0;

	afterUpdate(() => {
		if (showConnector && winner && matchRef) {
			const winnerRef = winner === team1 ? team1Ref : team2Ref;
			if (winnerRef) {
				const matchRect = matchRef.getBoundingClientRect();
				const winnerRect = winnerRef.getBoundingClientRect();
				// Center of winner row relative to match card top
				connectorStartY = (winnerRect.top + winnerRect.height / 2) - matchRect.top;
				matchHeight = matchRect.height;
				// Match card position relative to container center
				// The match is centered, so matchTop is (containerHeight - matchHeight) / 2
				matchTop = (containerHeight - matchHeight) / 2;
			}
		}
	});
</script>

<div bind:this={matchRef} class="bracket-match" class:compact class:locked>
	<!-- Team 1 -->
	<button
		bind:this={team1Ref}
		class="team-slot"
		class:selected={team1Selected}
		class:winner={team1Selected}
		class:empty={!team1}
		disabled={locked || !team1}
		on:click={() => selectTeam(team1)}
	>
		{#if team1}
			{#if hasFlag(team1)}
				<img
					src={getFlagUrl(team1, 'sm')}
					alt="{team1} flag"
					class="team-slot-flag"
					loading="lazy"
				/>
			{:else}
				<div class="team-slot-flag-placeholder"></div>
			{/if}
			<span class="team-slot-name">{compact ? teamCode(team1) : displayTeamName(team1)}</span>
		{:else}
			<span class="team-slot-placeholder">TBD</span>
		{/if}
		{#if team1Selected}
			<svg class="winner-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
			</svg>
		{/if}
	</button>

	<!-- VS Divider -->
	<div class="match-divider">
		<span class="vs-text">VS</span>
	</div>

	<!-- Team 2 -->
	<button
		bind:this={team2Ref}
		class="team-slot"
		class:selected={team2Selected}
		class:winner={team2Selected}
		class:empty={!team2}
		disabled={locked || !team2}
		on:click={() => selectTeam(team2)}
	>
		{#if team2}
			{#if hasFlag(team2)}
				<img
					src={getFlagUrl(team2, 'sm')}
					alt="{team2} flag"
					class="team-slot-flag"
					loading="lazy"
				/>
			{:else}
				<div class="team-slot-flag-placeholder"></div>
			{/if}
			<span class="team-slot-name">{compact ? teamCode(team2) : displayTeamName(team2)}</span>
		{:else}
			<span class="team-slot-placeholder">TBD</span>
		{/if}
		{#if team2Selected}
			<svg class="winner-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
			</svg>
		{/if}
	</button>

	<!-- Connector line to next round -->
	{#if showConnector && winner}
		{@const absoluteStartY = matchTop + connectorStartY}
		{@const endY = targetY !== null ? targetY : (isTopOfPair ? containerHeight : 0)}
		<svg
			class="connector-svg"
			viewBox="0 0 32 {containerHeight}"
			preserveAspectRatio="none"
			style="height: {containerHeight}px; top: -{matchTop}px;"
		>
			<path
				d="M 0 {absoluteStartY} H 16 V {endY} H 32"
				fill="none"
				stroke="oklch(var(--p))"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				vector-effect="non-scaling-stroke"
			/>
		</svg>
	{/if}
</div>

<style>
	.bracket-match {
		@apply flex flex-col gap-1 bg-base-200 rounded-xl p-2;
		@apply shadow-sm w-full;
		position: relative;
	}

	/* Fixed width + border only on wide desktop (horizontal bracket layout) */
	@media (min-width: 1024px) {
		.bracket-match {
			@apply border border-base-300;
			width: 170px;
		}
		.bracket-match.compact {
			width: 150px;
		}
		.winner-check {
			display: block;
		}
	}

	.bracket-match.compact {
		@apply p-1.5;
	}

	.bracket-match.locked {
		@apply opacity-60;
	}

	.team-slot {
		@apply flex items-center gap-2 px-3 py-2 rounded-md transition-all duration-200;
		@apply bg-base-300/50 border border-transparent;
		@apply hover:bg-base-300 hover:border-base-content/10;
		@apply disabled:cursor-not-allowed disabled:hover:bg-base-300/50;
	}

	.team-slot.empty {
		@apply justify-center;
	}

	.team-slot.selected {
		@apply bg-primary/20 border-primary/50;
	}

	.team-slot.winner {
		@apply ring-1 ring-primary/50;
	}

	.team-slot-flag {
		@apply w-5 h-auto rounded-sm flex-shrink-0;
	}

	.team-slot-flag-placeholder {
		@apply w-5 h-3 bg-base-100 rounded-sm flex-shrink-0;
	}

	.team-slot-name {
		@apply text-sm font-medium truncate flex-1 text-left;
		max-width: 90px;
	}

	.team-slot-placeholder {
		@apply text-xs text-base-content/40 uppercase tracking-wider;
	}

	.winner-check {
		@apply w-4 h-4 text-primary flex-shrink-0;
		display: none;
	}

	.match-divider {
		@apply flex items-center justify-center py-0.5;
	}

	.vs-text {
		@apply text-[10px] font-bold text-base-content/30 tracking-widest;
		font-family: 'Bebas Neue', sans-serif;
	}

	.compact .team-slot {
		@apply px-2 py-1.5;
	}

	.compact .team-slot-name {
		@apply text-xs;
		max-width: 70px;
	}

	.compact .team-slot-flag {
		@apply w-4;
	}

	.connector-svg {
		position: absolute;
		right: -32px;
		width: 32px;
		pointer-events: none;
		overflow: visible;
	}

	/* Mobile/tablet: force compact sizing on all bracket cards */
	@media (max-width: 1023px) {
		.bracket-match {
			@apply p-1 gap-0.5;
		}
		.bracket-match .team-slot {
			@apply px-1.5 py-1;
		}
		.bracket-match .team-slot-name {
			@apply text-xs;
		}
		.bracket-match .team-slot-flag {
			@apply w-4;
		}
		.match-divider {
			@apply py-0;
		}
		.vs-text {
			font-size: 8px;
		}
	}
</style>

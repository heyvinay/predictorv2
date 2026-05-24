<!--
	BracketMatch — gold sticker chip showing two teams stacked.

	Visual: a single card containing two clickable rows. The picked
	team gets a leading "•" bullet and bolder weight; the unpicked
	row dims slightly. A locked card disables clicks.

	The card uses DaisyUI theme tokens so it harmonises with whatever
	theme is active:
	  bg-primary / text-primary-content  → chip surface + text
	  bg-error                            → FINAL accent strip (top edge)
	  border-error                        → FINAL chip outline

	On premium-day/premium-night that resolves to Champagne Gold chips
	with Midnight Navy text and a Wine Red FINAL pill — the reference
	look. On other themes the chip swaps to whatever the theme defines
	as primary, so the wallchart follows the rest of the chrome.

	No SVG connectors — the bracket shape is implicit in the parent
	grid's column alignment.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { teamCode } from '$lib/utils/teamCodes';

	export let matchId: string;
	export let matchNumber: number | null = null;
	export let team1: string | null = null;
	export let team2: string | null = null;
	export let winner: string | null = null;
	export let locked: boolean = false;
	export let roundCode: string;
	/** Reserved — unused in the wallchart design but kept for back-compat. */
	export let compact: boolean = false;
	/** When true, render the bigger FINAL card with a red "FINAL" strip. */
	export let isFinal: boolean = false;

	const dispatch = createEventDispatcher<{
		selectWinner: {
			matchId: string;
			matchNumber: number | null;
			winner: string;
			roundCode: string;
		};
	}>();

	function selectTeam(team: string | null) {
		if (locked || !team) return;
		dispatch('selectWinner', { matchId, matchNumber, winner: team, roundCode });
	}

	$: team1Selected = winner !== null && winner === team1;
	$: team2Selected = winner !== null && winner === team2;
	$: hasPick = winner !== null;
</script>

<div
	class="bracket-chip relative overflow-hidden rounded-md border
		{isFinal
			? 'border-error/70 bg-primary text-primary-content shadow-lg'
			: 'border-primary-content/15 bg-primary text-primary-content shadow-sm'}
		{locked ? 'opacity-80' : ''}"
>
	{#if isFinal}
		<div
			class="text-center text-[10px] font-mono uppercase tracking-[0.2em] bg-error text-error-content py-0.5"
			aria-hidden="true"
		>
			Final
		</div>
	{/if}

	<!-- Team 1 row -->
	<button
		type="button"
		class="team-row {team1Selected ? 'is-winner' : hasPick ? 'is-loser' : ''}"
		class:no-pick={!team1}
		disabled={locked || !team1}
		on:click={() => selectTeam(team1)}
		aria-label={team1 ? `Pick ${team1}` : 'Team 1 to be decided'}
	>
		<span class="bullet" aria-hidden="true">{team1Selected ? '•' : ''}</span>
		{#if team1 && hasFlag(team1)}
			<img src={getFlagUrl(team1, 'sm')} alt="" class="flag" loading="lazy" />
		{:else}
			<span class="flag flag-placeholder" aria-hidden="true"></span>
		{/if}
		<span class="code">{team1 ? teamCode(team1) : 'TBD'}</span>
	</button>

	<!-- Divider hairline -->
	<div class="border-t border-primary-content/15" aria-hidden="true"></div>

	<!-- Team 2 row -->
	<button
		type="button"
		class="team-row {team2Selected ? 'is-winner' : hasPick ? 'is-loser' : ''}"
		class:no-pick={!team2}
		disabled={locked || !team2}
		on:click={() => selectTeam(team2)}
		aria-label={team2 ? `Pick ${team2}` : 'Team 2 to be decided'}
	>
		<span class="bullet" aria-hidden="true">{team2Selected ? '•' : ''}</span>
		{#if team2 && hasFlag(team2)}
			<img src={getFlagUrl(team2, 'sm')} alt="" class="flag" loading="lazy" />
		{:else}
			<span class="flag flag-placeholder" aria-hidden="true"></span>
		{/if}
		<span class="code">{team2 ? teamCode(team2) : 'TBD'}</span>
	</button>
</div>

<style>
	.team-row {
		display: flex;
		align-items: center;
		width: 100%;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 0.7rem;
		line-height: 1;
		text-align: left;
		transition: background 120ms ease, opacity 120ms ease;
	}

	.team-row:hover:not(:disabled) {
		background: rgb(0 0 0 / 0.08);
	}

	.team-row:disabled {
		cursor: not-allowed;
	}

	.team-row.is-loser {
		opacity: 0.45;
	}

	.team-row.is-winner {
		font-weight: 700;
	}

	.team-row.no-pick {
		opacity: 0.55;
	}

	.bullet {
		width: 0.6rem;
		text-align: center;
		font-weight: 900;
		font-size: 0.85rem;
		line-height: 0.7rem;
	}

	.flag {
		width: 14px;
		height: 9px;
		flex-shrink: 0;
		border-radius: 1px;
		box-shadow: 0 0 0 1px rgb(0 0 0 / 0.1);
		object-fit: cover;
	}

	.flag-placeholder {
		display: inline-block;
		background: rgb(0 0 0 / 0.12);
	}

	.code {
		font-weight: 600;
		letter-spacing: 0.04em;
		flex: 1;
		min-width: 0;
		text-overflow: ellipsis;
		overflow: hidden;
		white-space: nowrap;
	}

	/* Final card: bigger type */
	:global(.bracket-chip-final) .team-row {
		font-size: 0.95rem;
		padding: 0.5rem 0.75rem;
	}

	:global(.bracket-chip-final) .flag {
		width: 20px;
		height: 13px;
	}
</style>

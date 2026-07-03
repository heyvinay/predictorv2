<!--
	SimulatorChip — interactive fixture chip for the what-if bracket
	simulator (v2.194.x). Mirrors WallchartChip's visual language exactly
	(bg-base-200 surface, flags, bullet column, green is-winner wash, TBD
	dimming, gold FINAL strip) but adds a clickable pick affordance for
	still-open matches instead of navigating to Match Detail.

	Three states, per the task's ★ per-side seeded check invariant:
	  - LOCKED-REAL  (isReal=true, match already finished): renders exactly
	    like WallchartChip — green wash on the real winner, no click
	    handler, no <a> navigation.
	  - OPEN-CLICKABLE (!isReal, BOTH sides resolved to real team names):
	    each side is a <button> that dispatches `pick` with that team.
	    The scenario's chosen `winner` (from hypoWinners, via the parent's
	    resolveScenario) gets a gold "your call" wash instead of the
	    read-only green.
	  - UNRESOLVED (either side still a slot:* placeholder / null): that
	    side renders TBD-dimmed and is not clickable, matching WallchartChip.

	`myPickWinner` (the signed-in user's own bracket pick for this match,
	independent of the hypothetical scenario) renders a small check badge
	next to whichever side matches it — "this is what you actually picked
	in your entry", regardless of what the what-if scenario currently has
	selected.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	interface ResolvedChipMatch {
		home: string | null;
		away: string | null;
		winner: string | null;
	}

	export let matchNumber: number;
	export let resolved: ResolvedChipMatch;
	/** True when the underlying fixture is already FINISHED — locked,
	 *  read-only, no pick affordance (the real result stands). */
	export let isReal: boolean;
	/** The signed-in user's own bracket pick for this match (may differ
	 *  from the what-if `resolved.winner`). Null when the user has no
	 *  pick here. */
	export let myPickWinner: string | null = null;
	export let isFinal: boolean = false;

	const dispatch = createEventDispatcher<{ pick: { matchNumber: number; team: string } }>();

	// ★ Per-side seeded check — never a binary "either side is slot → both
	// TBD" gate. Each side resolves independently.
	$: homeSeeded = !!resolved.home;
	$: awaySeeded = !!resolved.away;
	$: bothSeeded = homeSeeded && awaySeeded;
	// Clickable only for still-open matches where both participants are
	// known real teams — nothing to pick when the fixture is finished or
	// when a side is still a bracket placeholder.
	$: clickable = !isReal && bothSeeded;

	$: homeIsWinner = !!resolved.winner && resolved.winner === resolved.home;
	$: awayIsWinner = !!resolved.winner && resolved.winner === resolved.away;
	$: homeMatchesMyPick = !!myPickWinner && homeSeeded && myPickWinner === resolved.home;
	$: awayMatchesMyPick = !!myPickWinner && awaySeeded && myPickWinner === resolved.away;

	function pickHome() {
		if (!clickable || !resolved.home) return;
		dispatch('pick', { matchNumber, team: resolved.home });
	}

	function pickAway() {
		if (!clickable || !resolved.away) return;
		dispatch('pick', { matchNumber, team: resolved.away });
	}
</script>

<div
	class="sim-chip block bg-base-200 border
		{isFinal ? 'border-primary/80 sim-chip--final' : 'border-base-content/15'}"
	class:sim-chip--clickable={clickable}
>
	{#if isFinal}
		<div class="final-strip">Final</div>
	{/if}

	<!-- Home row -->
	{#if clickable}
		<button
			type="button"
			class="team-row team-row--btn"
			class:is-winner={homeIsWinner}
			on:click={pickHome}
		>
			<span class="bullet" class:win={homeIsWinner} class:hit={homeMatchesMyPick && !homeIsWinner}>{homeIsWinner ? '•' : homeMatchesMyPick ? '✓' : ''}</span>
			{#if hasFlag(resolved.home ?? '')}
				<img src={getFlagUrl(resolved.home ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
			{:else}<span class="flag flag-ph"></span>{/if}
			<span class="tname">{displayTeamName(resolved.home).toUpperCase()}</span>
		</button>
	{:else}
		<div class="team-row" class:is-winner={homeIsWinner} class:tbd={!homeSeeded}>
			<span class="bullet" class:win={homeIsWinner} class:hit={homeMatchesMyPick && !homeIsWinner}>{homeIsWinner ? '•' : homeMatchesMyPick ? '✓' : ''}</span>
			{#if homeSeeded && hasFlag(resolved.home ?? '')}
				<img src={getFlagUrl(resolved.home ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
			{:else}<span class="flag flag-ph"></span>{/if}
			<span class="tname">{homeSeeded ? displayTeamName(resolved.home).toUpperCase() : 'TBD'}</span>
		</div>
	{/if}

	<div class="border-t border-base-content/15" aria-hidden="true"></div>

	<!-- Away row -->
	{#if clickable}
		<button
			type="button"
			class="team-row team-row--btn"
			class:is-winner={awayIsWinner}
			on:click={pickAway}
		>
			<span class="bullet" class:win={awayIsWinner} class:hit={awayMatchesMyPick && !awayIsWinner}>{awayIsWinner ? '•' : awayMatchesMyPick ? '✓' : ''}</span>
			{#if hasFlag(resolved.away ?? '')}
				<img src={getFlagUrl(resolved.away ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
			{:else}<span class="flag flag-ph"></span>{/if}
			<span class="tname">{displayTeamName(resolved.away).toUpperCase()}</span>
		</button>
	{:else}
		<div class="team-row" class:is-winner={awayIsWinner} class:tbd={!awaySeeded}>
			<span class="bullet" class:win={awayIsWinner} class:hit={awayMatchesMyPick && !awayIsWinner}>{awayIsWinner ? '•' : awayMatchesMyPick ? '✓' : ''}</span>
			{#if awaySeeded && hasFlag(resolved.away ?? '')}
				<img src={getFlagUrl(resolved.away ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
			{:else}<span class="flag flag-ph"></span>{/if}
			<span class="tname">{awaySeeded ? displayTeamName(resolved.away).toUpperCase() : 'TBD'}</span>
		</div>
	{/if}
</div>

<style>
	.sim-chip {
		position: relative;
		overflow: hidden;
		border-radius: 6px;
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
	}

	.sim-chip--final {
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.25);
	}

	.sim-chip--clickable {
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.12), 0 0 0 1px hsl(var(--p) / 0.25);
	}

	.final-strip {
		text-align: center;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 10px;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		@apply bg-primary text-primary-content;
		padding: 2px 0;
	}

	/* ── Team row ──────────────────────────────────────────────────────────── */
	.team-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 0.7rem;
		line-height: 1;
		transition: background 120ms ease, opacity 120ms ease;
	}

	.team-row--btn {
		width: 100%;
		border: none;
		background: transparent;
		cursor: pointer;
		color: inherit;
		text-align: left;
	}

	.team-row--btn:hover {
		background: hsl(var(--p) / 0.12);
	}

	.team-row.is-winner {
		font-weight: 700;
		background: rgb(34 197 94 / 0.28);
	}

	.team-row--btn.is-winner {
		background: hsl(var(--p) / 0.25);
	}

	.team-row--btn.is-winner:hover {
		background: hsl(var(--p) / 0.32);
	}

	.team-row.tbd {
		opacity: 0.55;
	}

	/* ── Bullet ─────────────────────────────────────────────────────────────── */
	.bullet {
		width: 0.6rem;
		flex-shrink: 0;
		text-align: center;
		font-size: 0.7rem;
		font-weight: 900;
		line-height: 1;
	}

	/* Scenario winner — gold dot (matches the gold "your call" wash). */
	.bullet.win {
		@apply text-primary;
		font-size: 1rem;
	}

	/* Team the user actually picked in their own bracket entry — green tick. */
	.bullet.hit {
		@apply text-success;
	}

	/* ── Flag ──────────────────────────────────────────────────────────────── */
	.flag {
		width: 14px;
		height: 9px;
		flex-shrink: 0;
		border-radius: 1px;
		box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 15%, transparent);
		object-fit: cover;
	}

	.flag-ph {
		display: inline-block;
		width: 14px;
		height: 9px;
		background: color-mix(in srgb, currentColor 12%, transparent);
		border-radius: 1px;
	}

	/* ── Team name ─────────────────────────────────────────────────────────── */
	.tname {
		font-weight: 600;
		letter-spacing: 0.04em;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* ── Final chip: bigger rows ────────────────────────────────────────────── */
	.sim-chip--final .team-row {
		font-size: 0.95rem;
		padding: 0.5rem 0.75rem;
	}

	.sim-chip--final .flag {
		width: 20px;
		height: 13px;
	}
</style>

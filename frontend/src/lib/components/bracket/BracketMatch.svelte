<!--
	BracketMatch — chip showing two teams stacked.

	Visual: a single card containing two clickable rows. The picked
	team gets a leading "•" bullet, bolder weight and a green wash;
	the unpicked row dims slightly. A locked card disables clicks.

	Each row shows the full country name (e.g. "GERMANY") by default,
	falling back to the 3-letter FIFA code ("GER") if the full name
	would overflow the chip's width. A ResizeObserver re-evaluates the
	fallback per chip whenever its container width changes.

	The card uses neutral DaisyUI base tokens so the wallchart reads as
	a clean light-canvas chart in any theme:
	  bg-base-200 / text-base-content    → chip surface + text (subtle
	                                        gray on near-white panel,
	                                        charcoal text)
	  bg-primary / border-primary        → FINAL accent strip + outline,
	                                        theme-driven so the gold reads
	                                        correctly in both premium-night
	                                        (champagne #D4AF37) and
	                                        hybrid (deeper #B8941F).
	  is-winner background rgb(34 197 94) → green wash on the picked team
	                                        row, pinned to Tailwind green-500
	                                        at 28 % alpha so the highlight
	                                        renders identically in every
	                                        theme. Deepens to 42 % on hover.

	No SVG connectors — the bracket shape is implicit in the parent
	grid's column alignment.
-->
<script lang="ts">
	import { createEventDispatcher, onMount, onDestroy, tick } from 'svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
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
	$: isIncomplete = !team1 || !team2;

	// ── Full-name-or-code rendering ───────────────────────────────────────
	// Render the full country name (e.g. "Germany") by default. After
	// layout, measure each .code span — if scrollWidth exceeds clientWidth
	// the name would overflow / clip, so fall back to the 3-letter code
	// ("GER"). A ResizeObserver watches the chip so the decision re-runs
	// when the parent column resizes.
	let chipEl: HTMLDivElement | undefined;
	let team1CodeEl: HTMLSpanElement | undefined;
	let team2CodeEl: HTMLSpanElement | undefined;
	let team1UseCode = false;
	let team2UseCode = false;
	let resizeObserver: ResizeObserver | null = null;

	async function reEvaluate(): Promise<void> {
		// Reset to the full name first so we always measure the longest
		// desired text against the available width — never the shorter
		// fallback (which would loop us back to "fits, use full name").
		team1UseCode = false;
		team2UseCode = false;
		await tick();
		if (team1CodeEl && team1CodeEl.scrollWidth > team1CodeEl.clientWidth + 1) {
			team1UseCode = true;
		}
		if (team2CodeEl && team2CodeEl.scrollWidth > team2CodeEl.clientWidth + 1) {
			team2UseCode = true;
		}
	}

	onMount(() => {
		if (typeof ResizeObserver !== 'undefined' && chipEl) {
			resizeObserver = new ResizeObserver(() => {
				void reEvaluate();
			});
			resizeObserver.observe(chipEl);
		}
		void reEvaluate();
	});

	onDestroy(() => {
		resizeObserver?.disconnect();
	});

	// Re-evaluate when either team prop changes (different names = different
	// lengths). The reactive statement references team1/team2 only so it
	// does NOT loop when reEvaluate flips the *useCode flags.
	$: team1, team2, void reEvaluate();

	/** Display text for a team slot — full name if it fits, else 3-letter code. */
	function nameOrCode(team: string | null, useCode: boolean): string {
		if (!team) return 'TBD';
		if (useCode) return teamCode(team);
		return displayTeamName(team).toUpperCase();
	}
</script>

<div
	bind:this={chipEl}
	class="bracket-chip relative overflow-hidden rounded-md
		{isIncomplete
			? 'border-2 border-error bg-base-200 text-base-content shadow-sm'
			: isFinal
				? 'border border-primary/80 bg-base-200 text-base-content shadow-lg'
				: 'border border-base-content/15 bg-base-200 text-base-content shadow-sm'}
		{locked ? 'opacity-80' : ''}"
>
	{#if isFinal}
		<div
			class="text-center text-[10px] font-mono uppercase tracking-[0.2em] bg-primary text-primary-content py-0.5"
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
		title={team1 ?? ''}
		on:click={() => selectTeam(team1)}
		aria-label={team1 ? `Pick ${team1}` : 'Team 1 to be decided'}
	>
		<span class="bullet" aria-hidden="true">{team1Selected ? '•' : ''}</span>
		{#if team1 && hasFlag(team1)}
			<img src={getFlagUrl(team1, 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio: 4 / 3" />
		{:else}
			<span class="flag flag-placeholder" aria-hidden="true"></span>
		{/if}
		<span class="code" bind:this={team1CodeEl}>{nameOrCode(team1, team1UseCode)}</span>
	</button>

	<!-- Divider hairline -->
	<div class="border-t border-base-content/15" aria-hidden="true"></div>

	<!-- Team 2 row -->
	<button
		type="button"
		class="team-row {team2Selected ? 'is-winner' : hasPick ? 'is-loser' : ''}"
		class:no-pick={!team2}
		disabled={locked || !team2}
		title={team2 ?? ''}
		on:click={() => selectTeam(team2)}
		aria-label={team2 ? `Pick ${team2}` : 'Team 2 to be decided'}
	>
		<span class="bullet" aria-hidden="true">{team2Selected ? '•' : ''}</span>
		{#if team2 && hasFlag(team2)}
			<img src={getFlagUrl(team2, 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio: 4 / 3" />
		{:else}
			<span class="flag flag-placeholder" aria-hidden="true"></span>
		{/if}
		<span class="code" bind:this={team2CodeEl}>{nameOrCode(team2, team2UseCode)}</span>
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
		background: color-mix(in srgb, currentColor 8%, transparent);
	}

	.team-row:disabled {
		cursor: not-allowed;
	}

	.team-row.is-loser {
		opacity: 0.45;
	}

	/* Winner row: literal Tailwind green-500 wash so the highlight is
	   guaranteed to render regardless of how the active DaisyUI theme
	   serialises its --su variable. Deepened on hover so the wash
	   isn't replaced by the generic hover overlay. */
	.team-row.is-winner {
		font-weight: 700;
		background: rgb(34 197 94 / 0.28) !important;
	}

	.team-row.is-winner:hover:not(:disabled) {
		background: rgb(34 197 94 / 0.42) !important;
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
		box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 15%, transparent);
		object-fit: cover;
	}

	.flag-placeholder {
		display: inline-block;
		background: color-mix(in srgb, currentColor 12%, transparent);
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

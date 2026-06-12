<!--
	FixtureCard — single fixture rendered as a vertical card.

	Replaces FixtureRow.svelte (horizontal 3-col + TAP/preset/stepper state
	machine). The card carries:
	  - Header:   📅 date · 🕐 time     [Match N chip + dirty dot]
	  - Venue:    📍 city, country      (hidden when null)
	  - Home row: [flag] [name] [−][score][+]
	  - Away row: [flag] [name] [−][score][+]

	Border tone encodes per-card state:
	  - locked        → muted base-300/40 + opacity-70  (un-editable fixture)
	  - dirty         → warning/50 + ring + match-chip orange dot
	  - has saved     → success/40
	  - empty (default) → base-300/60

	Score display: shows `-` when no prediction object exists. First tap of
	any stepper sets that side to 1 and defaults the OTHER side to 0
	(atomic-pair model — confirmed UX decision; "incomplete one-sided" is
	unreachable by construction).

	0-15 cap enforced both via `Math.max(0, Math.min(15, ...))` in bump()
	and via `disabled` on the +/- buttons.
-->
<script lang="ts">
	import { unsavedChanges } from '$stores/predictions';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import type { Fixture } from '$lib/types';

	export let fixture: Fixture;
	/** Current prediction for this fixture (null = no prediction object yet). */
	export let prediction: { home: number; away: number } | null = null;
	/** false = fixture locked or sheet not editable. */
	export let editable: boolean = false;
	/** Fired when the user changes the score via either stepper. */
	export let onScore: (home: number, away: number) => void = () => {};

	$: dirty = $unsavedChanges[fixture.id] !== undefined;
	$: hasPrediction = prediction !== null;
	$: locked = !editable;

	$: homeScore = prediction?.home ?? null;
	$: awayScore = prediction?.away ?? null;

	// Predicted outcome — drives per-team-name weight. Bold for the
	// winner, muted for the loser, neutral medium for draw / no
	// prediction. Computed once at card level (needs both scores) and
	// passed into each row as a class string.
	type Outcome = 'home' | 'away' | 'draw' | 'none';
	$: outcome = ((): Outcome => {
		if (homeScore === null || awayScore === null) return 'none';
		if (homeScore > awayScore) return 'home';
		if (awayScore > homeScore) return 'away';
		return 'draw';
	})();
	function nameClass(side: 'home' | 'away'): string {
		if (outcome === 'none' || outcome === 'draw') return 'font-medium text-base-content';
		if (outcome === side) return 'font-bold text-base-content';
		return 'font-normal text-base-content/60';
	}

	$: borderClass = locked
		? 'border-base-300/40 opacity-70'
		: dirty
			? 'border-warning/50 ring-1 ring-warning/30'
			: hasPrediction
				? 'border-success/40'
				: 'border-base-300/60';

	// Kickoff formatting — split into date and time so the header can show
	// both with a separating dot.
	$: kickoffDate = new Date(fixture.kickoff);
	$: fmtDate = kickoffDate.toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'long',
		year: 'numeric'
	});
	$: fmtTime = kickoffDate.toLocaleTimeString('en-GB', {
		hour: '2-digit',
		minute: '2-digit'
	});

	function bump(side: 'home' | 'away', delta: number) {
		if (locked) return;
		// Treat null as 0 so the very first tap creates a (1,0) or (0,1)
		// prediction pair — locked atomic-first-tap behaviour.
		const h = prediction?.home ?? 0;
		const a = prediction?.away ?? 0;
		const newH =
			side === 'home' ? Math.max(0, Math.min(15, h + delta)) : h;
		const newA =
			side === 'away' ? Math.max(0, Math.min(15, a + delta)) : a;
		onScore(newH, newA);
	}
</script>

<article
	class="fixture-card rounded-xl border bg-base-100 p-2.5 transition-colors {borderClass}"
	aria-label="{fixture.home_team} vs {fixture.away_team}"
>
	<!-- Header: date · time on the left, Match # chip (with dirty dot) on the right -->
	<header class="flex items-center justify-between gap-3 text-[11px] text-base-content/60 mb-1.5">
		<span class="font-mono truncate">
			{fmtDate}
			<span class="opacity-50 mx-1">·</span>
			{fmtTime}
		</span>
		{#if fixture.match_number !== null}
			<span class="badge badge-sm badge-ghost font-mono relative flex-shrink-0">
				Match {fixture.match_number}
				{#if dirty}
					<span
						class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-warning"
						aria-label="Unsaved changes"
					></span>
				{/if}
			</span>
		{/if}
	</header>

	<!-- Venue (hidden until backend ships venue data) -->
	{#if fixture.venue_city}
		<p class="text-xs text-base-content/50 mb-3">
			<span aria-hidden="true">📍</span>
			{fixture.venue_city}{#if fixture.venue_country}, {fixture.venue_country}{/if}
		</p>
	{/if}

	<!-- Team rows. Inline-rendered (six buttons total — not worth a separate component yet). -->
	{#each [{ side: 'home', team: fixture.home_team, score: homeScore }, { side: 'away', team: fixture.away_team, score: awayScore }] as row (row.side)}
		<div class="flex items-center gap-3 py-1">
			{#if hasFlag(row.team)}
				<img
					src={getFlagUrl(row.team, 'md')}
					alt=""
					class="w-7 h-auto rounded-sm flex-shrink-0" style="aspect-ratio: 4 / 3" />
			{:else}
				<span class="w-7 h-5 rounded-sm bg-base-300/50 flex-shrink-0" aria-hidden="true"></span>
			{/if}
			<span
				class="flex-1 truncate text-[0.9375rem] transition-colors {nameClass(row.side === 'home' ? 'home' : 'away')}"
				title={row.team}>{displayTeamName(row.team)}</span>
			<!-- Stepper trio: ring-style buttons + a "score tile" in the middle.
			     The tile shares the buttons' border + neutral fill so the three
			     pieces read as a single composite control. Digits use font-display
			     to match the hero doughnut's numeric typography. -->
			<div class="inline-flex items-center gap-1.5">
				<button
					type="button"
					class="w-8 h-8 rounded-full border border-base-content/15 bg-base-100 text-base-content/80 hover:bg-base-200 hover:border-base-content/25 disabled:opacity-30 disabled:hover:bg-base-100 disabled:hover:border-base-content/15 transition-colors flex items-center justify-center text-base leading-none"
					disabled={locked || (row.score ?? 0) <= 0}
					on:click={() => bump(row.side === 'home' ? 'home' : 'away', -1)}
					aria-label="Decrease {row.team} score"
				>−</button>
				<span
					class="inline-flex items-center justify-center w-10 h-8 rounded-xl border border-base-content/15 bg-base-200/40 font-display font-bold text-sm tabular-nums text-base-content leading-none"
					aria-label="{row.team} predicted score"
				>{row.score ?? '-'}</span>
				<button
					type="button"
					class="w-8 h-8 rounded-full border border-base-content/15 bg-base-100 text-base-content/80 hover:bg-base-200 hover:border-base-content/25 disabled:opacity-30 disabled:hover:bg-base-100 disabled:hover:border-base-content/15 transition-colors flex items-center justify-center text-base leading-none"
					disabled={locked || (row.score ?? 0) >= 15}
					on:click={() => bump(row.side === 'home' ? 'home' : 'away', +1)}
					aria-label="Increase {row.team} score"
				>+</button>
			</div>
		</div>
	{/each}
</article>

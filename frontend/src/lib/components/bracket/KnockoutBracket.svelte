<!--
	KnockoutBracket — symmetric wallchart visualisation of the knockout
	stage. The matches converge from R32 on the outer edges through R16,
	QF and SF to the FINAL at the centre.

	Two layouts:
	  - Desktop (≥ lg / 1024 px): 9-column CSS grid wallchart with the
	    Final column centred and slightly wider.
	  - Mobile (< lg): a 4-page swipeable carousel
	      page 0 → R32 (left + right halves shown side-by-side)
	      page 1 → R16
	      page 2 → QF + SF
	      page 3 → Final + Champion sticker
	    Champion strip is also persistent at the page footer.

	Prop signature is unchanged from the previous linear version, so
	existing callers (entry-detail page, Phase1Bracket wizard wrapper)
	work without code changes.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import BracketMatch from './BracketMatch.svelte';
	import ChampionStrip from './ChampionStrip.svelte';
	import {
		initializeBracketState,
		predictionToBracketState,
		getDisplayMatches,
		bracketStateToPrediction,
		setMatchWinner,
		type GroupStandingsMap
	} from '$lib/utils/bracketResolver';
	import type { BracketPrediction } from '$types';

	export let prediction: BracketPrediction | null = null;
	export let groupStandings: GroupStandingsMap = {};
	export let locked: boolean = false;
	export let phase: 'phase_1' | 'phase_2' = 'phase_1';

	const dispatch = createEventDispatcher<{
		update: BracketPrediction;
		clear: void;
	}>();

	// ── Derived bracket state ────────────────────────────────────────────────
	$: state = (() => {
		if (Object.keys(groupStandings).length === 0) return null;
		if (prediction && hasValidPrediction(prediction)) {
			return predictionToBracketState(prediction, groupStandings);
		}
		return initializeBracketState(groupStandings);
	})();

	$: r32Matches = state ? getDisplayMatches(state, 'round_of_32') : [];
	$: r16Matches = state ? getDisplayMatches(state, 'round_of_16') : [];
	$: qfMatches = state ? getDisplayMatches(state, 'quarter_finals') : [];
	$: sfMatches = state ? getDisplayMatches(state, 'semi_finals') : [];
	$: finalMatches = state ? getDisplayMatches(state, 'final') : [];

	// ── Left / right halves for the symmetric wallchart ─────────────────────
	// FIFA pairs the bracket so the first half of each round's matches
	// feeds the left side of the next round; the second half feeds the right.
	$: r32L = r32Matches.slice(0, Math.ceil(r32Matches.length / 2));
	$: r32R = r32Matches.slice(Math.ceil(r32Matches.length / 2));
	$: r16L = r16Matches.slice(0, Math.ceil(r16Matches.length / 2));
	$: r16R = r16Matches.slice(Math.ceil(r16Matches.length / 2));
	$: qfL = qfMatches.slice(0, Math.ceil(qfMatches.length / 2));
	$: qfR = qfMatches.slice(Math.ceil(qfMatches.length / 2));
	$: sfL = sfMatches.slice(0, Math.ceil(sfMatches.length / 2));
	$: sfR = sfMatches.slice(Math.ceil(sfMatches.length / 2));
	// Final centre card: the actual final (match 104), not the third-place
	// playoff (match 103) which lives in the same round bucket on some configs.
	$: finalMatch =
		finalMatches.find((m) => m.match.matchNumber === 104) ?? finalMatches[0] ?? null;

	$: tournamentWinner = state?.matchResults[104]?.winner ?? null;

	// ── Picks count: distinct match winners chosen so far ────────────────────
	// Excludes the third-place playoff (match 103) so the count matches the
	// wallchart header total of 31 = R32(16) + R16(8) + QF(4) + SF(2) + F(1).
	$: picked = state
		? Object.entries(state.matchResults).filter(
				([num, m]) => Number(num) !== 103 && m.winner !== null
			).length
		: 0;
	const TOTAL_PICKS = 31;

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

	// ── Selection handling ──────────────────────────────────────────────────
	function handleSelectWinner(
		event: CustomEvent<{ matchNumber: number | null; winner: string }>
	) {
		const { matchNumber, winner } = event.detail;
		if (!state || matchNumber === null) return;
		const newState = setMatchWinner(state, matchNumber, winner);
		const newPrediction = bracketStateToPrediction(newState);
		dispatch('update', newPrediction);
	}

	export function clearAllSelections() {
		if (!state || !groupStandings) return;
		const emptyState = initializeBracketState(groupStandings);
		const emptyPrediction = bracketStateToPrediction(emptyState);
		dispatch('update', emptyPrediction);
	}

	// ── Mobile carousel state ────────────────────────────────────────────────
	let page = 0;
	const PAGE_COUNT = 4;
	const PAGE_LABELS = [
		'R32 · L + R',
		'R16 · L + R',
		'QF → SF',
		'FINAL · CHAMPION'
	] as const;

	function goPrev() {
		if (page > 0) page -= 1;
	}
	function goNext() {
		if (page < PAGE_COUNT - 1) page += 1;
	}

	// Swipe handling — minimal: just track touch start X and resolve on end.
	let touchStartX: number | null = null;
	function onTouchStart(e: TouchEvent) {
		touchStartX = e.touches[0]?.clientX ?? null;
	}
	function onTouchEnd(e: TouchEvent) {
		if (touchStartX === null) return;
		const endX = e.changedTouches[0]?.clientX ?? touchStartX;
		const dx = endX - touchStartX;
		if (dx > 50) goPrev();
		else if (dx < -50) goNext();
		touchStartX = null;
	}
</script>

<!-- ═══════════════════════════════════════════════════════════════════════
	 DESKTOP WALLCHART (≥ lg)
	 Neutral DaisyUI token palette — bg-base-100 canvas, bg-base-200 chips,
	 text-base-content body, with primary as the title accent, secondary
	 as the FINAL vibrant focal hue, and success as the champion frame.
	 ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="wallchart-panel hidden lg:block bg-base-100 text-base-content
		rounded-2xl p-6 shadow-2xl border border-base-content/15"
>
	<!-- Header strip: title + status meta -->
	<header class="flex items-start justify-between mb-3 gap-6">
		<h2 class="font-display text-2xl tracking-wide leading-none">
			YOUR <span class="text-primary">BRACKET</span>
		</h2>

		<dl
			class="grid grid-flow-col auto-cols-max gap-x-8 gap-y-0
				text-[10px] font-mono uppercase tracking-[0.18em] opacity-90"
		>
			<dt class="opacity-60 row-start-1">Picks Locked</dt>
			<dt class="opacity-60 row-start-1">Status</dt>
			<dt class="opacity-60 row-start-1">Final · Your Pick</dt>
			<dd class="row-start-2 font-display text-lg leading-none tracking-wide">
				{picked} / {TOTAL_PICKS}
			</dd>
			<dd class="row-start-2 font-display text-lg leading-none tracking-wide">
				{locked ? 'LOCKED' : 'OPEN'}
			</dd>
			<dd
				class="row-start-2 font-display text-lg leading-none tracking-wide text-primary"
			>
				{tournamentWinner ? tournamentWinner.toUpperCase() : '—'}
			</dd>
		</dl>
	</header>

	<hr class="border-base-content/15 mb-5" />

	<!-- 9-column wallchart -->
	<div
		class="grid gap-3 items-stretch"
		style="grid-template-columns: 1.1fr 1.1fr 1.1fr 1.1fr 1.5fr 1.1fr 1.1fr 1.1fr 1.1fr;"
	>
		<!-- Column header labels -->
		<div class="col-label">R32 · L</div>
		<div class="col-label">R16 · L</div>
		<div class="col-label">QF · L</div>
		<div class="col-label">SF · L</div>
		<div class="col-label col-label--final">FINAL</div>
		<div class="col-label">SF · R</div>
		<div class="col-label">QF · R</div>
		<div class="col-label">R16 · R</div>
		<div class="col-label">R32 · R</div>

		<!-- Match columns: each col is justified around its vertical space so
			 the matches converge towards the centre via implicit alignment. -->
		<div class="match-col">
			{#each r32L as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`round_of_32-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="round_of_32"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each r16L as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`round_of_16-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="round_of_16"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each qfL as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`quarter_finals-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="quarter_finals"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each sfL as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`semi_finals-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="semi_finals"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<!-- Centre: Final card + Champion strip -->
		<div class="match-col justify-center">
			{#if finalMatch}
				<div class="bracket-chip-final">
					<BracketMatch
						matchId={`final-${finalMatch.match.matchNumber}`}
						matchNumber={finalMatch.match.matchNumber}
						team1={finalMatch.homeTeam}
						team2={finalMatch.awayTeam}
						winner={finalMatch.winner}
						roundCode="final"
						{locked}
						isFinal={true}
						on:selectWinner={handleSelectWinner}
					/>
				</div>
				<div class="mt-3">
					<ChampionStrip
						champion={tournamentWinner}
						{picked}
						total={TOTAL_PICKS}
						showPicks={false}
					/>
				</div>
			{/if}
		</div>

		<div class="match-col">
			{#each sfR as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`semi_finals-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="semi_finals"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each qfR as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`quarter_finals-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="quarter_finals"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each r16R as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`round_of_16-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="round_of_16"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>

		<div class="match-col">
			{#each r32R as m (m.match.matchNumber)}
				<BracketMatch
					matchId={`round_of_32-${m.match.matchNumber}`}
					matchNumber={m.match.matchNumber}
					team1={m.homeTeam}
					team2={m.awayTeam}
					winner={m.winner}
					roundCode="round_of_32"
					{locked}
					on:selectWinner={handleSelectWinner}
				/>
			{/each}
		</div>
	</div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════════
	 MOBILE CAROUSEL (< lg)
	 ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="wallchart-panel lg:hidden bg-base-100 text-base-content
		rounded-2xl p-4 shadow-2xl border border-base-content/15"
>
	<!-- Header: title + page dots + counter -->
	<header class="flex items-center justify-between mb-3 gap-3">
		<h2 class="font-display text-base tracking-wide leading-none">
			YOUR <span class="text-primary">BRACKET</span>
		</h2>
		<div class="flex gap-1.5">
			{#each Array(PAGE_COUNT) as _, i}
				<button
					type="button"
					class="w-1.5 h-1.5 rounded-full transition-colors
						{page === i ? 'bg-primary' : 'bg-base-content/30'}"
					aria-label={`Go to page ${i + 1}`}
					on:click={() => (page = i)}
				></button>
			{/each}
		</div>
		<span class="font-mono text-[10px] uppercase tracking-[0.18em] opacity-80">
			{picked} / {TOTAL_PICKS}
		</span>
	</header>

	<!-- Current page label -->
	<div
		class="rounded bg-base-content/10 px-3 py-1.5 mb-3 text-center
			text-[11px] font-mono uppercase tracking-[0.2em]"
	>
		{PAGE_LABELS[page]}
	</div>

	<!-- Sliding track -->
	<div
		class="overflow-hidden"
		role="region"
		aria-roledescription="carousel"
		aria-label="Bracket pages"
		on:touchstart={onTouchStart}
		on:touchend={onTouchEnd}
	>
		<div
			class="flex transition-transform duration-300 ease-out"
			style="transform: translateX(-{page * 100}%);"
		>
			<!-- Page 0: R32 (8L + 8R side by side) -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						{#each r32L as m (m.match.matchNumber)}
							<BracketMatch
								matchId={`round_of_32-${m.match.matchNumber}`}
								matchNumber={m.match.matchNumber}
								team1={m.homeTeam}
								team2={m.awayTeam}
								winner={m.winner}
								roundCode="round_of_32"
								{locked}
								on:selectWinner={handleSelectWinner}
							/>
						{/each}
					</div>
					<div class="space-y-1.5">
						{#each r32R as m (m.match.matchNumber)}
							<BracketMatch
								matchId={`round_of_32-${m.match.matchNumber}`}
								matchNumber={m.match.matchNumber}
								team1={m.homeTeam}
								team2={m.awayTeam}
								winner={m.winner}
								roundCode="round_of_32"
								{locked}
								on:selectWinner={handleSelectWinner}
							/>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 1: R16 (4L + 4R) -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-2">
						{#each r16L as m (m.match.matchNumber)}
							<BracketMatch
								matchId={`round_of_16-${m.match.matchNumber}`}
								matchNumber={m.match.matchNumber}
								team1={m.homeTeam}
								team2={m.awayTeam}
								winner={m.winner}
								roundCode="round_of_16"
								{locked}
								on:selectWinner={handleSelectWinner}
							/>
						{/each}
					</div>
					<div class="space-y-2">
						{#each r16R as m (m.match.matchNumber)}
							<BracketMatch
								matchId={`round_of_16-${m.match.matchNumber}`}
								matchNumber={m.match.matchNumber}
								team1={m.homeTeam}
								team2={m.awayTeam}
								winner={m.winner}
								roundCode="round_of_16"
								{locked}
								on:selectWinner={handleSelectWinner}
							/>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 2: QF on left, SF on right -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-3">
					<div>
						<div
							class="text-[10px] font-mono uppercase tracking-widest opacity-60 mb-1.5"
						>
							QF
						</div>
						<div class="space-y-2">
							{#each qfMatches as m (m.match.matchNumber)}
								<BracketMatch
									matchId={`quarter_finals-${m.match.matchNumber}`}
									matchNumber={m.match.matchNumber}
									team1={m.homeTeam}
									team2={m.awayTeam}
									winner={m.winner}
									roundCode="quarter_finals"
									{locked}
									on:selectWinner={handleSelectWinner}
								/>
							{/each}
						</div>
					</div>
					<div>
						<div
							class="text-[10px] font-mono uppercase tracking-widest opacity-60 mb-1.5"
						>
							SF
						</div>
						<div class="space-y-2">
							{#each sfMatches as m (m.match.matchNumber)}
								<BracketMatch
									matchId={`semi_finals-${m.match.matchNumber}`}
									matchNumber={m.match.matchNumber}
									team1={m.homeTeam}
									team2={m.awayTeam}
									winner={m.winner}
									roundCode="semi_finals"
									{locked}
									on:selectWinner={handleSelectWinner}
								/>
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- Page 3: Final + Champion -->
			<div class="min-w-full px-0.5">
				<div class="flex flex-col items-center gap-4 py-2">
					{#if finalMatch}
						<div class="w-full max-w-xs bracket-chip-final">
							<BracketMatch
								matchId={`final-${finalMatch.match.matchNumber}`}
								matchNumber={finalMatch.match.matchNumber}
								team1={finalMatch.homeTeam}
								team2={finalMatch.awayTeam}
								winner={finalMatch.winner}
								roundCode="final"
								{locked}
								isFinal={true}
								on:selectWinner={handleSelectWinner}
							/>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Persistent champion strip -->
	<div class="mt-4">
		<ChampionStrip
			champion={tournamentWinner}
			{picked}
			total={TOTAL_PICKS}
			compact={true}
		/>
	</div>

	<!-- Footer nav -->
	<footer
		class="flex items-center justify-between mt-3 text-[11px] font-mono uppercase tracking-[0.15em]"
	>
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
			disabled={page === 0}
			on:click={goPrev}
		>
			← Prev
		</button>
		<span class="opacity-60">Page {page + 1} / {PAGE_COUNT}</span>
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
			disabled={page === PAGE_COUNT - 1}
			on:click={goNext}
		>
			Next →
		</button>
	</footer>
</div>

<style>
	/* .wallchart-panel — semantic class kept on the panel divs for
	   future styling hooks. Surface colour comes from bg-base-100 on
	   the parent element; no extra texture. */

	.col-label {
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 10px;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		text-align: center;
		opacity: 0.7;
		padding: 0.35rem 0.5rem;
		background: color-mix(in srgb, currentColor 6%, transparent);
		border-radius: 4px;
	}

	.col-label--final {
		/* Pinned gold (darker hex for legibility on light panels;
		   stays readable on dark panels too). Background tints the
		   project's #FFD700 gold at 18 % alpha. */
		color: #b8860b;
		font-weight: 700;
		opacity: 1;
		background: rgb(255 215 0 / 0.18);
	}

	.match-col {
		display: flex;
		flex-direction: column;
		justify-content: space-around;
		gap: 6px;
		min-height: 100%;
	}

</style>

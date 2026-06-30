<!--
	ResultsBracket — read-only tournament wallchart for V4 Results page (v2.187.0).

	Drives off $fixtures (team names already resolved by the backend
	ko_lineup_resolver chain at read time) and $bracketPrediction (the
	active entry's submitted picks). No interactive selection — purely
	a scan surface.

	★ Per-side seeded check invariant (v2.184.x):
	  homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')
	  Never a binary "either side = TBD" gate.
	★ third_place excluded (v2.164.0): stage never surfaces in this
	  wallchart. finalF is identified by matchNumber 104.
	★ koLoserSide priority: pens → ET → regulation (v2.185.1).

	Two layouts:
	  Desktop (≥ lg): 9-column CSS grid wallchart (same full-bleed
	    technique as KnockoutBracket — escapes max-w-[1180px] container).
	  Mobile (< lg): 4-page swipeable carousel (same pattern).
-->
<script lang="ts">
	import type { BracketPrediction, Fixture } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import { bracketPicksForRound, fixtureKoHits, isRoundLineupSeeded } from '$lib/utils/koPoints';
	import { koLoserSide } from '$lib/utils/matchDetailV4';
	import { displayTeamName } from '$lib/utils/teamName';
	import { matchNumberOf } from '$lib/utils/bracketGeometry';

	export let fixtures: Fixture[];
	export let bracketPrediction: BracketPrediction | null;
	export let rules: ScoringRules | null;
	export let knockoutScoringEnabled: boolean;

	// ── KO fixture sets, sorted by FIFA match number ─────────────────────────
	function koByStage(stage: string): Fixture[] {
		return fixtures
			.filter((f) => f.stage === stage)
			.sort(
				(a, b) =>
					(matchNumberOf(a, fixtures) ?? 999) - (matchNumberOf(b, fixtures) ?? 999)
			);
	}

	$: r32All = koByStage('round_of_32');
	$: r16All = koByStage('round_of_16');
	$: qfAll = koByStage('quarter_final');
	$: sfAll = koByStage('semi_final');
	// M104 is the final; exclude third_place (M103) which shares the 'final'/'third_place' stage bucket.
	$: finalF =
		fixtures.find((f) => f.stage === 'final' && matchNumberOf(f, fixtures) === 104) ??
		fixtures.find((f) => f.stage === 'final') ??
		null;

	// ── L / R halves (FIFA match-number-sorted: M73-M80 left, M81-M88 right) ─
	$: r32L = r32All.slice(0, 8);
	$: r32R = r32All.slice(8);
	$: r16L = r16All.slice(0, 4);
	$: r16R = r16All.slice(4);
	$: qfL = qfAll.slice(0, 2);
	$: qfR = qfAll.slice(2);
	$: sfL = sfAll.slice(0, 1);
	$: sfR = sfAll.slice(1);

	// ── Bracket picks per round ───────────────────────────────────────────────
	$: r32Picks = bracketPicksForRound(bracketPrediction, 'r32');
	$: r16Picks = bracketPicksForRound(bracketPrediction, 'r16');
	$: qfPicks = bracketPicksForRound(bracketPrediction, 'qf');
	$: sfPicks = bracketPicksForRound(bracketPrediction, 'sf');
	$: fPicks = bracketPicksForRound(bracketPrediction, 'f');

	// ── Lineup-seeded gates ───────────────────────────────────────────────────
	$: r32Seeded = isRoundLineupSeeded(r32All);
	$: r16Seeded = isRoundLineupSeeded(r16All);
	$: qfSeeded = isRoundLineupSeeded(qfAll);
	$: sfSeeded = isRoundLineupSeeded(sfAll);
	$: fSeeded = isRoundLineupSeeded(finalF ? [finalF] : []);

	// ── Scoring rules ─────────────────────────────────────────────────────────
	$: adv = rules?.advancement ?? ({} as Record<string, number>);

	// ── Hit counts (for points strip) ────────────────────────────────────────
	function roundHits(fxs: Fixture[], picks: Set<string>): number {
		return fxs.reduce((s, f) => s + fixtureKoHits(f, picks).hits, 0);
	}

	$: r32Hits = roundHits(r32All, r32Picks);
	$: r16Hits = roundHits(r16All, r16Picks);
	$: qfHits = roundHits(qfAll, qfPicks);
	$: sfHits = roundHits(sfAll, sfPicks);
	$: fHits = roundHits(finalF ? [finalF] : [], fPicks);

	// ── Mobile carousel ───────────────────────────────────────────────────────
	let page = 0;
	const PAGE_COUNT = 4;
	const PAGE_LABELS = ['R32 · L + R', 'R16 · L + R', 'QF + SF', 'Final'] as const;

	function goPrev() {
		if (page > 0) page -= 1;
	}
	function goNext() {
		if (page < PAGE_COUNT - 1) page += 1;
	}

	let touchStartX: number | null = null;
	function onTouchStart(e: TouchEvent) {
		touchStartX = e.touches[0]?.clientX ?? null;
	}
	function onTouchEnd(e: TouchEvent) {
		if (touchStartX === null) return;
		const dx = (e.changedTouches[0]?.clientX ?? touchStartX) - touchStartX;
		if (dx > 50) goPrev();
		else if (dx < -50) goNext();
		touchStartX = null;
	}
</script>

<!-- ═══════════════════════════════════════════════════════════════════════
     DESKTOP WALLCHART (≥ lg)
     Full-bleed so the 9 columns have room: escapes max-w-[1180px].
     The -12rem in the calc reserves for <main>'s pl-48 sidebar offset.
     ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="hidden lg:block bg-base-100 text-base-content rounded-2xl
		p-6 shadow-2xl border border-base-content/15 mt-3
		relative left-1/2 -translate-x-1/2
		w-[calc(100vw-2rem-12rem)] max-w-[1800px]"
>
	{#if !bracketPrediction}
		<p class="text-center text-sm text-base-content/55 mb-4">
			This entry hasn't submitted bracket picks — showing actual results only.
		</p>
	{/if}

	<!-- 9-column wallchart grid -->
	<div
		class="grid gap-x-4 gap-y-2 items-stretch"
		style="grid-template-columns: repeat(4, minmax(0, 1.1fr)) minmax(0, 1.5fr) repeat(4, minmax(0, 1.1fr));"
	>
		<!-- Column headers -->
		<div class="col-label">R32</div>
		<div class="col-label">R16</div>
		<div class="col-label">QF</div>
		<div class="col-label">SF</div>
		<div class="col-label col-label--final">FINAL</div>
		<div class="col-label">SF</div>
		<div class="col-label">QF</div>
		<div class="col-label">R16</div>
		<div class="col-label">R32</div>

		<!-- R32 Left -->
		<div class="match-col">
			{#each r32L as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && r32Picks.has(f.home_team)}
				{@const awayHit = awaySeeded && r32Picks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark" aria-label="bracket pick">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark" aria-label="bracket pick">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- R16 Left -->
		<div class="match-col">
			{#each r16L as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && r16Picks.has(f.home_team)}
				{@const awayHit = awaySeeded && r16Picks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- QF Left -->
		<div class="match-col">
			{#each qfL as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && qfPicks.has(f.home_team)}
				{@const awayHit = awaySeeded && qfPicks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- SF Left -->
		<div class="match-col">
			{#each sfL as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && sfPicks.has(f.home_team)}
				{@const awayHit = awaySeeded && sfPicks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- Final (centre, vertically centred) -->
		<div class="match-col justify-center">
			{#if finalF}
				{@const loser = koLoserSide(finalF.score)}
				{@const homeSeeded = !!finalF.home_team && !finalF.home_team.startsWith('slot:')}
				{@const awaySeeded = !!finalF.away_team && !finalF.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && fPicks.has(finalF.home_team)}
				{@const awayHit = awaySeeded && fPicks.has(finalF.away_team)}
				<div class="match-cell match-cell--final">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(finalF.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(finalF.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/if}
		</div>

		<!-- SF Right -->
		<div class="match-col">
			{#each sfR as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && sfPicks.has(f.home_team)}
				{@const awayHit = awaySeeded && sfPicks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- QF Right -->
		<div class="match-col">
			{#each qfR as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && qfPicks.has(f.home_team)}
				{@const awayHit = awaySeeded && qfPicks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- R16 Right -->
		<div class="match-col">
			{#each r16R as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && r16Picks.has(f.home_team)}
				{@const awayHit = awaySeeded && r16Picks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- R32 Right -->
		<div class="match-col">
			{#each r32R as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && r32Picks.has(f.home_team)}
				{@const awayHit = awaySeeded && r32Picks.has(f.away_team)}
				<div class="match-cell">
					<div class="team-row" class:loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="team-name">{displayTeamName(f.home_team)}</span>
						{#if homeHit}<span class="hit-mark">✓</span>{/if}
					</div>
					<div class="team-row" class:loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="team-name">{displayTeamName(f.away_team)}</span>
						{#if awayHit}<span class="hit-mark">✓</span>{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>

	<!-- Points summary strip — only when knockout scoring is active and at
	     least one round's lineup is confirmed -->
	{#if knockoutScoringEnabled && (r32Seeded || r16Seeded || qfSeeded || sfSeeded || fSeeded)}
		<div
			class="mt-5 pt-4 border-t border-base-content/10
				flex flex-wrap items-center justify-center gap-x-8 gap-y-1
				text-[10px] font-mono uppercase tracking-[0.15em] text-base-content/60"
		>
			{#if r32Seeded}
				<span
					><span class="text-success">✓</span> R32 · {r32Hits}/{r32All.length} ×
					{adv['round_of_32'] ?? '?'}pts</span
				>
			{/if}
			{#if r16Seeded}
				<span
					><span class="text-success">✓</span> R16 · {r16Hits}/{r16All.length} ×
					{adv['round_of_16'] ?? '?'}pts</span
				>
			{/if}
			{#if qfSeeded}
				<span
					><span class="text-success">✓</span> QF · {qfHits}/{qfAll.length} ×
					{adv['quarter_final'] ?? '?'}pts</span
				>
			{/if}
			{#if sfSeeded}
				<span
					><span class="text-success">✓</span> SF · {sfHits}/{sfAll.length} ×
					{adv['semi_final'] ?? '?'}pts</span
				>
			{/if}
			{#if fSeeded}
				<span
					><span class="text-success">✓</span> F · {fHits}/1 ×
					{adv['final'] ?? '?'}pts</span
				>
			{/if}
		</div>
	{/if}
</div>

<!-- ═══════════════════════════════════════════════════════════════════════
     MOBILE CAROUSEL (< lg)
     4 pages: R32 | R16 | QF+SF | Final
     ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="lg:hidden bg-base-100 text-base-content rounded-2xl
		p-4 shadow-2xl border border-base-content/15 mt-3"
>
	<!-- Header: page label + dots -->
	<header class="flex items-center justify-between mb-3 gap-3">
		<div
			class="rounded bg-base-content/10 px-3 py-1.5
				text-[11px] font-mono uppercase tracking-[0.2em]"
		>
			{PAGE_LABELS[page]}
		</div>
		<div class="flex gap-1.5">
			{#each Array(PAGE_COUNT) as _, i}
				<button
					type="button"
					class="w-2 h-2 rounded-full transition-colors
						{page === i ? 'bg-primary' : 'bg-base-content/30'}"
					aria-label="Go to page {i + 1}"
					on:click={() => (page = i)}
				></button>
			{/each}
		</div>
	</header>

	{#if !bracketPrediction}
		<p class="text-xs text-base-content/55 mb-3">
			No bracket picks — showing actual results only.
		</p>
	{/if}

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
			<div class="min-w-full">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						{#each r32L as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r32Picks.has(f.home_team)}
							{@const awayHit = awaySeeded && r32Picks.has(f.away_team)}
							<div class="match-cell">
								<div
									class="team-row"
									class:loser={loser === 'home'}
									class:tbd={!homeSeeded}
								>
									<span class="team-name">{displayTeamName(f.home_team)}</span>
									{#if homeHit}<span class="hit-mark">✓</span>{/if}
								</div>
								<div
									class="team-row"
									class:loser={loser === 'away'}
									class:tbd={!awaySeeded}
								>
									<span class="team-name">{displayTeamName(f.away_team)}</span>
									{#if awayHit}<span class="hit-mark">✓</span>{/if}
								</div>
							</div>
						{/each}
					</div>
					<div class="space-y-1.5">
						{#each r32R as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r32Picks.has(f.home_team)}
							{@const awayHit = awaySeeded && r32Picks.has(f.away_team)}
							<div class="match-cell">
								<div
									class="team-row"
									class:loser={loser === 'home'}
									class:tbd={!homeSeeded}
								>
									<span class="team-name">{displayTeamName(f.home_team)}</span>
									{#if homeHit}<span class="hit-mark">✓</span>{/if}
								</div>
								<div
									class="team-row"
									class:loser={loser === 'away'}
									class:tbd={!awaySeeded}
								>
									<span class="team-name">{displayTeamName(f.away_team)}</span>
									{#if awayHit}<span class="hit-mark">✓</span>{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 1: R16 (4L + 4R) -->
			<div class="min-w-full">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-2">
						{#each r16L as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r16Picks.has(f.home_team)}
							{@const awayHit = awaySeeded && r16Picks.has(f.away_team)}
							<div class="match-cell">
								<div
									class="team-row"
									class:loser={loser === 'home'}
									class:tbd={!homeSeeded}
								>
									<span class="team-name">{displayTeamName(f.home_team)}</span>
									{#if homeHit}<span class="hit-mark">✓</span>{/if}
								</div>
								<div
									class="team-row"
									class:loser={loser === 'away'}
									class:tbd={!awaySeeded}
								>
									<span class="team-name">{displayTeamName(f.away_team)}</span>
									{#if awayHit}<span class="hit-mark">✓</span>{/if}
								</div>
							</div>
						{/each}
					</div>
					<div class="space-y-2">
						{#each r16R as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r16Picks.has(f.home_team)}
							{@const awayHit = awaySeeded && r16Picks.has(f.away_team)}
							<div class="match-cell">
								<div
									class="team-row"
									class:loser={loser === 'home'}
									class:tbd={!homeSeeded}
								>
									<span class="team-name">{displayTeamName(f.home_team)}</span>
									{#if homeHit}<span class="hit-mark">✓</span>{/if}
								</div>
								<div
									class="team-row"
									class:loser={loser === 'away'}
									class:tbd={!awaySeeded}
								>
									<span class="team-name">{displayTeamName(f.away_team)}</span>
									{#if awayHit}<span class="hit-mark">✓</span>{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 2: QF + SF -->
			<div class="min-w-full">
				<div class="grid grid-cols-2 gap-3">
					<div>
						<div class="section-label">QF</div>
						<div class="space-y-2">
							{#each qfAll as f (f.id)}
								{@const loser = koLoserSide(f.score)}
								{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
								{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
								{@const homeHit = homeSeeded && qfPicks.has(f.home_team)}
								{@const awayHit = awaySeeded && qfPicks.has(f.away_team)}
								<div class="match-cell">
									<div
										class="team-row"
										class:loser={loser === 'home'}
										class:tbd={!homeSeeded}
									>
										<span class="team-name">{displayTeamName(f.home_team)}</span>
										{#if homeHit}<span class="hit-mark">✓</span>{/if}
									</div>
									<div
										class="team-row"
										class:loser={loser === 'away'}
										class:tbd={!awaySeeded}
									>
										<span class="team-name">{displayTeamName(f.away_team)}</span>
										{#if awayHit}<span class="hit-mark">✓</span>{/if}
									</div>
								</div>
							{/each}
						</div>
					</div>
					<div>
						<div class="section-label">SF</div>
						<div class="space-y-2">
							{#each sfAll as f (f.id)}
								{@const loser = koLoserSide(f.score)}
								{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
								{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
								{@const homeHit = homeSeeded && sfPicks.has(f.home_team)}
								{@const awayHit = awaySeeded && sfPicks.has(f.away_team)}
								<div class="match-cell">
									<div
										class="team-row"
										class:loser={loser === 'home'}
										class:tbd={!homeSeeded}
									>
										<span class="team-name">{displayTeamName(f.home_team)}</span>
										{#if homeHit}<span class="hit-mark">✓</span>{/if}
									</div>
									<div
										class="team-row"
										class:loser={loser === 'away'}
										class:tbd={!awaySeeded}
									>
										<span class="team-name">{displayTeamName(f.away_team)}</span>
										{#if awayHit}<span class="hit-mark">✓</span>{/if}
									</div>
								</div>
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- Page 3: Final -->
			<div class="min-w-full">
				<div class="flex flex-col items-center gap-4 py-2">
					<div class="section-label">Final</div>
					{#if finalF}
						{@const loser = koLoserSide(finalF.score)}
						{@const homeSeeded = !!finalF.home_team && !finalF.home_team.startsWith('slot:')}
						{@const awaySeeded = !!finalF.away_team && !finalF.away_team.startsWith('slot:')}
						{@const homeHit = homeSeeded && fPicks.has(finalF.home_team)}
						{@const awayHit = awaySeeded && fPicks.has(finalF.away_team)}
						<div class="match-cell match-cell--final w-full max-w-xs">
							<div
								class="team-row"
								class:loser={loser === 'home'}
								class:tbd={!homeSeeded}
							>
								<span class="team-name">{displayTeamName(finalF.home_team)}</span>
								{#if homeHit}<span class="hit-mark">✓</span>{/if}
							</div>
							<div
								class="team-row"
								class:loser={loser === 'away'}
								class:tbd={!awaySeeded}
							>
								<span class="team-name">{displayTeamName(finalF.away_team)}</span>
								{#if awayHit}<span class="hit-mark">✓</span>{/if}
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Footer nav -->
	<footer
		class="flex items-center justify-between mt-3
			text-[11px] font-mono uppercase tracking-[0.15em]"
	>
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10
				disabled:opacity-30 disabled:cursor-not-allowed"
			disabled={page === 0}
			on:click={goPrev}
		>
			← Prev
		</button>
		<span class="opacity-60">Page {page + 1} / {PAGE_COUNT}</span>
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10
				disabled:opacity-30 disabled:cursor-not-allowed"
			disabled={page === PAGE_COUNT - 1}
			on:click={goNext}
		>
			Next →
		</button>
	</footer>
</div>

<style>
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
		@apply text-primary bg-primary/20;
		font-weight: 700;
		opacity: 1;
	}

	.match-col {
		display: flex;
		flex-direction: column;
		justify-content: space-around;
		gap: 5px;
		min-height: 100%;
	}

	.match-cell {
		background: color-mix(in srgb, currentColor 5%, transparent);
		border: 1px solid color-mix(in srgb, currentColor 10%, transparent);
		border-radius: 5px;
		padding: 3px 6px;
		font-size: 11px;
		font-weight: 500;
	}

	.match-cell--final {
		@apply border-primary/40 bg-primary/10;
		padding: 5px 8px;
		font-size: 12px;
	}

	.team-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 4px;
		min-height: 18px;
		padding: 1px 0;
	}

	.team-row + .team-row {
		border-top: 1px solid color-mix(in srgb, currentColor 8%, transparent);
		margin-top: 1px;
		padding-top: 2px;
	}

	.team-name {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Eliminated side — greyed + struck through. Mirrors BracketChip/FixtureRowKo. */
	.loser .team-name {
		opacity: 0.35;
		text-decoration: line-through;
	}

	/* Unresolved slot — muted TBD text */
	.tbd .team-name {
		opacity: 0.45;
		font-style: italic;
	}

	/* ✓ marker — text-success (theme-aware; both premium-night and hybrid). */
	.hit-mark {
		@apply text-success;
		font-size: 10px;
		font-weight: 700;
		flex-shrink: 0;
	}

	.section-label {
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 10px;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		opacity: 0.6;
		margin-bottom: 6px;
	}
</style>

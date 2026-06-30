<!--
	ResultsBracket — read-only tournament wallchart for V4 Results page (v2.188.0).

	Chip design mirrors KnockoutBracket / BracketMatch exactly:
	  bg-base-200 surface · flags · bullet column · is-winner green wash ·
	  is-loser dim · gold FINAL strip.

	★ Per-side seeded check invariant (v2.184.x):
	  homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')
	★ third_place excluded (v2.164.0).
	★ koLoserSide priority: pens → ET → regulation (v2.185.1).
-->
<script lang="ts">
	import type { BracketPrediction, Fixture } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import { bracketPicksForRound, fixtureKoHits, isRoundLineupSeeded } from '$lib/utils/koPoints';
	import { koLoserSide } from '$lib/utils/matchDetailV4';
	import { displayTeamName } from '$lib/utils/teamName';
	import { matchNumberOf } from '$lib/utils/bracketGeometry';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

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
	$: finalF =
		fixtures.find((f) => f.stage === 'final' && matchNumberOf(f, fixtures) === 104) ??
		fixtures.find((f) => f.stage === 'final') ??
		null;

	// ── L / R halves ─────────────────────────────────────────────────────────
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

	$: adv = rules?.advancement ?? ({} as Record<string, number>);

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

	function goPrev() { if (page > 0) page -= 1; }
	function goNext() { if (page < PAGE_COUNT - 1) page += 1; }

	let touchStartX: number | null = null;
	function onTouchStart(e: TouchEvent) { touchStartX = e.touches[0]?.clientX ?? null; }
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
     ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="hidden lg:block bg-base-100 text-base-content rounded-2xl
		p-8 shadow-2xl border border-base-content/15 mt-3
		relative left-1/2 -translate-x-1/2
		w-[calc(100vw-2rem-12rem)] max-w-[1800px]"
>
	<!-- Header: title + legend -->
	<header class="flex items-center justify-between mb-4">
		<h2 class="font-display text-xl tracking-wide leading-none">
			KNOCKOUT <span class="text-primary">BRACKET</span>
		</h2>
		<div class="flex items-center gap-5 text-[10px] font-mono uppercase tracking-[0.16em] opacity-70">
			<span class="flex items-center gap-1.5">
				<span class="winner-sample"></span>Advanced
			</span>
			<span class="flex items-center gap-1.5">
				<span class="pick-sample">✓</span>Your pick
			</span>
			{#if !bracketPrediction}
				<span class="opacity-60 italic normal-case tracking-normal">No bracket picks submitted</span>
			{/if}
		</div>
	</header>

	<hr class="border-base-content/15 mb-5" />

	<!-- 9-column wallchart -->
	<div
		class="grid gap-x-5 gap-y-3 items-stretch"
		style="grid-template-columns: repeat(4, minmax(0, 1.1fr)) minmax(0, 1.5fr) repeat(4, minmax(0, 1.1fr));"
	>
		<!-- Column headers — exact same classes as KnockoutBracket -->
		<div class="col-label">R32 · L</div>
		<div class="col-label">R16 · L</div>
		<div class="col-label">QF · L</div>
		<div class="col-label">SF · L</div>
		<div class="col-label col-label--final">FINAL</div>
		<div class="col-label">SF · R</div>
		<div class="col-label">QF · R</div>
		<div class="col-label">R16 · R</div>
		<div class="col-label">R32 · R</div>

		<!-- R32 Left -->
		<div class="match-col">
			{#each r32L as f (f.id)}
				{@const loser = koLoserSide(f.score)}
				{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
				{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
				{@const homeHit = homeSeeded && r32Picks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && r32Picks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row"
						class:is-winner={loser === 'away'}
						class:is-loser={loser === 'home'}
						class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row"
						class:is-winner={loser === 'home'}
						class:is-loser={loser === 'away'}
						class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && r16Picks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && r16Picks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && qfPicks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && qfPicks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && sfPicks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && sfPicks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && fPicks.has(finalF.home_team ?? '')}
				{@const awayHit = awaySeeded && fPicks.has(finalF.away_team ?? '')}
				<div class="bracket-chip bracket-chip--final border border-primary/80 bg-base-200">
					<div class="final-strip">Final</div>
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(finalF.home_team ?? '')}
							<img src={getFlagUrl(finalF.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(finalF.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(finalF.away_team ?? '')}
							<img src={getFlagUrl(finalF.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(finalF.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && sfPicks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && sfPicks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && qfPicks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && qfPicks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && r16Picks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && r16Picks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
				{@const homeHit = homeSeeded && r32Picks.has(f.home_team ?? '')}
				{@const awayHit = awaySeeded && r32Picks.has(f.away_team ?? '')}
				<div class="bracket-chip border border-base-content/15 bg-base-200">
					<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
						<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
						{#if homeSeeded && hasFlag(f.home_team ?? '')}
							<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
					</div>
					<div class="border-t border-base-content/15" aria-hidden="true"></div>
					<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
						<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
						{#if awaySeeded && hasFlag(f.away_team ?? '')}
							<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
						{:else}<span class="flag flag-ph"></span>{/if}
						<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
					</div>
				</div>
			{/each}
		</div>
	</div>

	<!-- Points summary strip -->
	{#if knockoutScoringEnabled && (r32Seeded || r16Seeded || qfSeeded || sfSeeded || fSeeded)}
		<div
			class="mt-5 pt-4 border-t border-base-content/10
				flex flex-wrap items-center justify-center gap-x-8 gap-y-1
				text-[10px] font-mono uppercase tracking-[0.15em] text-base-content/60"
		>
			{#if r32Seeded}<span><span class="text-success">✓</span> R32 · {r32Hits}/{r32All.length} × {adv['round_of_32'] ?? '?'}pts</span>{/if}
			{#if r16Seeded}<span><span class="text-success">✓</span> R16 · {r16Hits}/{r16All.length} × {adv['round_of_16'] ?? '?'}pts</span>{/if}
			{#if qfSeeded}<span><span class="text-success">✓</span> QF · {qfHits}/{qfAll.length} × {adv['quarter_final'] ?? '?'}pts</span>{/if}
			{#if sfSeeded}<span><span class="text-success">✓</span> SF · {sfHits}/{sfAll.length} × {adv['semi_final'] ?? '?'}pts</span>{/if}
			{#if fSeeded}<span><span class="text-success">✓</span> F · {fHits}/1 × {adv['final'] ?? '?'}pts</span>{/if}
		</div>
	{/if}
</div>

<!-- ═══════════════════════════════════════════════════════════════════════
     MOBILE CAROUSEL (< lg)
     ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="lg:hidden bg-base-100 text-base-content rounded-2xl
		p-4 shadow-2xl border border-base-content/15 mt-3"
>
	<header class="flex items-center justify-between mb-3 gap-3">
		<h2 class="font-display text-sm tracking-wide leading-none">
			KNOCKOUT <span class="text-primary">BRACKET</span>
		</h2>
		<div class="flex gap-1.5">
			{#each Array(PAGE_COUNT) as _, i}
				<button
					type="button"
					class="w-1.5 h-1.5 rounded-full transition-colors
						{page === i ? 'bg-primary' : 'bg-base-content/30'}"
					aria-label="Go to page {i + 1}"
					on:click={() => (page = i)}
				></button>
			{/each}
		</div>
	</header>

	<div class="rounded bg-base-content/10 px-3 py-1.5 mb-3 text-center text-[11px] font-mono uppercase tracking-[0.2em]">
		{PAGE_LABELS[page]}
	</div>

	<div
		class="overflow-hidden"
		role="region"
		aria-roledescription="carousel"
		aria-label="Bracket pages"
		on:touchstart={onTouchStart}
		on:touchend={onTouchEnd}
	>
		<div class="flex transition-transform duration-300 ease-out" style="transform: translateX(-{page * 100}%);">

			<!-- Page 0: R32 (8L + 8R) -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						{#each r32L as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r32Picks.has(f.home_team ?? '')}
							{@const awayHit = awaySeeded && r32Picks.has(f.away_team ?? '')}
							<div class="bracket-chip border border-base-content/15 bg-base-200">
								<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
									<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
									{#if homeSeeded && hasFlag(f.home_team ?? '')}
										<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
								</div>
								<div class="border-t border-base-content/15" aria-hidden="true"></div>
								<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
									<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
									{#if awaySeeded && hasFlag(f.away_team ?? '')}
										<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
								</div>
							</div>
						{/each}
					</div>
					<div class="space-y-1.5">
						{#each r32R as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r32Picks.has(f.home_team ?? '')}
							{@const awayHit = awaySeeded && r32Picks.has(f.away_team ?? '')}
							<div class="bracket-chip border border-base-content/15 bg-base-200">
								<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
									<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
									{#if homeSeeded && hasFlag(f.home_team ?? '')}
										<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
								</div>
								<div class="border-t border-base-content/15" aria-hidden="true"></div>
								<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
									<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
									{#if awaySeeded && hasFlag(f.away_team ?? '')}
										<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 1: R16 (4L + 4R) -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-2">
						{#each r16L as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r16Picks.has(f.home_team ?? '')}
							{@const awayHit = awaySeeded && r16Picks.has(f.away_team ?? '')}
							<div class="bracket-chip border border-base-content/15 bg-base-200">
								<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
									<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
									{#if homeSeeded && hasFlag(f.home_team ?? '')}
										<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
								</div>
								<div class="border-t border-base-content/15" aria-hidden="true"></div>
								<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
									<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
									{#if awaySeeded && hasFlag(f.away_team ?? '')}
										<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
								</div>
							</div>
						{/each}
					</div>
					<div class="space-y-2">
						{#each r16R as f (f.id)}
							{@const loser = koLoserSide(f.score)}
							{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
							{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
							{@const homeHit = homeSeeded && r16Picks.has(f.home_team ?? '')}
							{@const awayHit = awaySeeded && r16Picks.has(f.away_team ?? '')}
							<div class="bracket-chip border border-base-content/15 bg-base-200">
								<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
									<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
									{#if homeSeeded && hasFlag(f.home_team ?? '')}
										<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
								</div>
								<div class="border-t border-base-content/15" aria-hidden="true"></div>
								<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
									<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
									{#if awaySeeded && hasFlag(f.away_team ?? '')}
										<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
									{:else}<span class="flag flag-ph"></span>{/if}
									<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 2: QF + SF -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-3">
					<div>
						<div class="section-label">QF</div>
						<div class="space-y-2">
							{#each qfAll as f (f.id)}
								{@const loser = koLoserSide(f.score)}
								{@const homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:')}
								{@const awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:')}
								{@const homeHit = homeSeeded && qfPicks.has(f.home_team ?? '')}
								{@const awayHit = awaySeeded && qfPicks.has(f.away_team ?? '')}
								<div class="bracket-chip border border-base-content/15 bg-base-200">
									<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
										<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
										{#if homeSeeded && hasFlag(f.home_team ?? '')}
											<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
										{:else}<span class="flag flag-ph"></span>{/if}
										<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
									</div>
									<div class="border-t border-base-content/15" aria-hidden="true"></div>
									<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
										<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
										{#if awaySeeded && hasFlag(f.away_team ?? '')}
											<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
										{:else}<span class="flag flag-ph"></span>{/if}
										<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
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
								{@const homeHit = homeSeeded && sfPicks.has(f.home_team ?? '')}
								{@const awayHit = awaySeeded && sfPicks.has(f.away_team ?? '')}
								<div class="bracket-chip border border-base-content/15 bg-base-200">
									<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
										<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
										{#if homeSeeded && hasFlag(f.home_team ?? '')}
											<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
										{:else}<span class="flag flag-ph"></span>{/if}
										<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
									</div>
									<div class="border-t border-base-content/15" aria-hidden="true"></div>
									<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
										<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
										{#if awaySeeded && hasFlag(f.away_team ?? '')}
											<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
										{:else}<span class="flag flag-ph"></span>{/if}
										<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
									</div>
								</div>
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- Page 3: Final -->
			<div class="min-w-full px-0.5">
				<div class="flex flex-col items-center gap-4 py-2">
					{#if finalF}
						{@const loser = koLoserSide(finalF.score)}
						{@const homeSeeded = !!finalF.home_team && !finalF.home_team.startsWith('slot:')}
						{@const awaySeeded = !!finalF.away_team && !finalF.away_team.startsWith('slot:')}
						{@const homeHit = homeSeeded && fPicks.has(finalF.home_team ?? '')}
						{@const awayHit = awaySeeded && fPicks.has(finalF.away_team ?? '')}
						<div class="bracket-chip bracket-chip--final border border-primary/80 bg-base-200 w-full max-w-xs">
							<div class="final-strip">Final</div>
							<div class="team-row" class:is-winner={loser === 'away'} class:is-loser={loser === 'home'} class:tbd={!homeSeeded}>
								<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
								{#if homeSeeded && hasFlag(finalF.home_team ?? '')}
									<img src={getFlagUrl(finalF.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
								{:else}<span class="flag flag-ph"></span>{/if}
								<span class="tname">{homeSeeded ? displayTeamName(finalF.home_team).toUpperCase() : 'TBD'}</span>
							</div>
							<div class="border-t border-base-content/15" aria-hidden="true"></div>
							<div class="team-row" class:is-winner={loser === 'home'} class:is-loser={loser === 'away'} class:tbd={!awaySeeded}>
								<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
								{#if awaySeeded && hasFlag(finalF.away_team ?? '')}
									<img src={getFlagUrl(finalF.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
								{:else}<span class="flag flag-ph"></span>{/if}
								<span class="tname">{awaySeeded ? displayTeamName(finalF.away_team).toUpperCase() : 'TBD'}</span>
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<footer class="flex items-center justify-between mt-3 text-[11px] font-mono uppercase tracking-[0.15em]">
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
			disabled={page === 0}
			on:click={goPrev}
		>← Prev</button>
		<span class="opacity-60">Page {page + 1} / {PAGE_COUNT}</span>
		<button
			type="button"
			class="px-2 py-1 rounded hover:bg-base-content/10 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
			disabled={page === PAGE_COUNT - 1}
			on:click={goNext}
		>Next →</button>
	</footer>
</div>

<style>
	/* ── Column labels — exact match to KnockoutBracket ───────────────────── */
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
		gap: 6px;
		min-height: 100%;
	}

	/* ── Bracket chip — layout only; surface tokens applied via Tailwind classes
	       on the element so DaisyUI's rgb-channel variables resolve correctly ── */
	.bracket-chip {
		position: relative;
		overflow: hidden;
		border-radius: 6px;
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
	}

	.bracket-chip--final {
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.25);
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

	/* Advancing team: literal green wash — same value as BracketMatch */
	.team-row.is-winner {
		font-weight: 700;
		background: rgb(34 197 94 / 0.28);
	}

	/* Eliminated team: dim only (no line-through — matches BracketMatch) */
	.team-row.is-loser {
		opacity: 0.45;
	}

	/* Unresolved slot */
	.team-row.tbd {
		opacity: 0.55;
	}

	/* ── Bullet column (reserved width so name text aligns) ───────────────── */
	.bullet {
		width: 0.6rem;
		flex-shrink: 0;
		text-align: center;
		font-size: 0.7rem;
		font-weight: 900;
		line-height: 1;
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

	/* ── Final chip: bigger rows (mirrors BracketMatch .bracket-chip-final) ── */
	.bracket-chip--final .team-row {
		font-size: 0.95rem;
		padding: 0.5rem 0.75rem;
	}

	.bracket-chip--final .flag {
		width: 20px;
		height: 13px;
	}

	/* ── Mobile section label ──────────────────────────────────────────────── */
	.section-label {
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 10px;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		opacity: 0.6;
		margin-bottom: 6px;
	}

	/* ── Legend samples ────────────────────────────────────────────────────── */
	.winner-sample {
		display: inline-block;
		width: 1rem;
		height: 0.6rem;
		border-radius: 2px;
		background: rgb(34 197 94 / 0.5);
	}

	.pick-sample {
		color: hsl(var(--su));
		font-weight: 900;
	}
</style>

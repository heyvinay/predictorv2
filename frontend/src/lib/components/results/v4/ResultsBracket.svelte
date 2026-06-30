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
	import { buildMatchNumberIndex } from '$lib/utils/bracketGeometry';
	import { SEMI_FINALS, QUARTER_FINALS, ROUND_OF_16 } from '$lib/config/bracketConfig';
	import WallchartChip from '$lib/components/results/v4/WallchartChip.svelte';

	export let fixtures: Fixture[];
	export let bracketPrediction: BracketPrediction | null;
	export let rules: ScoringRules | null;
	export let knockoutScoringEnabled: boolean;

	// ── Derive wallchart columns by walking the source graph ─────────────────
	// FIFA match numbers are chronological, NOT visual top-to-bottom order.
	// We walk SF → QF → R16 → R32 via homeSource/awaySource to get the
	// correct wallchart sequence — the same approach BracketQuadrant uses.
	interface BracketHalf {
		r32: Fixture[];
		r16: Fixture[];
		qf: Fixture[];
		sf: Fixture | null;
	}

	function deriveHalf(sfMatchNum: number, idx: Map<number, Fixture>): BracketHalf {
		const sfCfg = SEMI_FINALS.find((m) => m.matchNumber === sfMatchNum);
		if (!sfCfg) return { r32: [], r16: [], qf: [], sf: null };

		const winnerNums = (src: { type: string; matchNumber?: number }[]) =>
			src.flatMap((s) => (s.type === 'winner' && s.matchNumber !== undefined ? [s.matchNumber] : []));

		const qfNums = winnerNums([sfCfg.homeSource, sfCfg.awaySource]);
		const r16Nums: number[] = [];
		const r32Nums: number[] = [];

		for (const qfNum of qfNums) {
			const qfCfg = QUARTER_FINALS.find((m) => m.matchNumber === qfNum);
			if (!qfCfg) continue;
			const r16Pair = winnerNums([qfCfg.homeSource, qfCfg.awaySource]);
			for (const r16Num of r16Pair) {
				r16Nums.push(r16Num);
				const r16Cfg = ROUND_OF_16.find((m) => m.matchNumber === r16Num);
				if (!r16Cfg) continue;
				r32Nums.push(...winnerNums([r16Cfg.homeSource, r16Cfg.awaySource]));
			}
		}

		const fx = (n: number) => idx.get(n) ?? null;
		return {
			r32: r32Nums.map(fx).filter((f): f is Fixture => f !== null),
			r16: r16Nums.map(fx).filter((f): f is Fixture => f !== null),
			qf: qfNums.map(fx).filter((f): f is Fixture => f !== null),
			sf: fx(sfMatchNum),
		};
	}

	$: matchIdx = buildMatchNumberIndex(fixtures);
	$: leftHalf  = deriveHalf(101, matchIdx);  // SF M101 → QF M97/98 → left columns
	$: rightHalf = deriveHalf(102, matchIdx);  // SF M102 → QF M99/100 → right columns

	$: r32L = leftHalf.r32;
	$: r16L = leftHalf.r16;
	$: qfL  = leftHalf.qf;
	$: sfL  = leftHalf.sf ? [leftHalf.sf] : [];

	$: r32R = rightHalf.r32;
	$: r16R = rightHalf.r16;
	$: qfR  = rightHalf.qf;
	$: sfR  = rightHalf.sf ? [rightHalf.sf] : [];

	$: finalF = matchIdx.get(104) ?? null;

	// ── All fixtures per stage for hits/seeded checks ─────────────────────────
	$: r32All = [...r32L, ...r32R];
	$: r16All = [...r16L, ...r16R];
	$: qfAll  = [...qfL, ...qfR];
	$: sfAll  = [...sfL, ...sfR];

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
				<WallchartChip fixture={f} picks={r32Picks} />
			{/each}
		</div>

		<!-- R16 Left -->
		<div class="match-col">
			{#each r16L as f (f.id)}
				<WallchartChip fixture={f} picks={r16Picks} />
			{/each}
		</div>

		<!-- QF Left -->
		<div class="match-col">
			{#each qfL as f (f.id)}
				<WallchartChip fixture={f} picks={qfPicks} />
			{/each}
		</div>

		<!-- SF Left -->
		<div class="match-col">
			{#each sfL as f (f.id)}
				<WallchartChip fixture={f} picks={sfPicks} />
			{/each}
		</div>

		<!-- Final (centre, vertically centred) -->
		<div class="match-col justify-center">
			{#if finalF}
				<WallchartChip fixture={finalF} picks={fPicks} isFinal={true} />
			{/if}
		</div>

		<!-- SF Right -->
		<div class="match-col">
			{#each sfR as f (f.id)}
				<WallchartChip fixture={f} picks={sfPicks} />
			{/each}
		</div>

		<!-- QF Right -->
		<div class="match-col">
			{#each qfR as f (f.id)}
				<WallchartChip fixture={f} picks={qfPicks} />
			{/each}
		</div>

		<!-- R16 Right -->
		<div class="match-col">
			{#each r16R as f (f.id)}
				<WallchartChip fixture={f} picks={r16Picks} />
			{/each}
		</div>

		<!-- R32 Right -->
		<div class="match-col">
			{#each r32R as f (f.id)}
				<WallchartChip fixture={f} picks={r32Picks} />
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
							<WallchartChip fixture={f} picks={r32Picks} />
						{/each}
					</div>
					<div class="space-y-1.5">
						{#each r32R as f (f.id)}
							<WallchartChip fixture={f} picks={r32Picks} />
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 1: R16 (4L + 4R) -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-2">
						{#each r16L as f (f.id)}
							<WallchartChip fixture={f} picks={r16Picks} />
						{/each}
					</div>
					<div class="space-y-2">
						{#each r16R as f (f.id)}
							<WallchartChip fixture={f} picks={r16Picks} />
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
								<WallchartChip fixture={f} picks={qfPicks} />
							{/each}
						</div>
					</div>
					<div>
						<div class="section-label">SF</div>
						<div class="space-y-2">
							{#each sfAll as f (f.id)}
								<WallchartChip fixture={f} picks={sfPicks} />
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- Page 3: Final -->
			<div class="min-w-full px-0.5">
				<div class="flex flex-col items-center gap-4 py-2">
					{#if finalF}
						<div class="w-full max-w-xs">
							<WallchartChip fixture={finalF} picks={fPicks} isFinal={true} />
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

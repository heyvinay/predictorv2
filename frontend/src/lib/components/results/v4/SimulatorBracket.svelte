<!--
	SimulatorBracket — interactive knockout wallchart for the what-if
	bracket simulator (v2.194.x).

	Column-derivation (`deriveHalf`) is copy-adapted from ResultsBracket —
	same FIFA match-number walk (SF → QF → R16 → R32 via homeSource /
	awaySource) so the two bracket layouts stay pixel-compatible. This
	component swaps WallchartChip (read-only, navigates to Match Detail)
	for SimulatorChip (clickable, dispatches `pick` up).

	Desktop: identical 9-column grid to ResultsBracket. Mobile: the same
	4-page swipe carousel, simplified only in that pages read straight off
	the resolved-scenario maps rather than needing separate hits/hasPens
	bookkeeping (the simulator doesn't score match points).
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { Fixture } from '$types';
	import type { ResolvedScenario } from '$lib/types/simulator';
	import { buildMatchNumberIndex } from '$lib/utils/bracketGeometry';
	import { SEMI_FINALS, QUARTER_FINALS, ROUND_OF_16 } from '$lib/config/bracketConfig';
	import SimulatorChip from '$lib/components/results/v4/SimulatorChip.svelte';

	export let fixtures: Fixture[];
	export let resolved: ResolvedScenario;
	/** Team names the signed-in user's own bracket picked to reach each
	 *  round, keyed by FIFA match number — used only for the "matches
	 *  your pick" badge inside each chip. */
	export let myPicksByMatch: Map<number, string>;

	const dispatch = createEventDispatcher<{ pick: { matchNumber: number; team: string } }>();

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
			sf: fx(sfMatchNum)
		};
	}

	$: matchIdx = buildMatchNumberIndex(fixtures);
	$: leftHalf = deriveHalf(101, matchIdx);
	$: rightHalf = deriveHalf(102, matchIdx);

	$: r32L = leftHalf.r32;
	$: r16L = leftHalf.r16;
	$: qfL = leftHalf.qf;
	$: sfL = leftHalf.sf ? [leftHalf.sf] : [];

	$: r32R = rightHalf.r32;
	$: r16R = rightHalf.r16;
	$: qfR = rightHalf.qf;
	$: sfR = rightHalf.sf ? [rightHalf.sf] : [];

	$: finalF = matchIdx.get(104) ?? null;

	// Reverse index (fixture id -> FIFA match number) — rebuilt alongside
	// matchIdx so matchNumberOf is O(1) per chip instead of re-scanning the
	// whole map for every fixture on every render.
	$: fixtureIdToMatchNumber = (() => {
		const rev = new Map<string, number>();
		for (const [num, f] of matchIdx) rev.set(f.id, num);
		return rev;
	})();

	function matchNumberOf(fixture: Fixture): number | null {
		return fixtureIdToMatchNumber.get(fixture.id) ?? null;
	}

	function resolvedOf(matchNumber: number | null) {
		if (matchNumber === null) return { home: null, away: null, winner: null };
		return resolved.matches.get(matchNumber) ?? { home: null, away: null, winner: null };
	}

	function isRealFixture(fixture: Fixture): boolean {
		return fixture.status === 'finished';
	}

	function myPickFor(matchNumber: number | null): string | null {
		if (matchNumber === null) return null;
		return myPicksByMatch.get(matchNumber) ?? null;
	}

	function forwardPick(e: CustomEvent<{ matchNumber: number; team: string }>) {
		dispatch('pick', e.detail);
	}

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
     ═══════════════════════════════════════════════════════════════════════ -->
<div
	class="hidden lg:grid gap-x-5 gap-y-3 items-stretch"
	style="grid-template-columns: repeat(4, minmax(0, 1.1fr)) minmax(0, 1.5fr) repeat(4, minmax(0, 1.1fr));"
>
	<div class="col-label">R32 · L</div>
	<div class="col-label">R16 · L</div>
	<div class="col-label">QF · L</div>
	<div class="col-label">SF · L</div>
	<div class="col-label col-label--final">FINAL</div>
	<div class="col-label">SF · R</div>
	<div class="col-label">QF · R</div>
	<div class="col-label">R16 · R</div>
	<div class="col-label">R32 · R</div>

	<div class="match-col">
		{#each r32L as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each r16L as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each qfL as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each sfL as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col justify-center">
		{#if finalF}
			{@const num = matchNumberOf(finalF)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(finalF)}
				myPickWinner={myPickFor(num)}
				isFinal={true}
				on:pick={forwardPick}
			/>
		{/if}
	</div>

	<div class="match-col">
		{#each sfR as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each qfR as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each r16R as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>

	<div class="match-col">
		{#each r32R as f (f.id)}
			{@const num = matchNumberOf(f)}
			<SimulatorChip
				matchNumber={num ?? 0}
				resolved={resolvedOf(num)}
				isReal={isRealFixture(f)}
				myPickWinner={myPickFor(num)}
				on:pick={forwardPick}
			/>
		{/each}
	</div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════════
     MOBILE CAROUSEL (< lg)
     ═══════════════════════════════════════════════════════════════════════ -->
<div class="lg:hidden">
	<div class="flex items-center justify-between mb-3 gap-3">
		<div class="rounded bg-base-content/10 px-3 py-1.5 text-center text-[11px] font-mono uppercase tracking-[0.2em] flex-1">
			{PAGE_LABELS[page]}
		</div>
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
			<!-- Page 0: R32 -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						{#each r32L as f (f.id)}
							{@const num = matchNumberOf(f)}
							<SimulatorChip
								matchNumber={num ?? 0}
								resolved={resolvedOf(num)}
								isReal={isRealFixture(f)}
								myPickWinner={myPickFor(num)}
								on:pick={forwardPick}
							/>
						{/each}
					</div>
					<div class="space-y-1.5">
						{#each r32R as f (f.id)}
							{@const num = matchNumberOf(f)}
							<SimulatorChip
								matchNumber={num ?? 0}
								resolved={resolvedOf(num)}
								isReal={isRealFixture(f)}
								myPickWinner={myPickFor(num)}
								on:pick={forwardPick}
							/>
						{/each}
					</div>
				</div>
			</div>

			<!-- Page 1: R16 -->
			<div class="min-w-full px-0.5">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-2">
						{#each r16L as f (f.id)}
							{@const num = matchNumberOf(f)}
							<SimulatorChip
								matchNumber={num ?? 0}
								resolved={resolvedOf(num)}
								isReal={isRealFixture(f)}
								myPickWinner={myPickFor(num)}
								on:pick={forwardPick}
							/>
						{/each}
					</div>
					<div class="space-y-2">
						{#each r16R as f (f.id)}
							{@const num = matchNumberOf(f)}
							<SimulatorChip
								matchNumber={num ?? 0}
								resolved={resolvedOf(num)}
								isReal={isRealFixture(f)}
								myPickWinner={myPickFor(num)}
								on:pick={forwardPick}
							/>
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
							{#each [...qfL, ...qfR] as f (f.id)}
								{@const num = matchNumberOf(f)}
								<SimulatorChip
									matchNumber={num ?? 0}
									resolved={resolvedOf(num)}
									isReal={isRealFixture(f)}
									myPickWinner={myPickFor(num)}
									on:pick={forwardPick}
								/>
							{/each}
						</div>
					</div>
					<div>
						<div class="section-label">SF</div>
						<div class="space-y-2">
							{#each [...sfL, ...sfR] as f (f.id)}
								{@const num = matchNumberOf(f)}
								<SimulatorChip
									matchNumber={num ?? 0}
									resolved={resolvedOf(num)}
									isReal={isRealFixture(f)}
									myPickWinner={myPickFor(num)}
									on:pick={forwardPick}
								/>
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- Page 3: Final -->
			<div class="min-w-full px-0.5">
				<div class="flex flex-col items-center gap-4 py-2">
					{#if finalF}
						{@const num = matchNumberOf(finalF)}
						<div class="w-full max-w-xs">
							<SimulatorChip
								matchNumber={num ?? 0}
								resolved={resolvedOf(num)}
								isReal={isRealFixture(finalF)}
								myPickWinner={myPickFor(num)}
								isFinal={true}
								on:pick={forwardPick}
							/>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<div class="flex items-center justify-between mt-3 text-[11px] font-mono uppercase tracking-[0.15em]">
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
	</div>
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
		gap: 6px;
		min-height: 100%;
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

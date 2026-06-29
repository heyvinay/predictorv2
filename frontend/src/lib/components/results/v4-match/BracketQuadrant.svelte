<script lang="ts">
	/** Bracket Quadrant — SVG tree of the LOCAL bracket neighborhood for a
	 *  knockout fixture (v2.184.x rebuild).
	 *
	 *  R32 case (the user's screenshot trigger): renders the actual FIFA
	 *  quadrant — 4 R32 matches that genuinely converge to the same QF —
	 *  derived from bracketConfig.ts via `bracketGeometry.ts`. The earlier
	 *  version grouped 4 consecutive R32s by kickoff, which doesn't match
	 *  FIFA's bracket fan-in (M73 + M76 don't share a QF — M76 belongs to
	 *  a different quadrant). With the new walker, M73 (SA-Can) correctly
	 *  pairs with M75 (Ned-Mar) in R16#A, and M74 + M77 in R16#B; both
	 *  R16s feed QF M97.
	 *
	 *  Once an upstream R32 finishes, the corresponding R16 fixture's
	 *  resolved team flows through automatically via the v2.184.x backend
	 *  ko_lineup_resolver — we just look up the fixture by FIFA match
	 *  number and render whatever team names are surfaced.
	 *
	 *  Non-R32 fixtures fall back to a linear list — proper neighborhood
	 *  rendering for R16/QF/SF/F can come later.
	 */
	import type { Fixture } from '$types';
	import { fixtures } from '$stores/fixtures';
	import { activeEntryId } from '$stores/entries';
	import { teamCode } from '$lib/utils/teamCodes';
	import {
		buildMatchNumberIndex,
		matchNumberOf,
		r32QuadrantFor
	} from '$lib/utils/bracketGeometry';

	export let fixture: Fixture;

	// Match-number index from the live fixtures store.
	$: byMatchNum = buildMatchNumberIndex($fixtures);
	$: currentMatchNum = matchNumberOf(fixture, $fixtures);
	$: quadrant = currentMatchNum !== null ? r32QuadrantFor(currentMatchNum) : null;
	$: isR32 = fixture.stage === 'round_of_32';

	// Per-fixture helpers — pull resolved team codes from the fixtures store.
	// A slot:* string flowing through teamCode() resolves to '?'; that's OK
	// for downstream cells where the team is genuinely TBD.
	function isResolved(s: string | null | undefined): boolean {
		return !!s && !s.startsWith('slot:');
	}

	function r32Cell(matchNum: number): { fixture: Fixture | null; home: string; away: string } {
		const f = byMatchNum.get(matchNum) ?? null;
		if (!f) return { fixture: null, home: '?', away: '?' };
		return {
			fixture: f,
			home: isResolved(f.home_team) ? teamCode(f.home_team) : 'TBD',
			away: isResolved(f.away_team) ? teamCode(f.away_team) : 'TBD'
		};
	}

	// Build the layout-ready data once we have a recognized quadrant.
	$: primaryR32A = quadrant ? r32Cell(quadrant.primaryR32[0]) : null;
	$: primaryR32B = quadrant ? r32Cell(quadrant.primaryR32[1]) : null;
	$: secondaryR32A = quadrant ? r32Cell(quadrant.secondaryR32[0]) : null;
	$: secondaryR32B = quadrant ? r32Cell(quadrant.secondaryR32[1]) : null;
	$: primaryR16Cell = quadrant ? r32Cell(quadrant.primaryR16) : null;
	$: secondaryR16Cell = quadrant ? r32Cell(quadrant.secondaryR16) : null;
	$: qfCell = quadrant ? r32Cell(quadrant.qf) : null;

	// Geometry — same dimensions as the prior version (the layout shape
	// hasn't changed, just the data it's bound to).
	const LAYOUT = {
		r32Box: { x: 6, w: 120, h: 34 },
		r32Ys: [10, 54, 118, 162],
		r16Box: { x: 150, w: 105, h: 34 },
		r16Ys: [32, 140],
		qfBox: { x: 277, w: 38, h: 80, y: 86 },
		viewBox: '0 0 326 210'
	};

	$: entryHref = $activeEntryId ? `/entries/${$activeEntryId}` : '/entries';

	// Non-R32 fallback: collect this stage's fixtures and show as a strip.
	$: stageSiblings = $fixtures
		.filter((f) => f.stage === fixture.stage)
		.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">Bracket position</span>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
			>quadrant</span
		>
	</div>

	{#if isR32 && quadrant && primaryR32A && primaryR32B && secondaryR32A && secondaryR32B && primaryR16Cell && secondaryR16Cell && qfCell}
		<svg viewBox={LAYOUT.viewBox} class="w-full" style="max-height: 220px;" role="img" aria-label="Local bracket position">
			<!-- Connector lines: R32 → R16 → QF, classic bracket-tree shape. -->
			<g stroke="currentColor" stroke-width="1" fill="none" opacity="0.3">
				<path d="M 126 27 H 138 V 49 H 150" />
				<path d="M 126 71 H 138 V 49 H 150" />
				<path d="M 126 135 H 138 V 157 H 150" />
				<path d="M 126 179 H 138 V 157 H 150" />
				<path d="M 255 49 H 266 V 126 H 277" />
				<path d="M 255 157 H 266 V 126 H 277" />
			</g>

			<!-- 4 R32 boxes: primary pair on top, secondary pair on bottom -->
			{#each [{ cell: primaryR32A, y: LAYOUT.r32Ys[0], num: quadrant.primaryR32[0] }, { cell: primaryR32B, y: LAYOUT.r32Ys[1], num: quadrant.primaryR32[1] }, { cell: secondaryR32A, y: LAYOUT.r32Ys[2], num: quadrant.secondaryR32[0] }, { cell: secondaryR32B, y: LAYOUT.r32Ys[3], num: quadrant.secondaryR32[1] }] as row}
				{@const isHere = row.cell.fixture?.id === fixture.id}
				<g>
					<rect
						x={LAYOUT.r32Box.x}
						y={row.y}
						width={LAYOUT.r32Box.w}
						height={LAYOUT.r32Box.h}
						rx="4"
						class={isHere
							? 'fill-primary/15 stroke-primary'
							: 'fill-base-300/20 stroke-base-300/50'}
						stroke-width={isHere ? 1.5 : 1}
					/>
					<text
						x={LAYOUT.r32Box.x + 6}
						y={row.y + 14}
						class="fill-current text-[10px] font-bold"
						class:text-primary={isHere}
						class:text-base-content={!isHere}
					>
						{row.cell.home}
					</text>
					<text
						x={LAYOUT.r32Box.x + 6}
						y={row.y + 28}
						class="fill-current text-[10px] font-bold"
						class:text-primary={isHere}
						class:text-base-content={!isHere}
					>
						{row.cell.away}
					</text>
					{#if isHere}
						<text
							x={LAYOUT.r32Box.x + LAYOUT.r32Box.w - 4}
							y={row.y + 14}
							text-anchor="end"
							class="fill-primary text-[8px] font-extrabold tracking-wider"
						>
							YOU
						</text>
					{/if}
				</g>
			{/each}

			<!-- 2 R16 boxes — show resolved team codes when available, M-number tag below -->
			{#each [{ cell: primaryR16Cell, y: LAYOUT.r16Ys[0], num: quadrant.primaryR16 }, { cell: secondaryR16Cell, y: LAYOUT.r16Ys[1], num: quadrant.secondaryR16 }] as r16}
				<g>
					<rect
						x={LAYOUT.r16Box.x}
						y={r16.y}
						width={LAYOUT.r16Box.w}
						height={LAYOUT.r16Box.h}
						rx="4"
						class="fill-base-300/15 stroke-base-300/45"
						stroke-width="1"
					/>
					<text x={LAYOUT.r16Box.x + 6} y={r16.y + 14} class="fill-current text-[9.5px] font-bold opacity-80">
						{r16.cell.home} <tspan class="opacity-55">vs</tspan> {r16.cell.away}
					</text>
					<text x={LAYOUT.r16Box.x + 6} y={r16.y + 27} class="fill-current text-[8.5px] opacity-45">
						R16 · M{r16.num}
					</text>
				</g>
			{/each}

			<!-- QF box — narrow column with M-number and resolved teams if any -->
			<g>
				<rect
					x={LAYOUT.qfBox.x}
					y={LAYOUT.qfBox.y}
					width={LAYOUT.qfBox.w}
					height={LAYOUT.qfBox.h}
					rx="4"
					class="fill-base-300/10 stroke-base-300/40"
					stroke-width="1"
				/>
				<text
					x={LAYOUT.qfBox.x + LAYOUT.qfBox.w / 2}
					y={LAYOUT.qfBox.y + 16}
					text-anchor="middle"
					class="fill-current text-[10px] font-extrabold opacity-65"
				>
					QF
				</text>
				<text
					x={LAYOUT.qfBox.x + LAYOUT.qfBox.w / 2}
					y={LAYOUT.qfBox.y + 30}
					text-anchor="middle"
					class="fill-current text-[8.5px] opacity-40"
				>
					M{quadrant.qf}
				</text>
				<text
					x={LAYOUT.qfBox.x + LAYOUT.qfBox.w / 2}
					y={LAYOUT.qfBox.y + 48}
					text-anchor="middle"
					class="fill-current text-[8.5px] opacity-55"
				>
					{qfCell.home}
				</text>
				<text
					x={LAYOUT.qfBox.x + LAYOUT.qfBox.w / 2}
					y={LAYOUT.qfBox.y + 62}
					text-anchor="middle"
					class="fill-current text-[8.5px] opacity-55"
				>
					{qfCell.away}
				</text>
			</g>
		</svg>

		<p class="mt-2 text-[10.5px] text-base-content/50">
			4 R32 matches converge into 1 quarter-final · resolved teams appear as upstream rounds finish.
		</p>
	{:else}
		<!-- Non-R32 stages: simple list of the stage's siblings. Proper
		     local neighborhood rendering for R16+ is a future polish. -->
		<div class="flex flex-col gap-2">
			{#each stageSiblings as sib}
				{@const isHere = sib.id === fixture.id}
				<div
					class="flex items-center justify-between rounded-btn border px-3 py-2 text-[12px] {isHere
						? 'border-primary/40 bg-primary/15 font-bold text-primary'
						: 'border-base-300/40 bg-base-300/15 text-base-content/70'}"
				>
					<span>
						{teamCode(sib.home_team)} vs {teamCode(sib.away_team)}
					</span>
					{#if isHere}
						<span class="text-[9.5px] font-extrabold tracking-wider">YOU</span>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<a
		href={entryHref}
		class="mt-3 flex items-center justify-between rounded-btn bg-base-300/20 px-3 py-2 text-[11.5px] text-base-content/65 transition hover:bg-base-300/35 hover:text-base-content"
	>
		<span>Open your bracket</span>
		<span class="font-mono text-[10px] opacity-60">→</span>
	</a>
</div>

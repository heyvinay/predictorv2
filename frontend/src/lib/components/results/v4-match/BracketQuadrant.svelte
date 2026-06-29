<script lang="ts">
	/** Bracket Quadrant — schematic SVG showing this fixture's local bracket
	 *  neighborhood (4 R32 matches → 2 R16 → 1 QF, classic tournament tree).
	 *
	 *  Why not the full bracket? The /entries/{id} page already renders the
	 *  full tournament wallchart via KnockoutBracket.svelte. This sidebar
	 *  widget's job is *orientation* — make it tangible where the current
	 *  fixture sits, then let the user escape to the full view via the
	 *  "Open your bracket →" link.
	 *
	 *  Fixture-to-matchNumber mapping isn't available in the DB (match_number
	 *  is NULL for all KO fixtures, verified 2026-06-28), so adjacency is
	 *  inferred from kickoff-sorted ordering within the same stage. For R32,
	 *  the 16 matches divide cleanly into 4 quadrants of 4 matches each.
	 *  This matches the FIFA bracket structure but isn't authoritative —
	 *  intentional v1 trade-off, documented in the wireframe.
	 */
	import type { Fixture } from '$types';
	import { fixtures } from '$stores/fixtures';
	import { activeEntryId } from '$stores/entries';
	import { teamCode } from '$lib/utils/teamCodes';

	export let fixture: Fixture;

	$: stage = fixture.stage;

	// Kickoff-sorted same-stage fixtures — index proxies for matchNumber.
	$: stageFixtures = $fixtures
		.filter((f) => f.stage === stage)
		.sort((a, b) => a.kickoff.localeCompare(b.kickoff));

	$: idx = stageFixtures.findIndex((f) => f.id === fixture.id);

	// Quadrant logic — for R32, group every 4 matches (4 quadrants × 4 matches).
	// For later stages, scope narrows naturally (R16 → halves of 4, QF → halves
	// of 2). For Final, just the one match.
	$: quadrantSize = stage === 'round_of_32' ? 4 : stage === 'round_of_16' ? 4 : stage === 'quarter_final' ? 2 : 1;
	$: quadrantIdx = idx >= 0 ? Math.floor(idx / quadrantSize) : 0;
	$: quadrantStart = quadrantIdx * quadrantSize;
	$: siblings = stageFixtures.slice(quadrantStart, quadrantStart + quadrantSize);

	// View geometry (R32 case): 4 boxes left → 2 boxes mid → 1 box right.
	// For other stages we render a simpler vertical strip.
	const R32_LAYOUT = {
		r32Box: { x: 6, w: 120, h: 34 },
		r32Ys: [10, 54, 118, 162],
		r16Box: { x: 150, w: 105, h: 34 },
		r16Ys: [32, 140],
		qfBox: { x: 277, w: 38, h: 80, y: 86 },
		viewBox: '0 0 326 210'
	};

	$: entryHref = $activeEntryId ? `/entries/${$activeEntryId}` : '/entries';
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">Bracket position</span>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
			>quadrant</span
		>
	</div>

	{#if stage === 'round_of_32' && siblings.length === 4}
		<!-- R32 quadrant tree: 4 → 2 → 1, classic bracket-tree shape -->
		<svg viewBox={R32_LAYOUT.viewBox} class="w-full" style="max-height: 220px;" role="img" aria-label="Local bracket position">
			<!-- Connector lines: each pair of R32s → one R16, both R16s → QF.
			     stroke-current ⇒ inherits theme text colour so light/dark both work. -->
			<g stroke="currentColor" stroke-width="1" fill="none" opacity="0.3">
				<!-- R32#1 (y top edge 10, h 34, mid 27) → R16#1 (mid 49) — bracket -->
				<path d="M 126 27 H 138 V 49 H 150" />
				<!-- R32#2 (mid 71) → R16#1 (mid 49) -->
				<path d="M 126 71 H 138 V 49 H 150" />
				<!-- R32#3 (mid 135) → R16#2 (mid 157) -->
				<path d="M 126 135 H 138 V 157 H 150" />
				<!-- R32#4 (mid 179) → R16#2 (mid 157) -->
				<path d="M 126 179 H 138 V 157 H 150" />
				<!-- R16#1 (mid 49) → QF (mid 126) -->
				<path d="M 255 49 H 266 V 126 H 277" />
				<!-- R16#2 (mid 157) → QF (mid 126) -->
				<path d="M 255 157 H 266 V 126 H 277" />
			</g>

			<!-- R32 boxes: 4 stacked left -->
			{#each siblings as sib, i}
				{@const y = R32_LAYOUT.r32Ys[i]}
				{@const isHere = sib.id === fixture.id}
				{@const homeCode = teamCode(sib.home_team)}
				{@const awayCode = teamCode(sib.away_team)}
				<g>
					<rect
						x={R32_LAYOUT.r32Box.x}
						{y}
						width={R32_LAYOUT.r32Box.w}
						height={R32_LAYOUT.r32Box.h}
						rx="4"
						class={isHere ? 'fill-primary/15 stroke-primary' : 'fill-base-300/20 stroke-base-300/50'}
						stroke-width={isHere ? 1.5 : 1}
					/>
					<text
						x={R32_LAYOUT.r32Box.x + 6}
						y={y + 14}
						class="fill-current text-[10px] font-bold"
						class:text-primary={isHere}
						class:text-base-content={!isHere}
					>
						{homeCode}
					</text>
					<text
						x={R32_LAYOUT.r32Box.x + 6}
						y={y + 28}
						class="fill-current text-[10px] font-bold"
						class:text-primary={isHere}
						class:text-base-content={!isHere}
					>
						{awayCode}
					</text>
					{#if isHere}
						<text
							x={R32_LAYOUT.r32Box.x + R32_LAYOUT.r32Box.w - 4}
							y={y + 14}
							text-anchor="end"
							class="fill-primary text-[8px] font-extrabold tracking-wider"
						>
							YOU
						</text>
					{/if}
				</g>
			{/each}

			<!-- R16 boxes: 2 in the middle column -->
			{#each R32_LAYOUT.r16Ys as y, i}
				<g>
					<rect
						x={R32_LAYOUT.r16Box.x}
						{y}
						width={R32_LAYOUT.r16Box.w}
						height={R32_LAYOUT.r16Box.h}
						rx="4"
						class="fill-base-300/15 stroke-base-300/45"
						stroke-width="1"
					/>
					<text
						x={R32_LAYOUT.r16Box.x + 6}
						y={y + 14}
						class="fill-current text-[9px] font-bold opacity-60"
					>
						R16 · M{i + 1}
					</text>
					<text
						x={R32_LAYOUT.r16Box.x + 6}
						y={y + 27}
						class="fill-current text-[9px] opacity-45"
					>
						TBD
					</text>
				</g>
			{/each}

			<!-- QF box (narrow, just a label column) -->
			<g>
				<rect
					x={R32_LAYOUT.qfBox.x}
					y={R32_LAYOUT.qfBox.y}
					width={R32_LAYOUT.qfBox.w}
					height={R32_LAYOUT.qfBox.h}
					rx="4"
					class="fill-base-300/10 stroke-base-300/40"
					stroke-width="1"
				/>
				<text
					x={R32_LAYOUT.qfBox.x + R32_LAYOUT.qfBox.w / 2}
					y={R32_LAYOUT.qfBox.y + R32_LAYOUT.qfBox.h / 2 - 2}
					text-anchor="middle"
					class="fill-current text-[10px] font-extrabold opacity-65"
				>
					QF
				</text>
				<text
					x={R32_LAYOUT.qfBox.x + R32_LAYOUT.qfBox.w / 2}
					y={R32_LAYOUT.qfBox.y + R32_LAYOUT.qfBox.h / 2 + 12}
					text-anchor="middle"
					class="fill-current text-[8px] opacity-40"
				>
					#{quadrantIdx + 1}
				</text>
			</g>
		</svg>

		<p class="mt-2 text-[10.5px] text-base-content/50">
			Quadrant #{quadrantIdx + 1} · 4 R32 matches converge to 1 quarter-final
		</p>
	{:else}
		<!-- Fallback for R16/QF/SF/F: linear path from current to trophy -->
		<div class="flex flex-col gap-2">
			{#each siblings as sib}
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
			<p class="mt-1 text-[10.5px] text-base-content/50">
				{siblings.length === 1
					? 'This match feeds the next round.'
					: 'Both matches in this section of the bracket.'}
			</p>
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

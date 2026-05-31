<script lang="ts">
	import type { CommunityPrediction, FixtureScore } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';

	export let predictions: CommunityPrediction[];
	export let actual: FixtureScore | null;
	export let homeTeam: string;
	export let awayTeam: string;
	export let userPrediction: { home_score: number; away_score: number } | null = null;

	// SVG dimensions
	const svgSize = 320;
	const pad = 44;
	const plotSize = svgSize - pad * 2; // 232

	// Compute grid max from data
	$: allScores = [
		...predictions.flatMap((p) => [p.home_score, p.away_score]),
		...(actual ? [actual.home_score, actual.away_score] : [])
	];
	$: maxScore = Math.max(4, Math.max(...allScores, 0) + 1);

	// Scale helpers
	$: cellSize = plotSize / maxScore;
	function toX(awayScore: number): number {
		return pad + awayScore * cellSize + cellSize / 2;
	}
	function toY(homeScore: number): number {
		return pad + (maxScore - homeScore) * cellSize - cellSize / 2;
	}

	// Prediction result type — matches the red/yellow/green from score cards
	type PredResult = 'exact' | 'outcome' | 'wrong' | null;

	function getPredResult(home: number, away: number): PredResult {
		if (!actual) return null;
		if (home === actual.home_score && away === actual.away_score) return 'exact';
		const predOutcome = home > away ? '1' : home < away ? '2' : 'X';
		if (predOutcome === actual.outcome) return 'outcome';
		return 'wrong';
	}

	// Group predictions by coordinate
	interface GroupedPrediction {
		home: number;
		away: number;
		count: number;
		names: string[];
		result: PredResult;
	}
	$: grouped = (() => {
		const map = new Map<string, GroupedPrediction>();
		for (const p of predictions) {
			const key = `${p.home_score},${p.away_score}`;
			const existing = map.get(key);
			if (existing) {
				existing.count++;
				existing.names.push(p.user_name);
			} else {
				map.set(key, {
					home: p.home_score,
					away: p.away_score,
					count: 1,
					names: [p.user_name],
					result: getPredResult(p.home_score, p.away_score),
				});
			}
		}
		return Array.from(map.values());
	})();

	// Set of predicted coordinates (to skip background dot at those positions)
	$: predictedKeys = new Set(grouped.map((g) => `${g.home},${g.away}`));

	// All possible grid coordinates
	$: gridDots = (() => {
		const dots: { home: number; away: number }[] = [];
		for (let h = 0; h < maxScore; h++) {
			for (let a = 0; a < maxScore; a++) {
				dots.push({ home: h, away: a });
			}
		}
		return dots;
	})();

	// Check if the actual result is a draw
	$: isDraw = actual ? actual.outcome === 'X' : false;

	// Zone shading polygon points
	// Home win zone: above the diagonal (home_score > away_score)
	// In SVG coords: top-left corner → grid along top → diagonal points → left edge
	$: homeWinPoly = (() => {
		// Corners of the plot area
		const topLeft = `${pad},${pad}`;
		const topRight = `${pad + plotSize},${pad}`;
		// Walk along the diagonal from top-right to bottom-left
		// The diagonal goes from (away=0,home=0) bottom-left to (away=max-1,home=max-1) top-right
		// In SVG: from toX(0),toY(0) to toX(maxScore-1),toY(maxScore-1)
		const diagTopRight = `${toX(maxScore - 1)},${toY(maxScore - 1)}`;
		const diagBottomLeft = `${toX(0)},${toY(0)}`;
		const bottomLeft = `${pad},${pad + plotSize}`;
		return `${topLeft} ${topRight} ${diagTopRight} ${diagBottomLeft} ${bottomLeft}`;
	})();

	$: awayWinPoly = (() => {
		const topRight = `${pad + plotSize},${pad}`;
		const bottomRight = `${pad + plotSize},${pad + plotSize}`;
		const bottomLeft = `${pad},${pad + plotSize}`;
		const diagTopRight = `${toX(maxScore - 1)},${toY(maxScore - 1)}`;
		const diagBottomLeft = `${toX(0)},${toY(0)}`;
		return `${diagTopRight} ${topRight} ${bottomRight} ${bottomLeft} ${diagBottomLeft}`;
	})();

	// Diagonal midpoint for DRAW label
	$: diagMidX = (toX(0) + toX(maxScore - 1)) / 2;
	$: diagMidY = (toY(0) + toY(maxScore - 1)) / 2;

	// Whether anyone predicted the exact score (to decide if we need standalone actual star)
	$: hasExactPrediction = grouped.some(g => g.result === 'exact');

	// Tooltip state
	let hoveredGroup: GroupedPrediction | null = null;
	let tooltipX = 0;
	let tooltipY = 0;

	function showTooltip(group: GroupedPrediction, event: MouseEvent | TouchEvent) {
		hoveredGroup = group;
		if (event instanceof MouseEvent) {
			tooltipX = event.offsetX;
			tooltipY = event.offsetY - 10;
		} else if (event.touches.length > 0) {
			const rect = (event.currentTarget as Element).closest('svg')?.getBoundingClientRect();
			if (rect) {
				tooltipX = event.touches[0].clientX - rect.left;
				tooltipY = event.touches[0].clientY - rect.top - 10;
			}
		}
	}

	function hideTooltip() {
		hoveredGroup = null;
	}

	// Star polygon points
	function starPoints(cx: number, cy: number, outerR: number, innerR: number, points: number): string {
		const coords: string[] = [];
		for (let i = 0; i < points * 2; i++) {
			const angle = (Math.PI / points) * i - Math.PI / 2;
			const r = i % 2 === 0 ? outerR : innerR;
			coords.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
		}
		return coords.join(' ');
	}

	// Tick values for axis labels
	$: ticks = Array.from({ length: maxScore }, (_, i) => i);

	// Base radius for grouped dots
	const baseRadius = 6;
	const emptyDotRadius = 2.5;
	const userRingPad = 4;

	// Compute the "YOU" ring position and radius based on the grouped dot at that coordinate
	$: userRing = (() => {
		if (!userPrediction) return null;
		const uh = userPrediction.home_score;
		const ua = userPrediction.away_score;
		const cx = toX(ua);
		const cy = toY(uh);
		const group = grouped.find(g => g.home === uh && g.away === ua);
		let ringR: number;
		if (group) {
			const dotR = Math.sqrt(group.count) * baseRadius;
			if (group.result === 'exact') {
				// Star outer radius
				ringR = Math.max(12, dotR + 4) + userRingPad;
			} else {
				ringR = dotR + userRingPad;
			}
		} else {
			// User's prediction isn't in the community list (shouldn't happen, but safe fallback)
			ringR = baseRadius + userRingPad;
		}
		return { cx, cy, r: ringR };
	})();
</script>

<div class="w-full max-w-sm sm:max-w-md lg:max-w-lg mx-auto relative" on:click={hideTooltip} role="presentation">
	<svg viewBox="0 0 {svgSize} {svgSize}" class="w-full h-auto" xmlns="http://www.w3.org/2000/svg">
		<!-- Zone shading: neutral slate fills (no green/red to avoid conflicting with result colors) -->
		<polygon
			points={homeWinPoly}
			fill="rgba(148, 163, 184, 0.06)"
		/>
		<polygon
			points={awayWinPoly}
			fill="rgba(148, 163, 184, 0.10)"
		/>

		<!-- Zone corner labels -->
		<text
			x={pad + 6}
			y={pad + 12}
			fill="rgba(148, 163, 184, 0.35)"
			font-size="7"
			font-weight="600"
			font-family="'Inter', sans-serif"
		>HOME</text>
		<text
			x={pad + plotSize - 6}
			y={pad + plotSize - 6}
			text-anchor="end"
			fill="rgba(148, 163, 184, 0.35)"
			font-size="7"
			font-weight="600"
			font-family="'Inter', sans-serif"
		>AWAY</text>

		<!-- Diagonal line (draw line) — neutral gray, emphasized when actual result is a draw -->
		<line
			x1={pad}
			y1={pad + plotSize}
			x2={pad + plotSize}
			y2={pad}
			class={isDraw ? 'stroke-base-content/30' : 'stroke-base-content/10'}
			stroke-width={isDraw ? 1.5 : 0.75}
			stroke-dasharray={isDraw ? '6 3' : '4 4'}
		/>

		<!-- Always-visible DRAW label along diagonal -->
		<text
			x={diagMidX}
			y={diagMidY - 5}
			text-anchor="middle"
			class={isDraw ? 'fill-base-content/40' : 'fill-base-content/20'}
			font-size="8"
			font-weight="600"
			font-family="'Inter', sans-serif"
			transform="rotate(-45, {diagMidX}, {diagMidY - 5})"
		>DRAW</text>

		<!-- Background dots: every possible scoreline -->
		{#each gridDots as dot}
			{@const hasPrediction = predictedKeys.has(`${dot.home},${dot.away}`)}
			{@const isActual = actual && dot.home === actual.home_score && dot.away === actual.away_score}
			{#if !hasPrediction && !isActual}
				<circle
					cx={toX(dot.away)}
					cy={toY(dot.home)}
					r={emptyDotRadius}
					class="fill-base-content/15"
				/>
			{/if}
		{/each}

		<!-- Axis labels: ticks -->
		{#each ticks as t}
			<!-- X-axis (away score) -->
			<text
				x={toX(t)}
				y={pad + plotSize + 18}
				text-anchor="middle"
				class="fill-base-content/40"
				font-size="11"
				font-family="'JetBrains Mono', monospace"
			>{t}</text>
			<!-- Y-axis (home score) -->
			<text
				x={pad - 14}
				y={toY(t) + 4}
				text-anchor="middle"
				class="fill-base-content/40"
				font-size="11"
				font-family="'JetBrains Mono', monospace"
			>{t}</text>
		{/each}

		<!-- Axis labels: centered flags -->
		<!-- Home team flag: centered along the Y-axis (left side) -->
		{#if hasFlag(homeTeam)}
			<image
				href={getFlagUrl(homeTeam, 'md')}
				x={0}
				y={pad + plotSize / 2 - 8}
				width="24"
				height="16"
				style="border-radius: 2px;"
			/>
		{:else}
			<text
				x={12}
				y={pad + plotSize / 2 + 4}
				text-anchor="middle"
				class="fill-base-content/60"
				font-size="11"
				font-weight="700"
			>{displayTeamName(homeTeam)}</text>
		{/if}
		<!-- Away team flag: centered below the plot (X-axis) -->
		{#if hasFlag(awayTeam)}
			<image
				href={getFlagUrl(awayTeam, 'md')}
				x={pad + plotSize / 2 - 12}
				y={svgSize - 18}
				width="24"
				height="16"
				style="border-radius: 2px;"
			/>
		{:else}
			<text
				x={pad + plotSize / 2}
				y={svgSize - 4}
				text-anchor="middle"
				class="fill-base-content/60"
				font-size="11"
				font-weight="700"
			>{displayTeamName(awayTeam)}</text>
		{/if}

		<!-- Prediction dots / stars -->
		{#each grouped as group}
			{@const cx = toX(group.away)}
			{@const cy = toY(group.home)}
			{@const r = Math.sqrt(group.count) * baseRadius}

			{#if group.result === 'exact'}
				<!-- Exact: green star -->
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<polygon
					points={starPoints(cx, cy, Math.max(12, r + 4), Math.max(5, (r + 4) * 0.45), 5)}
					class="fill-success"
					stroke="rgba(0,0,0,0.3)"
					stroke-width="0.5"
					on:mouseenter={(e) => showTooltip(group, e)}
					on:mouseleave={hideTooltip}
					on:touchstart|preventDefault={(e) => showTooltip(group, e)}
					style="cursor: pointer; filter: drop-shadow(0 0 4px rgba(0, 200, 83, 0.4));"
				/>
				{#if group.count > 1}
					<text
						x={cx}
						y={cy + 3.5}
						text-anchor="middle"
						fill="rgba(255,255,255,0.75)"
						font-size="10"
						font-weight="700"
						pointer-events="none"
					>{group.count}</text>
				{/if}
			{:else}
				<!-- Outcome (yellow) / Wrong (red) / No result yet (gray) -->
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<circle
					{cx}
					{cy}
					{r}
					class={group.result === 'outcome' ? 'fill-warning' : group.result === 'wrong' ? 'fill-error/70' : 'fill-base-content/40'}
					stroke="rgba(0,0,0,0.2)"
					stroke-width="0.5"
					on:mouseenter={(e) => showTooltip(group, e)}
					on:mouseleave={hideTooltip}
					on:touchstart|preventDefault={(e) => showTooltip(group, e)}
					style="cursor: pointer; transition: r 0.2s ease;"
				/>
				{#if group.count > 1}
					<text
						x={cx}
						y={cy + 3.5}
						text-anchor="middle"
						fill="rgba(255,255,255,0.75)"
						font-size="10"
						font-weight="700"
						pointer-events="none"
					>{group.count}</text>
				{/if}
			{/if}
		{/each}

		<!-- Actual result star — only if no one predicted exact -->
		{#if actual && !hasExactPrediction}
			{@const sx = toX(actual.away_score)}
			{@const sy = toY(actual.home_score)}
			<polygon
				points={starPoints(sx, sy, 10, 4.5, 5)}
				class="fill-success"
				stroke="rgba(0,0,0,0.3)"
				stroke-width="0.5"
				style="filter: drop-shadow(0 0 4px rgba(0, 200, 83, 0.4));"
			/>
		{/if}

		<!-- "YOU" ring: dashed circle around the viewer's prediction -->
		{#if userRing}
			<circle
				cx={userRing.cx}
				cy={userRing.cy}
				r={userRing.r}
				fill="none"
				stroke="rgba(255,255,255,0.6)"
				stroke-width="1.5"
				stroke-dasharray="3 2.5"
			/>
			<text
				x={userRing.cx}
				y={userRing.cy - userRing.r - 4}
				text-anchor="middle"
				fill="rgba(255,255,255,0.5)"
				font-size="7"
				font-weight="600"
				font-family="'Inter', sans-serif"
				pointer-events="none"
			>YOU</text>
		{/if}
	</svg>

	<!-- Tooltip -->
	{#if hoveredGroup}
		<div
			class="absolute z-10 px-3 py-2 bg-base-300 border border-base-content/20 rounded-lg shadow-lg text-xs pointer-events-none"
			style="left: {tooltipX}px; top: {tooltipY}px; transform: translate(-50%, -100%);"
		>
			<div class="font-semibold text-base-content/80 mb-1">
				{hoveredGroup.home} - {hoveredGroup.away}
				{#if hoveredGroup.result === 'exact'}
					<span class="text-success ml-1">Exact</span>
				{:else if hoveredGroup.result === 'outcome'}
					<span class="text-warning-text ml-1">Correct</span>
				{:else if hoveredGroup.result === 'wrong'}
					<span class="text-error ml-1">Wrong</span>
				{/if}
			</div>
			{#each hoveredGroup.names as name}
				<div class="text-base-content/60">{name}</div>
			{/each}
		</div>
	{/if}
</div>

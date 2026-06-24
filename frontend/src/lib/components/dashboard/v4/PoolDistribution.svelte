<script lang="ts">
	import { onMount } from 'svelte';
	import { getPoolDistribution } from '$lib/api/leaderboard';
	import type { PoolDistributionResponse } from '$lib/types/leaderboard';

	let data: PoolDistributionResponse | null = null;
	let loading = true;

	onMount(async () => {
		try {
			data = await getPoolDistribution();
			if (data.user_points === 0 && data.bins.length === 0) data = null;
		} catch {
			data = null;
		} finally {
			loading = false;
		}
	});

	const W = 1080;
	// Taller viewBox so the histogram bars actually fill the side-column
	// card. Earlier we tried stretching the CARD via flex-1 — the chart
	// then sat marooned in empty space. Stretching the chart itself
	// (viewBox 1080×400) makes the bars grow to ~3× their previous height
	// and the card height tracks the chart naturally.
	const H = 400;
	const PAD_X = 20;

	$: chartGeom = data ? buildChartGeom(data) : null;

	function buildChartGeom(d: PoolDistributionResponse) {
		const totalBins = d.window_size * 2 + 1;
		const usable = W - PAD_X * 2;
		const binWidth = usable / totalBins;
		const maxCount = Math.max(1, ...d.bins.map(b => b.count));
		const baseY = H - 40;
		const topY = 60;
		const countByDelta = new Map(d.bins.map(b => [b.points_delta, b.count]));
		const bars = d.bins.map(b => {
			const x = PAD_X + (b.points_delta + d.window_size) * binWidth + binWidth * 0.1;
			const h = ((b.count / maxCount) * (baseY - topY));
			return {
				x,
				y: baseY - h,
				width: binWidth * 0.8,
				height: h,
				delta: b.points_delta,
				count: b.count,
				centerX: x + binWidth * 0.4,
			};
		});
		const userX = PAD_X + d.window_size * binWidth + binWidth * 0.5;
		const nextRankX = d.next_rank_points_away != null
			? PAD_X + (d.next_rank_points_away + d.window_size) * binWidth + binWidth * 0.5
			: null;

		// Five tick anchors: −w, −w/2, 0, +w/2, +w. Deduped via Map so
		// small windows (window_size ≤ 1) don't render stacked labels.
		const half = Math.round(d.window_size / 2);
		const tickDeltasRaw = [-d.window_size, -half, 0, half, d.window_size];
		const tickEntries = tickDeltasRaw.map(delta => [
			delta,
			{
				delta,
				x: PAD_X + (delta + d.window_size) * binWidth + binWidth * 0.5,
				label: delta === 0 ? '0' : (delta > 0 ? `+${delta}` : `${delta}`),
			},
		] as const);
		const ticks = Array.from(new Map(tickEntries).values());

		return { bars, userX, nextRankX, baseY, topY, ticks, countByDelta };
	}

	function barTooltip(delta: number, count: number): string {
		const word = count === 1 ? 'entry' : 'entries';
		if (delta === 0) return `Your score · ${count} ${word}`;
		const sign = delta > 0 ? '+' : '';
		return `${sign}${delta} pts · ${count} ${word}`;
	}
</script>

{#if !loading && data && chartGeom}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Pool Distribution</h3>
		</header>
		<p class="m-0 mb-2 text-sm text-base-content/55">{data.caption}</p>
		<svg viewBox="0 0 {W} {H}" class="w-full block">
			<line x1={PAD_X} y1={chartGeom.baseY} x2={W - PAD_X} y2={chartGeom.baseY} stroke="currentColor" stroke-opacity="0.18" stroke-width="1" />
			{#each chartGeom.bars as bar (bar.delta)}
				{@const isUser = bar.delta === 0}
				{@const isNear = Math.abs(bar.delta) <= 2 && !isUser}
				{@const tip = barTooltip(bar.delta, bar.count)}
				<rect
					x={bar.x}
					y={bar.y}
					width={bar.width}
					height={bar.height}
					class={isUser ? 'fill-primary' : isNear ? 'fill-primary/40' : 'fill-base-content/15'}
					role="img"
					aria-label={tip}
				>
					<title>{tip}</title>
				</rect>
			{/each}
			<line x1={chartGeom.userX} y1={14} x2={chartGeom.userX} y2={chartGeom.topY - 2} stroke="currentColor" stroke-width="1.5" class="text-primary" />
			<text x={chartGeom.userX} y={11} text-anchor="middle" font-size="11" font-weight="700" class="fill-primary">YOU</text>
			{#if chartGeom.nextRankX != null && data.next_rank_position != null}
				<line x1={chartGeom.nextRankX} y1={22} x2={chartGeom.nextRankX} y2={chartGeom.topY + 14} stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 3" class="text-success" />
				<text x={chartGeom.nextRankX} y={18} text-anchor="middle" font-size="11" font-weight="600" class="fill-success">#{data.next_rank_position}</text>
			{/if}
			<!-- Five tick anchors with stub marks (replaces the old 3 low-contrast labels).
			     Centre tick is bolder + brighter; flanking ticks at /70 so they read
			     comfortably without competing with the gold YOU bar marker. -->
			{#each chartGeom.ticks as t (t.delta)}
				<line x1={t.x} y1={chartGeom.baseY} x2={t.x} y2={chartGeom.baseY + 4} stroke="currentColor" stroke-opacity="0.35" stroke-width="1" />
				<text
					x={t.x}
					y={H - 10}
					text-anchor="middle"
					font-size="16"
					font-weight={t.delta === 0 ? 700 : 500}
					class={t.delta === 0 ? 'fill-base-content/85' : 'fill-base-content/70'}>{t.label}</text
				>
			{/each}
			<!-- Micro-caption identifies the axis units without repeating "pts" per tick -->
			<text x={W - PAD_X} y={H - 28} text-anchor="end" font-size="11" class="fill-base-content/50">pts vs you</text>
		</svg>
	</section>
{/if}

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
		const bars = d.bins.map(b => {
			const x = PAD_X + (b.points_delta + d.window_size) * binWidth + binWidth * 0.1;
			const h = ((b.count / maxCount) * (baseY - topY));
			return {
				x,
				y: baseY - h,
				width: binWidth * 0.8,
				height: h,
				delta: b.points_delta,
			};
		});
		const userX = PAD_X + d.window_size * binWidth + binWidth * 0.5;
		const nextRankX = d.next_rank_points_away != null
			? PAD_X + (d.next_rank_points_away + d.window_size) * binWidth + binWidth * 0.5
			: null;
		return { bars, userX, nextRankX, baseY, topY };
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
				<rect
					x={bar.x}
					y={bar.y}
					width={bar.width}
					height={bar.height}
					class={isUser ? 'fill-primary' : isNear ? 'fill-primary/40' : 'fill-base-content/15'}
				/>
			{/each}
			<line x1={chartGeom.userX} y1={14} x2={chartGeom.userX} y2={chartGeom.topY - 2} stroke="currentColor" stroke-width="1.5" class="text-primary" />
			<text x={chartGeom.userX} y={11} text-anchor="middle" font-size="11" font-weight="700" class="fill-primary">YOU</text>
			{#if chartGeom.nextRankX != null && data.next_rank_position != null}
				<line x1={chartGeom.nextRankX} y1={22} x2={chartGeom.nextRankX} y2={chartGeom.topY + 14} stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 3" class="text-success" />
				<text x={chartGeom.nextRankX} y={18} text-anchor="middle" font-size="11" font-weight="600" class="fill-success">#{data.next_rank_position}</text>
			{/if}
			<text x={PAD_X} y={H - 10} font-size="11" class="fill-base-content/40">−{data.window_size}pt</text>
			<text x={W / 2} y={H - 10} text-anchor="middle" font-size="11" font-weight="700" class="fill-base-content/40">YOU</text>
			<text x={W - PAD_X} y={H - 10} text-anchor="end" font-size="11" class="fill-base-content/40">+{data.window_size}pt</text>
		</svg>
	</section>
{/if}

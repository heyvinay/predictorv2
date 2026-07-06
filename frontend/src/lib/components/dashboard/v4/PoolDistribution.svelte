<script lang="ts">
	import { onMount } from 'svelte';
	import { getPoolDistribution } from '$lib/api/leaderboard';
	import type { PoolDistributionResponse, YourEntryMarker } from '$lib/types/leaderboard';

	let data: PoolDistributionResponse | null = null;
	let loading = true;

	onMount(async () => {
		try {
			data = await getPoolDistribution();
			if (data.total_entries === 0) data = null;
		} catch {
			data = null;
		} finally {
			loading = false;
		}
	});

	// viewBox units — NOT screen pixels. This card renders at roughly
	// 400-500px wide, so a "16" font-size here lands around 6-7px on
	// screen. Every font-size below is picked backwards from a target
	// on-screen size at that scale (see the v2.198.x illegibility fix).
	const W = 1080;
	const H = 400;
	const PAD_X = 24;

	$: chartGeom = data ? buildChartGeom(data) : null;

	// Two labels are treated as colliding (and staggered onto different
	// vertical tiers) when their centers land within this many viewBox
	// units of each other — roughly 8% of the chart width.
	const COLLISION_PX = 90;

	function buildChartGeom(d: PoolDistributionResponse) {
		const usable = W - PAD_X * 2;
		// Axis line sits high enough to leave room for two label rows below
		// it (tick numbers, then the "pts in pool" caption) without either
		// row crowding the bottom edge or overlapping the other.
		const baseY = H - 64;
		const topY = 86;
		const span = Math.max(1, d.max_points - d.min_points + d.bucket_width);
		const xOf = (points: number) => PAD_X + ((points - d.min_points) / span) * usable;

		const maxCount = Math.max(1, ...d.bins.map((b) => b.count));
		const bars = d.bins.map((b) => {
			const x = xOf(b.bucket_start);
			const barW = Math.max(2, (usable / span) * d.bucket_width - 2);
			const h = (b.count / maxCount) * (baseY - topY);
			return { x, width: barW, y: baseY - h, height: h, bucketStart: b.bucket_start, bucketEnd: b.bucket_end, count: b.count };
		});

		// Sort by position on the x-axis so the collision pass only ever
		// compares neighbours, then alternate tiers whenever two labels
		// would land close enough to overlap.
		const sorted = [...d.your_entries].sort((a, b) => a.points - b.points);
		let lastX = -Infinity;
		let tier = 0;
		const markers = sorted.map((e) => {
			const x = xOf(e.points) + (usable / span) * (d.bucket_width / 2);
			if (x - lastX < COLLISION_PX) {
				tier = tier === 0 ? 1 : 0;
			} else {
				tier = 0;
			}
			lastX = x;
			return { entry: e, x, tier };
		});

		return { bars, markers, baseY, topY };
	}

	function barTooltip(bucketStart: number, bucketEnd: number, count: number): string {
		const word = count === 1 ? 'entry' : 'entries';
		return `${bucketStart}–${bucketEnd} pts · ${count} ${word}`;
	}
</script>

{#if !loading && data && chartGeom}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Pool Distribution</h3>
		</header>
		<p class="m-0 mb-2 text-sm text-base-content/55">{data.caption}</p>
		<svg viewBox="0 0 {W} {H}" class="w-full block" role="img" aria-label={data.caption}>
			<line x1={PAD_X} y1={chartGeom.baseY} x2={W - PAD_X} y2={chartGeom.baseY} stroke="currentColor" stroke-opacity="0.18" stroke-width="1" />

			{#each chartGeom.bars as bar (bar.bucketStart)}
				{@const tip = barTooltip(bar.bucketStart, bar.bucketEnd, bar.count)}
				<rect
					x={bar.x}
					y={bar.y}
					width={bar.width}
					height={bar.height}
					class="fill-base-content/15"
					role="img"
					aria-label={tip}
				>
					<title>{tip}</title>
				</rect>
			{/each}

			<!-- Every entry the user owns gets its own marker — staggered onto
			     a second vertical tier when two land close enough to collide,
			     so multi-entry players can see all of their picks at once. The
			     dashed guide runs the full label-to-axis height so it reads as
			     a pointer to the entry's exact position, not just a label stem. -->
			{#each chartGeom.markers as m (m.entry.entry_id)}
				{@const labelY = m.tier === 0 ? 34 : 60}
				<line x1={m.x} y1={labelY + 6} x2={m.x} y2={chartGeom.baseY} stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 5" class="text-primary" stroke-opacity="0.6" />
				<text x={m.x} y={labelY} text-anchor="middle" font-size="22" font-weight="700" class="fill-primary">{m.entry.entry_name}</text>
			{/each}

			<!-- One label per bar (its bucket's starting point total), rather
			     than generic evenly-spaced ticks — bucket boundaries aren't
			     evenly spaced relative to the point range, so a shared tick
			     set would drift out of alignment with the bars it sits under. -->
			<g font-family="monospace" font-size="20" fill="currentColor" fill-opacity="0.6">
				{#each chartGeom.bars as bar (bar.bucketStart)}
					{@const cx = bar.x + bar.width / 2}
					<line x1={cx} y1={chartGeom.baseY} x2={cx} y2={chartGeom.baseY + 4} stroke="currentColor" stroke-opacity="0.35" stroke-width="1" />
					<text x={cx} y={chartGeom.baseY + 28} text-anchor="middle">{bar.bucketStart}</text>
				{/each}
			</g>
			<text x={W / 2} y={chartGeom.baseY + 54} text-anchor="middle" font-size="22" class="fill-base-content/50">pts in pool</text>
		</svg>
	</section>
{/if}

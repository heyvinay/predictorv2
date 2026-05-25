<script lang="ts">
	// Small inline SVG sparkline used by Dashboard (rank trajectory) and
	// Leaderboard (per-player trend column). Renders a filled area + a line
	// + circle markers. Pure visualization — accepts pre-computed rank values
	// and scale so the caller controls seeding.
	import { sparklinePath } from '$lib/utils/widgetFallbacks';

	/** Rank values, oldest at [0], newest at [end]. Smaller = better. */
	export let ranks: number[];
	/** Max rank (e.g. total players) for normalising the y-axis. */
	export let maxRank: number;
	export let width: number = 240;
	export let height: number = 56;
	export let strokeColor: string = 'currentColor';
	export let fillColor: string = 'transparent';
	export let markerColor: string = 'currentColor';

	$: ({ linePath, fillPath, points } = sparklinePath(ranks, maxRank, {
		width,
		height,
		padTop: 0.05,
		padBottom: 0.05
	}));
</script>

<svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">
	{#each [0.25, 0.5, 0.75] as p}
		<line
			x1="0"
			y1={height * p}
			x2={width}
			y2={height * p}
			stroke="currentColor"
			stroke-opacity="0.12"
			stroke-width="0.6"
		/>
	{/each}
	<path d={fillPath} fill={fillColor} />
	<path d={linePath} fill="none" stroke={strokeColor} stroke-width="2" />
	{#each points as [x, y], i}
		<circle cx={x} cy={y} r={i === points.length - 1 ? 4 : 2.5} fill={markerColor} />
	{/each}
</svg>

<style>
	.sparkline {
		width: 100%;
		display: block;
	}
</style>

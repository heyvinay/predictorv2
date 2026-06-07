<!--
  Small inline SVG sparkline. Active variant = solid gold line + soft
  gold fill + gold end-marker. Ghost variant = dashed muted line, no
  fill, no marker (used by KPI trajectory to draw sibling-entry lines
  behind the active line).

  Ported from upstream's PnSparkline.svelte. Token swap:
    - var(--red) → var(--p, #D4AF37) (gold)
    - var(--gold) (marker) → var(--p)
    - var(--ink) (marker stroke) → var(--b2, #1C2541)
-->
<script lang="ts">
	import { sparklinePath } from '$lib/utils/sparklinePath';

	export let ranks: number[];
	export let maxRank: number;
	export let width: number = 240;
	export let height: number = 56;
	export let ghost: boolean = false;

	$: ({ linePath, fillPath, points } = sparklinePath(ranks, maxRank, {
		width,
		height,
		padTop: 0.05,
		padBottom: 0.05
	}));
</script>

<svg
	viewBox="0 0 {width} {height}"
	preserveAspectRatio="none"
	aria-hidden="true"
	style="display:block; width:100%; height:auto;"
>
	{#each [0.25, 0.5, 0.75] as p}
		<line
			x1="0"
			y1={height * p}
			x2={width}
			y2={height * p}
			stroke="rgba(255,255,255,0.06)"
			stroke-width="0.6"
		/>
	{/each}
	{#if !ghost && fillPath}
		<path d={fillPath} fill="rgba(212,175,55,0.12)" />
	{/if}
	{#if linePath}
		<path
			d={linePath}
			fill="none"
			stroke={ghost ? 'rgba(226,232,240,0.30)' : 'var(--p, #D4AF37)'}
			stroke-width={ghost ? 1.5 : 2}
			stroke-dasharray={ghost ? '3 3' : 'none'}
			vector-effect="non-scaling-stroke"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	{/if}
	{#if !ghost && points.length > 0}
		{@const last = points[points.length - 1]}
		<circle
			cx={last[0]}
			cy={last[1]}
			r="3"
			fill="var(--p, #D4AF37)"
			stroke="var(--b2, #1C2541)"
			stroke-width="1.5"
		/>
	{/if}
</svg>

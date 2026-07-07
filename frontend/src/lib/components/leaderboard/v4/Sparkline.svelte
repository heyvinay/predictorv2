<script lang="ts">
	/** Tiny SVG line chart of an entry's RANK trajectory (v2.206.0 —
	 *  was total-points, which is monotonically non-decreasing for
	 *  every entry by construction and so always trended up-right
	 *  regardless of how well an entry was actually doing). Lower
	 *  rank number is better, so the y-axis is inverted here: the
	 *  best rank in the window plots at the TOP. Coloured by net
	 *  direction (rank improved = success, worsened = error, flat
	 *  or single-point = muted). Returns a placeholder dash when
	 *  fewer than 2 data points exist. */
	export let ranks: number[] = [];

	const W = 60;
	const H = 18;

	$: ready = ranks.length >= 2;
	$: lo = ready ? Math.min(...ranks) : 0;
	$: hi = ready ? Math.max(...ranks) : 1;
	$: range = Math.max(1, hi - lo);
	$: dx = ready ? (W - 4) / (ranks.length - 1) : 0;
	$: path = ready
		? ranks
				.map((v, i) => {
					const x = 2 + i * dx;
					const y = 2 + ((v - lo) / range) * (H - 4); // lowest rank (best) -> top
					return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
				})
				.join(' ')
		: '';
	// Positive delta = rank NUMBER went down = improved.
	$: delta = ready ? ranks[0] - ranks[ranks.length - 1] : 0;
	$: stroke =
		delta > 0
			? 'stroke-success'
			: delta < 0
			? 'stroke-error'
			: 'stroke-base-content/40';
</script>

{#if ready}
	<svg
		viewBox="0 0 {W} {H}"
		class="h-[18px] w-[60px]"
		aria-label="Rank trajectory"
		role="img"
	>
		<path
			d={path}
			fill="none"
			stroke-width="1.4"
			stroke-linecap="round"
			stroke-linejoin="round"
			class="transition-colors {stroke}"
		/>
	</svg>
{:else}
	<span class="text-[10px] text-base-content/30" aria-label="no trajectory yet">—</span>
{/if}

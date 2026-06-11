<script lang="ts">
	/** Tiny SVG line chart of an entry's total-points trajectory.
	 *  Coloured by net direction (up = success, down = error, flat
	 *  or single-point = muted). Returns a placeholder dash when
	 *  fewer than 2 data points exist. */
	export let points: number[] = [];

	const W = 60;
	const H = 18;

	$: ready = points.length >= 2;
	$: lo = ready ? Math.min(...points) : 0;
	$: hi = ready ? Math.max(...points) : 1;
	$: range = Math.max(1, hi - lo);
	$: dx = ready ? (W - 4) / (points.length - 1) : 0;
	$: path = ready
		? points
				.map((v, i) => {
					const x = 2 + i * dx;
					const y = 2 + ((hi - v) / range) * (H - 4);
					return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
				})
				.join(' ')
		: '';
	$: delta = ready ? points[points.length - 1] - points[0] : 0;
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
		aria-label="Points trajectory"
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

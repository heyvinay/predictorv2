<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getCohortTrail } from '$lib/api/leaderboard';
	import type { CohortTrailResponse, CohortKey } from '$lib/types/leaderboard';

	const dispatch = createEventDispatcher<{ cohortClick: { cohort: CohortKey } }>();

	let data: CohortTrailResponse | null = null;
	let loading = true;

	const COLORS: Record<CohortKey, string> = {
		atlas: '#38bdf8',
		jmfa: '#a78bfa',
		guests: '#94a3b8',
	};
	const LABELS: Record<CohortKey, string> = {
		atlas: 'Atlas',
		jmfa: 'JMFA',
		guests: 'Guests',
	};

	onMount(async () => {
		try {
			data = await getCohortTrail();
		} catch {
			data = null;
		} finally {
			loading = false;
		}
	});

	const W = 1040, H = 220, PAD_L = 50, PAD_R = 200, PAD_T = 40, PAD_B = 50;

	$: yRange = computeYRange(data);
	$: xRange = computeXRange(data);

	function computeYRange(d: CohortTrailResponse | null): [number, number] {
		if (!d || d.cohorts.length === 0) return [1, 100];
		const all = d.cohorts.flatMap(c => c.points.map(p => p.median_rank));
		return [Math.max(1, Math.floor(Math.min(...all)) - 5), Math.ceil(Math.max(...all)) + 5];
	}

	function computeXRange(d: CohortTrailResponse | null): [string, string] {
		if (!d || d.cohorts.length === 0) return ['', ''];
		const dates = d.cohorts.flatMap(c => c.points.map(p => p.captured_date)).sort();
		return [dates[0], dates.at(-1)!];
	}

	function xPos(date: string): number {
		if (!data || !xRange[0]) return PAD_L;
		const t0 = Date.parse(xRange[0]);
		const t1 = Date.parse(xRange[1]);
		const t = Date.parse(date);
		const frac = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
		return PAD_L + frac * (W - PAD_L - PAD_R);
	}

	function yPos(rank: number): number {
		const [min, max] = yRange;
		const frac = (rank - min) / (max - min);
		return PAD_T + frac * (H - PAD_T - PAD_B);
	}
</script>

{#if !loading && data && data.cohorts.length > 0}
	<div class="bg-base-100 border border-base-300 rounded-box p-4">
		<div class="flex items-center gap-2 mb-2">
			<span class="font-semibold">Cohort Race</span>
			<span class="text-xs text-base-content/40">median rank · click a label to filter the chart above</span>
		</div>
		<svg viewBox="0 0 {W} {H}" class="w-full">
			<g stroke="currentColor" stroke-opacity="0.08" stroke-width="0.5">
				<line x1={PAD_L} y1={PAD_T} x2={W - PAD_R} y2={PAD_T} />
				<line x1={PAD_L} y1={(PAD_T + H - PAD_B) / 2} x2={W - PAD_R} y2={(PAD_T + H - PAD_B) / 2} />
				<line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} />
			</g>
			{#each data.cohorts as c (c.cohort)}
				{@const pts = c.points.map(p => `${xPos(p.captured_date)},${yPos(p.median_rank)}`).join(' ')}
				<polyline points={pts} stroke={COLORS[c.cohort]} stroke-width="3" fill="none" />
				<circle cx={xPos(c.points.at(-1)?.captured_date ?? '')} cy={yPos(c.current_median_rank)} r="5" fill={COLORS[c.cohort]} />
				<text
					x={W - PAD_R + 10}
					y={yPos(c.current_median_rank) + 4}
					font-size="12"
					font-weight="700"
					fill={COLORS[c.cohort]}
					class="cursor-pointer"
					on:click={() => dispatch('cohortClick', { cohort: c.cohort })}
				>{LABELS[c.cohort]} · median #{Math.round(c.current_median_rank)}</text>
			{/each}
		</svg>
		<p class="text-xs text-base-content/40 m-0 mt-2">
			Plotted as median rank. Lower is better — an upward line is good.
		</p>
	</div>
{/if}

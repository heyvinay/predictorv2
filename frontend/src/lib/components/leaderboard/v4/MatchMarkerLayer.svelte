<script lang="ts">
	import type { MatchMarker } from '$lib/types/leaderboard';

	export let markers: MatchMarker[];
	/** x-position function: ISO date → SVG x */
	export let xScale: (isoDate: string) => number;
	/** y-range of the chart in SVG units, used for the dashed crosshair line. */
	export let yTop: number;
	export let yBottom: number;
</script>

<g class="match-markers">
	{#each markers as m (m.fixture_id)}
		{@const cx = xScale(m.kickoff.slice(0, 10))}
		<line x1={cx} y1={yTop} x2={cx} y2={yBottom} stroke={m.is_upset ? 'rgb(212 175 55 / 0.55)' : 'rgb(255 255 255 / 0.08)'} stroke-width="1" stroke-dasharray="3 4"></line>
		<g transform="translate({cx}, {yBottom + 14})">
			<rect x="-38" y="0" width="76" height="16" rx="3" fill="var(--fallback-b1, hsl(var(--b1)))" stroke={m.is_upset ? 'rgb(212 175 55 / 0.5)' : 'currentColor'} stroke-opacity="0.3"></rect>
			<text x="0" y="11" text-anchor="middle" font-size="9" class={m.is_upset ? 'fill-primary font-bold' : 'fill-base-content/55'}>
				{m.home_team_code} {m.home_score}-{m.away_score} {m.away_team_code}
			</text>
		</g>
	{/each}
</g>

<!--
  3-segment crowd histogram bar for the match carousel. Shows the
  pool-wide split of home-win / draw / away-win predictions, with the
  active entry's predicted bucket outlined in gold.

  Data source: getCommunityPredictions(fixtureId) returns all individual
  predictions for that fixture. We bucket client-side into 1/X/2 and
  compute percentages. Privacy-safe — we only display aggregated counts,
  never individual picks.
-->
<script lang="ts">
	import type { CommunityPredictionsResponse } from '$types';

	export let community: CommunityPredictionsResponse | null;
	export let yourPickBucket: 'home' | 'draw' | 'away' | null;
	export let yourPickLabel: string | null = null;

	$: counts = community
		? bucket(community.predictions)
		: { home: 0, draw: 0, away: 0, total: 0 };

	function bucket(preds: { home_score: number; away_score: number }[]) {
		let home = 0;
		let draw = 0;
		let away = 0;
		for (const p of preds) {
			if (p.home_score > p.away_score) home++;
			else if (p.home_score < p.away_score) away++;
			else draw++;
		}
		return { home, draw, away, total: preds.length };
	}

	$: pct =
		counts.total > 0
			? {
					home: Math.round((counts.home / counts.total) * 100),
					draw: Math.round((counts.draw / counts.total) * 100),
					away: Math.round((counts.away / counts.total) * 100)
				}
			: { home: 0, draw: 0, away: 0 };

	function youBadge(b: 'home' | 'draw' | 'away'): string {
		return yourPickBucket === b ? ' ◂you' : '';
	}
</script>

{#if community && counts.total > 0}
	<div class="mt-2.5">
		<div
			class="flex justify-between text-[10px] font-bold uppercase tracking-[0.08em] text-base-content/55 mb-1.5"
		>
			<span>Crowd</span>
			{#if yourPickBucket && yourPickLabel}
				<span class="text-base-content/72 normal-case tracking-normal font-semibold">
					you: {yourPickLabel}
				</span>
			{/if}
		</div>
		<div class="flex h-2 rounded-full overflow-hidden border border-base-300/50">
			<div
				class="bg-primary"
				style:width="{pct.home}%"
				style:box-shadow={yourPickBucket === 'home' ? 'inset 0 0 0 2px var(--p, #D4AF37)' : 'none'}
			></div>
			<div
				class="bg-base-300"
				style:width="{pct.draw}%"
				style:box-shadow={yourPickBucket === 'draw' ? 'inset 0 0 0 2px var(--p, #D4AF37)' : 'none'}
			></div>
			<div
				class="bg-success"
				style:width="{pct.away}%"
				style:box-shadow={yourPickBucket === 'away' ? 'inset 0 0 0 2px var(--p, #D4AF37)' : 'none'}
			></div>
		</div>
		<div class="flex justify-between mt-1 text-[10px]">
			<span class:font-bold={yourPickBucket === 'home'} class:text-primary={yourPickBucket === 'home'} class:text-base-content={yourPickBucket !== 'home'} style:opacity={yourPickBucket === 'home' ? 1 : 0.55}>
				{pct.home}%{youBadge('home')}
			</span>
			<span class:font-bold={yourPickBucket === 'draw'} class:text-primary={yourPickBucket === 'draw'} class:text-base-content={yourPickBucket !== 'draw'} style:opacity={yourPickBucket === 'draw' ? 1 : 0.55}>
				{pct.draw}%{youBadge('draw')}
			</span>
			<span class:font-bold={yourPickBucket === 'away'} class:text-primary={yourPickBucket === 'away'} class:text-base-content={yourPickBucket !== 'away'} style:opacity={yourPickBucket === 'away' ? 1 : 0.55}>
				{pct.away}%{youBadge('away')}
			</span>
		</div>
	</div>
{/if}

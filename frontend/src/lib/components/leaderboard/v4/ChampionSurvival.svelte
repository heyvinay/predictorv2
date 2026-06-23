<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getChampionSurvival } from '$lib/api/leaderboard';
	import type { ChampionSurvivalResponse } from '$lib/types/leaderboard';

	const dispatch = createEventDispatcher<{ teamClick: { team_code: string } }>();

	let data: ChampionSurvivalResponse | null = null;
	let loading = true;

	onMount(async () => {
		try {
			data = await getChampionSurvival();
		} catch {
			data = null;
		} finally {
			loading = false;
		}
	});

	$: percentAlive = data && data.total_count > 0
		? Math.round((data.alive_count / data.total_count) * 100)
		: 0;

	$: gaugePath = buildGaugePath(percentAlive);

	function buildGaugePath(pct: number): string {
		const cx = 70, cy = 82, r = 58;
		const startA = Math.PI;
		const endA = Math.PI - (pct / 100) * Math.PI;
		const x1 = cx + r * Math.cos(startA);
		const y1 = cy + r * Math.sin(startA);
		const x2 = cx + r * Math.cos(endA);
		const y2 = cy + r * Math.sin(endA);
		const largeArc = pct > 50 ? 1 : 0;
		return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
	}
</script>

{#if !loading && data && data.total_count > 0}
	<div class="bg-base-100 border border-base-300 rounded-box p-4 mb-3">
		<div class="grid grid-cols-[120px_1fr] md:grid-cols-[160px_1fr] gap-4 items-center">
			<svg viewBox="0 0 140 95" class="w-full max-w-[160px] mx-auto">
				<path d="M 12 82 A 58 58 0 0 1 128 82" stroke="rgb(255 255 255 / 0.12)" stroke-width="14" fill="none" stroke-linecap="round" />
				<path d={gaugePath} stroke="currentColor" stroke-width="14" fill="none" stroke-linecap="round" class="text-success" />
				<text x="70" y="68" text-anchor="middle" font-size="28" font-weight="800" class="fill-base-content">{percentAlive}%</text>
				<text x="70" y="86" text-anchor="middle" font-size="10" class="fill-base-content/55">champion still alive</text>
			</svg>
			<div>
				<div class="text-sm text-base-content/55 mb-2">
					<b class="text-base-content">{data.alive_count} of {data.total_count} entries</b> still hold a champion pick alive in the tournament.
				</div>
				<div class="flex flex-wrap gap-1.5">
					{#each data.teams as t (t.team_code)}
						<button
							type="button"
							class="badge gap-1.5 cursor-pointer"
							class:badge-success={t.alive}
							class:badge-error={!t.alive}
							class:opacity-70={!t.alive}
							class:line-through={!t.alive}
							on:click={() => dispatch('teamClick', { team_code: t.team_code })}
						>
							{t.team_name} · {t.count} {t.alive ? 'alive' : 'out'}
						</button>
					{/each}
				</div>
			</div>
		</div>
	</div>
{/if}

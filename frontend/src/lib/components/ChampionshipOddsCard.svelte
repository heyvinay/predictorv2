<script lang="ts">
	/** "Who's favourite to win it all" — top 10 by averaged, de-vigged
	 *  implied win probability from The Odds API's outrights market
	 *  (backend/app/services/odds_cache.py:get_or_refresh_outrights).
	 *
	 *  Self-contained card (own chrome, own fetch) so it drops into either
	 *  the Dashboard side column or the Leaderboard Insights grid without
	 *  a wrapper — same convention as ChampionSurvival.svelte. Hides
	 *  itself entirely when the odds feed isn't configured or empty, so
	 *  neither page needs to branch on availability.
	 */
	import { onMount } from 'svelte';
	import { getChampionshipOdds } from '$lib/api/odds';
	import { getFlagUrl } from '$lib/utils/flags';
	import { relativeAgo } from '$lib/utils/relativeTime';

	let teams: { team: string; probability: number }[] = [];
	let fetchedAt: string | null = null;
	let loading = true;
	let now = Date.now();

	onMount(() => {
		void (async () => {
			try {
				const res = await getChampionshipOdds();
				if (!res.error && res.teams.length > 0) {
					teams = res.teams;
					fetchedAt = res.fetchedAt ?? null;
				}
			} catch {
				teams = [];
			} finally {
				loading = false;
			}
		})();
		const tick = setInterval(() => (now = Date.now()), 30_000);
		return () => clearInterval(tick);
	});

	$: maxProbability = teams.length ? teams[0].probability : 1;
	$: updatedLabel = fetchedAt ? relativeAgo(fetchedAt, now) : null;
</script>

{#if !loading && teams.length > 0}
	<section class="rounded-box border border-base-300 bg-base-200 p-4 sm:p-5">
		<header class="mb-1 flex items-start justify-between gap-3">
			<h3 class="font-hero text-[21px] tracking-[0.04em]">Championship Odds</h3>
		</header>
		<p class="mb-1 text-xs text-base-content/55">
			Top {teams.length} teams by market-implied chance of winning the World Cup
		</p>
		{#if updatedLabel}
			<p class="mb-3.5 text-[10.5px] text-base-content/40">Updated {updatedLabel}</p>
		{/if}

		<div class="flex flex-col gap-2">
			{#each teams as t, i (t.team)}
				{@const flagUrl = getFlagUrl(t.team, 'sm')}
				<div class="grid grid-cols-[16px_20px_1fr_auto] items-center gap-2.5">
					<span class="text-right font-display text-[11px] font-extrabold text-base-content/40"
						>{i + 1}</span
					>
					{#if flagUrl}
						<img
							src={flagUrl}
							alt=""
							class="h-3.5 w-5 flex-none rounded-sm object-cover ring-1 ring-black/30"
							loading="lazy"
						/>
					{:else}
						<span class="h-3.5 w-5 flex-none rounded-sm bg-base-300"></span>
					{/if}
					<span class="flex items-center gap-2 overflow-hidden">
						<span class="truncate text-xs font-semibold text-base-content">{t.team}</span>
						<span class="h-1.5 flex-1 min-w-[36px] overflow-hidden rounded-full bg-base-300/40">
							<span
								class="block h-full rounded-full bg-primary"
								style="width:{(t.probability / maxProbability) * 100}%"
							></span>
						</span>
					</span>
					<b class="text-right font-display text-[13px] font-extrabold text-primary tabular-nums"
						>{Math.round(t.probability * 100)}%</b
					>
				</div>
			{/each}
		</div>

		<p class="mt-3 border-t border-base-300/45 pt-2.5 text-[10.5px] leading-relaxed text-base-content/40">
			Market average across bookmakers, de-vigged. Moves with betting markets, not our
			scoring — for interest only.
		</p>
	</section>
{/if}

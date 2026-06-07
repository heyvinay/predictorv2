<!--
  Post-competition podium for the top 3 finishers. Adapted from upstream's
  DwChampionPodium and simplified for single-phase (no separate Groups
  Winner / Bracket Winner steps — those were two-phase artefacts).

  Three cards in a row at desktop, stacked on mobile. #1 in the center,
  visually elevated; #2 on the left, #3 on the right. Mockup-ordered:
  ranks display in 2-1-3 reading order on desktop (silver | gold | bronze)
  per traditional podium ergonomics; we render in semantic 1-2-3 order
  and let CSS reorder the visual sequence.
-->
<script lang="ts">
	import type { LeaderboardEntry } from '$types';

	export let top3: LeaderboardEntry[] = [];

	$: gold = top3[0] ?? null;
	$: silver = top3[1] ?? null;
	$: bronze = top3[2] ?? null;
</script>

<div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-10 max-w-3xl">
	<!-- 2nd (silver) — first on desktop reading order, second below gold -->
	{#if silver}
		<div class="stadium-card no-glow p-6 text-center order-2 sm:order-1">
			<div
				class="w-12 h-12 rounded-full mx-auto grid place-items-center font-display font-extrabold text-lg mb-3"
				style="background: linear-gradient(135deg, #D5D9E2, #9BA3B0); color: #0B1329;"
			>
				2
			</div>
			<p class="text-[10px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-2">Silver</p>
			<p class="font-display font-extrabold text-base sm:text-lg">{silver.entry_name}</p>
			<p class="text-base-content/55 text-xs">{silver.user_name}</p>
			<p class="font-display font-extrabold text-2xl sm:text-3xl text-primary mt-3 tabular-nums">
				{silver.total_points}
			</p>
			<p class="text-base-content/55 text-[10px] uppercase tracking-[0.12em] mt-0.5">pts</p>
		</div>
	{/if}

	<!-- 1st (gold) — visually largest, center on desktop -->
	{#if gold}
		<div
			class="stadium-card no-glow p-6 sm:p-8 text-center order-1 sm:order-2 sm:scale-105"
			style="background: linear-gradient(135deg, rgba(212,175,55,0.12), var(--b2, #1C2541));"
		>
			<div
				class="w-14 h-14 rounded-full mx-auto grid place-items-center font-display font-extrabold text-xl mb-3"
				style="background: linear-gradient(135deg, #E9C649, #A88621); color: #0B1329;"
			>
				1
			</div>
			<p class="text-[10px] font-bold uppercase tracking-[0.12em] text-primary mb-2">Champion</p>
			<p class="font-display font-extrabold text-lg sm:text-xl">{gold.entry_name}</p>
			<p class="text-base-content/55 text-xs">{gold.user_name}</p>
			<p class="font-display font-extrabold text-3xl sm:text-4xl text-primary mt-3 tabular-nums">
				{gold.total_points}
			</p>
			<p class="text-base-content/55 text-[10px] uppercase tracking-[0.12em] mt-0.5">pts</p>
		</div>
	{/if}

	<!-- 3rd (bronze) — last in all orderings -->
	{#if bronze}
		<div class="stadium-card no-glow p-6 text-center order-3">
			<div
				class="w-12 h-12 rounded-full mx-auto grid place-items-center font-display font-extrabold text-lg mb-3"
				style="background: linear-gradient(135deg, #D49A6A, #9B6B3F); color: #0B1329;"
			>
				3
			</div>
			<p class="text-[10px] font-bold uppercase tracking-[0.12em] text-base-content/55 mb-2">Bronze</p>
			<p class="font-display font-extrabold text-base sm:text-lg">{bronze.entry_name}</p>
			<p class="text-base-content/55 text-xs">{bronze.user_name}</p>
			<p class="font-display font-extrabold text-2xl sm:text-3xl text-primary mt-3 tabular-nums">
				{bronze.total_points}
			</p>
			<p class="text-base-content/55 text-[10px] uppercase tracking-[0.12em] mt-0.5">pts</p>
		</div>
	{/if}
</div>

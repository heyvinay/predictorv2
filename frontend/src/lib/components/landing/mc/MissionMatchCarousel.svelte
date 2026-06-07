<!--
  MissionMatchCarousel — bidirectional 2-row horizontal rail of match
  cards. Mockup section 4.5 (mockup-original layout; upstream uses a
  table view).

  Behaviour mirrors ESPN-style rails:
    - Hidden scrollbar, scroll/swipe works
    - Circular ‹/› arrow buttons float over left/right edges,
      vertically centered
    - On mount, auto-anchors to the first live (else first upcoming)
      match column
    - Pages smoothly via manual rAF tween (native smooth-scroll is
      unreliable on scroll-snap containers)

  Cards are MissionMatchCard. Status badges, picks, points, crowd bar
  and rarity payoff all live in the card; the carousel just owns
  layout + scroll.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import MissionMatchCard from './MissionMatchCard.svelte';
	import type { Fixture, MatchPrediction, CommunityPredictionsResponse } from '$types';
	import type { FixtureAgreement } from '$api/predictions';
	import type { ScoringConfig } from '$api/competition';

	export let fixtures: Fixture[];
	export let predictionByFixture: Map<string, MatchPrediction>;
	export let agreementByFixture: Map<string, FixtureAgreement>;
	export let communityByFixture: Map<string, CommunityPredictionsResponse>;
	export let scoringConfig: ScoringConfig;

	let trackRef: HTMLDivElement;

	$: liveCount = fixtures.filter((f) => f.status === 'live' || f.status === 'halftime').length;

	onMount(async () => {
		await tick();
		if (!trackRef) return;
		const idx = fixtures.findIndex((f) => f.status === 'live' || f.status === 'halftime');
		const anchor =
			idx >= 0
				? idx
				: fixtures.findIndex(
						(f) => f.status === 'scheduled' || (f.is_locked && f.status === 'scheduled')
					);
		if (anchor < 0) return;
		const col = Math.floor(anchor / 2);
		const card = trackRef.querySelector<HTMLElement>(`[data-col="${col}"]`);
		if (card) trackRef.scrollLeft = Math.max(0, card.offsetLeft - 12);
	});

	function page(dir: -1 | 1) {
		if (!trackRef) return;
		const start = trackRef.scrollLeft;
		const max = trackRef.scrollWidth - trackRef.clientWidth;
		const target = Math.max(0, Math.min(max, start + dir * Math.round(trackRef.clientWidth * 0.82)));
		const t0 = performance.now();
		const dur = 360;
		const ease = (t: number) => 1 - Math.pow(1 - t, 3);
		const step = (now: number) => {
			const p = Math.min(1, (now - t0) / dur);
			trackRef.scrollLeft = start + (target - start) * ease(p);
			if (p < 1) requestAnimationFrame(step);
		};
		requestAnimationFrame(step);
	}
</script>

<section class="mt-6">
	<div class="flex items-center justify-between mb-3">
		<h2 class="font-display font-extrabold text-lg flex items-center gap-2.5">
			Matches
			{#if liveCount > 0}
				<span
					class="inline-flex items-center gap-1.5 text-[10.5px] font-bold tracking-[0.05em] px-2.5 py-1 rounded-full"
					style:background="rgba(185,28,28,0.18)"
					style:color="#f87171"
				>
					<span class="w-1.5 h-1.5 rounded-full bg-error animate-pulse"></span>
					{liveCount} LIVE
				</span>
			{/if}
		</h2>
		<a href="/results" class="text-xs font-semibold text-primary hover:underline">
			Full results →
		</a>
	</div>

	<div class="relative">
		<button
			type="button"
			class="absolute z-10 w-10 h-10 rounded-full grid place-items-center text-lg font-bold transition-colors top-1/2 -translate-y-1/2"
			style:left="-10px"
			style:background="color-mix(in srgb, var(--b2, #1C2541) 94%, transparent)"
			style:border="1px solid rgba(42,53,82,0.8)"
			style:box-shadow="0 8px 22px -8px rgba(0,0,0,0.7)"
			on:click={() => page(-1)}
			aria-label="Earlier fixtures"
		>
			‹
		</button>

		<div
			bind:this={trackRef}
			class="grid grid-flow-col grid-rows-2 gap-3 overflow-x-auto px-0.5 py-1"
			style="grid-auto-columns: minmax(248px, 1fr); scrollbar-width: none; scroll-snap-type: x proximity;"
		>
			{#each fixtures as f, i (f.id)}
				<div
					data-col={Math.floor(i / 2)}
					class="min-w-0"
					style:scroll-snap-align={i % 2 === 0 ? 'start' : 'none'}
				>
					<MissionMatchCard
						fixture={f}
						prediction={predictionByFixture.get(f.id)}
						agreement={agreementByFixture.get(f.id)}
						community={communityByFixture.get(f.id)}
						{scoringConfig}
					/>
				</div>
			{/each}
		</div>

		<button
			type="button"
			class="absolute z-10 w-10 h-10 rounded-full grid place-items-center text-lg font-bold transition-colors top-1/2 -translate-y-1/2"
			style:right="-10px"
			style:background="color-mix(in srgb, var(--b2, #1C2541) 94%, transparent)"
			style:border="1px solid rgba(42,53,82,0.8)"
			style:box-shadow="0 8px 22px -8px rgba(0,0,0,0.7)"
			on:click={() => page(1)}
			aria-label="Later fixtures"
		>
			›
		</button>
	</div>
</section>

<style>
	/* Hide scrollbar across browsers — Tailwind's scrollbar-width: none
	   covers Firefox; we need a separate ::webkit rule for Chromium/Safari. */
	section :global([class*='overflow-x-auto'])::-webkit-scrollbar {
		display: none;
	}
</style>

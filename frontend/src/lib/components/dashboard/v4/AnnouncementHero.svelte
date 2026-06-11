<script lang="ts">
	/** Rotating admin-announcement hero (V4 Dashboard).
	 *
	 *  Auto-rotates every 8s, pauses while hovered, navigates via dots
	 *  and ‹ › arrows. Falls back to a built-in welcome card when no
	 *  announcement has been published yet, so the hero never renders
	 *  empty. Tones map to the design's pill treatments: gold = matchday
	 *  headline, green = good news, mute = housekeeping. */
	import { onDestroy } from 'svelte';
	import type { Announcement } from '$lib/types/dashboard';
	import { shortDate } from '$lib/utils/dashboardV4';

	export let announcements: Announcement[] = [];

	const FALLBACK: Announcement = {
		id: 'fallback',
		tag: 'Welcome',
		tone: 'gold',
		title: 'The tournament is on',
		body: 'Follow your picks match by match — results, points and the live table all update right here as the World Cup unfolds.',
		author_name: 'The Predictor',
		published: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString()
	};

	$: cards = announcements.length > 0 ? announcements : [FALLBACK];

	let idx = 0;
	let paused = false;
	// Reset the pointer when the feed changes size (e.g. poll refresh
	// shrinks the list) so idx can't point past the end.
	$: if (idx >= cards.length) idx = 0;
	$: current = cards[idx] ?? cards[0];

	const timer = setInterval(() => {
		if (!paused && cards.length > 1) idx = (idx + 1) % cards.length;
	}, 8000);
	onDestroy(() => clearInterval(timer));

	const TONE_CLASS: Record<string, string> = {
		gold: 'bg-primary/15 text-primary',
		green: 'bg-success/20 text-success',
		mute: 'bg-base-300/50 text-base-content/70'
	};
	$: toneClass = TONE_CLASS[current.tone] ?? TONE_CLASS.gold;

	function prev() {
		idx = (idx + cards.length - 1) % cards.length;
	}
	function next() {
		idx = (idx + 1) % cards.length;
	}
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<section
	class="relative overflow-hidden rounded-box border border-primary/25 bg-base-200"
	on:mouseenter={() => (paused = true)}
	on:mouseleave={() => (paused = false)}
	aria-label="Announcements"
>
	<!-- Gold radial wash over the card surface (design token treatment) -->
	<div
		class="pointer-events-none absolute inset-0"
		style="background: radial-gradient(120% 160% at 0% -30%, hsl(var(--p) / 0.13), transparent 55%);"
	></div>

	<div class="relative flex flex-col gap-2.5 p-5">
		<div class="flex flex-wrap items-center gap-2.5">
			<span
				class="rounded-badge px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] {toneClass}"
				>{current.tag}</span
			>
			<span class="text-[11px] font-semibold text-base-content/55">
				{current.author_name} · admin · posted {shortDate(current.created_at)}
			</span>
		</div>

		<h2 class="font-hero text-3xl leading-none tracking-[0.03em] text-base-content sm:text-4xl">
			{current.title}
		</h2>
		<p class="max-w-[560px] text-[13px] leading-relaxed text-base-content/70">
			{current.body}
		</p>

		{#if cards.length > 1}
			<div class="mt-1 flex items-center justify-between">
				<span class="flex items-center gap-1.5">
					{#each cards as card, i (card.id)}
						<button
							type="button"
							class="h-[7px] rounded-full transition-all {i === idx
								? 'w-[18px] bg-primary'
								: 'w-[7px] bg-base-300 hover:bg-base-content/30'}"
							aria-label={`Announcement ${i + 1}`}
							aria-current={i === idx}
							on:click={() => (idx = i)}
						></button>
					{/each}
				</span>
				<span class="flex items-center gap-1">
					<button
						type="button"
						class="grid h-[26px] w-[26px] place-items-center rounded-btn border border-base-300/60 text-base-content/55 transition-colors hover:border-primary/50 hover:text-primary"
						aria-label="Previous announcement"
						on:click={prev}>‹</button
					>
					<button
						type="button"
						class="grid h-[26px] w-[26px] place-items-center rounded-btn border border-base-300/60 text-base-content/55 transition-colors hover:border-primary/50 hover:text-primary"
						aria-label="Next announcement"
						on:click={next}>›</button
					>
				</span>
			</div>
		{/if}
	</div>
</section>

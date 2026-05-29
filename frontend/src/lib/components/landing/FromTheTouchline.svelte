<!--
	FromTheTouchline — World Cup news strip aggregated from BBC Sport
	and Guardian Football (server-side via lib/server/news). Three
	layout zones:
	  - One large "featured" card (image left, text right) at the top
	  - A 5-card grid below for the remaining headlines
	  - A dashed "All headlines" tile at the end pointing externally

	When the news prop is empty (RSS failure or both feeds down), we
	render a single "Feed temporarily unavailable" tile so the section
	doesn't disappear — keeps page layout stable.
-->
<script lang="ts">
	import type { NewsItem } from '$lib/server/news';
	import ArrowUpRight from 'lucide-svelte/icons/arrow-up-right';
	import Rss from 'lucide-svelte/icons/rss';
	import { track } from '$lib/analytics';

	export let news: NewsItem[] = [];

	$: featured = news[0] ?? null;
	// 6 grid cards (was 5 + an "All headlines" tile) — the 6th slot is
	// now a real article instead of a generic outbound link, which is
	// both more useful and more editorially honest.
	$: gridItems = news.slice(1, 7);

	function relativeTime(iso: string): string {
		const then = new Date(iso).getTime();
		if (Number.isNaN(then)) return '';
		const diffMs = Date.now() - then;
		const minutes = Math.floor(diffMs / 60_000);
		if (minutes < 1) return 'just now';
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		if (days < 7) return `${days}d ago`;
		const weeks = Math.floor(days / 7);
		return `${weeks}w ago`;
	}

	function onCardClick(item: NewsItem, position: number) {
		track('news_card_clicked', {
			source: item.source,
			position
		});
	}
</script>

<div class="bg-base-200 border-y border-base-300/60">
	<div class="max-w-[1200px] mx-auto mobile-padding py-20 sm:py-24">
		<header class="mb-10">
			<h2 class="font-hero text-3xl sm:text-4xl tracking-wide inline-block">
				FROM THE TOUCHLINE
			</h2>
			<div class="h-0.5 w-24 bg-primary mt-2"></div>
		</header>

		{#if !featured}
			<!-- Empty state — both feeds failed -->
			<div
				class="bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-10 border border-base-100/50
					text-center text-base-content/55"
			>
				<Rss size={28} strokeWidth={1.5} class="mx-auto mb-3 opacity-60" />
				<p class="text-sm">Feed temporarily unavailable — check back in a few minutes.</p>
			</div>
		{:else}
			<!-- Featured -->
			<a
				href={featured.link}
				target="_blank"
				rel="noopener noreferrer"
				class="group block bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl
					border border-base-100/50 shadow-card overflow-hidden mb-5
					hover:border-primary/30 transition-colors"
				on:click={() => onCardClick(featured, 0)}
			>
				<div class="grid grid-cols-1 lg:grid-cols-[1.15fr_1fr]">
					<div class="aspect-[16/10] lg:aspect-auto lg:min-h-[260px] bg-base-300/40 overflow-hidden">
						{#if featured.imageUrl}
							<img
								src={featured.imageUrl}
								alt=""
								class="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-500"
								loading="lazy"
							/>
						{:else}
							<div class="w-full h-full grid place-items-center text-base-content/30">
								<Rss size={36} strokeWidth={1.25} />
							</div>
						{/if}
					</div>
					<div class="p-6 sm:p-8 flex flex-col justify-center">
						<div class="flex items-center gap-2 mb-3">
							<span
								class="text-[10px] font-mono uppercase tracking-widest text-primary font-bold"
							>
								{featured.source}
							</span>
							<span
								class="text-[10px] font-mono uppercase tracking-widest text-base-content/40"
							>
								· Featured
							</span>
						</div>
						<h3
							class="font-display text-2xl sm:text-[26px] leading-tight mb-3 text-base-content
								group-hover:text-primary transition-colors"
						>
							{featured.title}
						</h3>
						{#if featured.excerpt}
							<p class="text-sm text-base-content/70 leading-relaxed mb-4 line-clamp-3">
								{featured.excerpt}
							</p>
						{/if}
						<p class="text-xs font-mono text-base-content/45">
							{relativeTime(featured.publishedAt)}
						</p>
					</div>
				</div>
			</a>

			<!-- 5-card grid + All headlines tile -->
			<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-5">
				{#each gridItems as item, idx (item.link)}
					<a
						href={item.link}
						target="_blank"
						rel="noopener noreferrer"
						class="group flex flex-col bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl
							border border-base-100/50 shadow-card overflow-hidden
							hover:border-primary/30 transition-colors"
						on:click={() => onCardClick(item, idx + 1)}
					>
						<div class="aspect-[16/9] bg-base-300/40 overflow-hidden">
							{#if item.imageUrl}
								<img
									src={item.imageUrl}
									alt=""
									class="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-500"
									loading="lazy"
								/>
							{:else}
								<div class="w-full h-full grid place-items-center text-base-content/30">
									<Rss size={28} strokeWidth={1.25} />
								</div>
							{/if}
						</div>
						<div class="p-5 flex-1 flex flex-col">
							<div class="flex items-center justify-between mb-2">
								<span
									class="text-[10px] font-mono uppercase tracking-widest text-primary font-bold"
								>
									{item.source}
								</span>
								<ArrowUpRight
									size={14}
									strokeWidth={2}
									class="text-base-content/40 group-hover:text-primary transition-colors"
								/>
							</div>
							<h3
								class="font-display text-base leading-tight text-base-content
									group-hover:text-primary transition-colors line-clamp-3 flex-1"
							>
								{item.title}
							</h3>
							<p class="text-xs font-mono text-base-content/45 mt-3">
								{relativeTime(item.publishedAt)}
							</p>
						</div>
					</a>
				{/each}
			</div>
		{/if}
	</div>
</div>

<!--
	EntryDepth — "Two minutes or two hours" section. Three lane cards
	speaking to player styles: QUICK (Smart Fill, ~2 minutes), TINKER
	(aficionado mode, fine-tune each match), unlimited entries (run
	multiple strategies in parallel).

	Visual rhythm: distinct from HowItWorks above. Middle card slightly
	wider/raised with a gold ring, outer cards tucked under via negative
	margin + lower z-index. Hover lifts each lane by 6px. The closer
	line below the cards anchors the section's promise.
-->
<script lang="ts">
	import Zap from 'lucide-svelte/icons/zap';
	import SlidersHorizontal from 'lucide-svelte/icons/sliders-horizontal';
	import Layers3 from 'lucide-svelte/icons/layers-3';
</script>

<div class="bg-base-100">
	<div class="max-w-[1200px] mx-auto mobile-padding py-20 sm:py-24">
		<header class="text-center mb-12">
			<h2 class="font-hero text-3xl sm:text-4xl tracking-wide">
				TWO MINUTES OR TWO HOURS. YOUR CALL.
			</h2>
			<p class="text-sm text-base-content/70 mt-3 max-w-2xl mx-auto">
				Pick the depth that suits you. Every entry plays the same leaderboard.
			</p>
		</header>

		<div class="grid grid-cols-1 lg:grid-cols-[1fr_1.15fr_1fr] lg:items-stretch gap-5 lg:gap-0">
			<!-- QUICK — left lane, tucked under middle on lg+ -->
			<article
				class="relative bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-7
					border border-base-100/50 shadow-card overflow-hidden
					lg:mr-[-1.25rem] lg:z-0 lg:my-3
					hover:-translate-y-1.5 transition-transform"
			>
				<div class="flex items-center justify-between mb-4">
					<Zap size={22} strokeWidth={1.75} class="text-primary" />
					<span
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-badge bg-primary text-primary-content
							text-[10px] font-mono uppercase tracking-widest font-bold"
					>
						<Zap size={11} strokeWidth={2.5} />
						2 minutes
					</span>
				</div>
				<h3 class="font-display text-lg mb-2">Smart Fill seeds every match</h3>
				<p class="text-sm text-base-content/70 leading-relaxed">
					One click, done before your coffee's cold.
				</p>
			</article>

			<!-- TINKER — centre lane, raised + ringed -->
			<article
				class="relative bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-8
					border border-primary/20 shadow-glow-gold overflow-hidden
					lg:z-10 ring-1 ring-primary/20
					hover:-translate-y-1.5 transition-transform"
			>
				<div class="flex items-center justify-between mb-4">
					<SlidersHorizontal size={22} strokeWidth={1.75} class="text-primary" />
					<span
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-badge bg-base-100 border border-base-content/30
							text-base-content text-[10px] font-mono uppercase tracking-widest font-bold"
					>
						<SlidersHorizontal size={11} strokeWidth={2.5} />
						Aficionado mode
					</span>
				</div>
				<h3 class="font-display text-xl mb-2">Open form guides, study head-to-heads</h3>
				<p class="text-sm text-base-content/70 leading-relaxed">
					Override Smart Fill on the matches you actually care about. Save in-progress, come back
					later, tweak right up to kickoff.
				</p>
			</article>

			<!-- unlimited entries — right lane, tucked under middle on lg+ -->
			<article
				class="relative bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-7
					border border-base-100/50 shadow-card overflow-hidden
					lg:ml-[-1.25rem] lg:z-0 lg:my-3
					hover:-translate-y-1.5 transition-transform"
			>
				<div class="flex items-center justify-between mb-4">
					<Layers3 size={22} strokeWidth={1.75} class="text-primary" />
					<span
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-badge bg-primary text-primary-content
							text-[10px] font-mono uppercase tracking-widest font-bold"
					>
						<Layers3 size={11} strokeWidth={2.5} />
						More shots at the pot
					</span>
				</div>
				<h3 class="font-display text-lg mb-2">Run three entries — bold, safe, crazy</h3>
				<p class="text-sm text-base-content/70 leading-relaxed">
					No limits! Each entry appears as its own on the leaderboard.
				</p>
			</article>
		</div>

		<p class="text-center text-sm italic text-base-content/55 mt-10 max-w-2xl mx-auto">
			Every entry plays the same leaderboard. The shortcut doesn't get a head start; you do.
		</p>
	</div>
</div>

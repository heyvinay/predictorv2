<!--
	ScoringAtAGlance — compact horizontal "scorecard" panel summarising
	the three ways to earn points per match. NOT a 3-card grid; one
	rounded panel with three internal columns separated by `divide-x`
	on md+, stacking on mobile.

	"Exact score" is the hero stat — bigger Bebas Neue, mint green. The
	caption + "See full scoring rules →" link points at /rules for the
	full detail (which lives there per the existing pattern).
-->
<script lang="ts">
	import { track } from '$lib/analytics';

	function onRulesClick() {
		track('rules_link_clicked', { placement: 'scoring_at_a_glance' });
	}
</script>

<div class="bg-base-200 border-y border-base-300/60">
	<div class="max-w-[1200px] mx-auto mobile-padding py-20 sm:py-24">
		<header class="mb-8">
			<h2 class="font-hero text-3xl sm:text-4xl tracking-wide inline-block">SCORING AT A GLANCE</h2>
			<div class="h-0.5 w-24 bg-primary mt-2"></div>
		</header>

		<div
			class="bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-6 sm:p-10
				border border-base-100/50 shadow-card"
		>
			<div
				class="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-base-300/60"
			>
				<!-- Outcome -->
				<div class="text-center md:text-left px-4 py-4 md:py-2">
					<p class="text-xs font-mono uppercase tracking-widest text-base-content/55 mb-2">
						Correct outcome
					</p>
					<p class="font-hero text-4xl text-success">+5 pts</p>
				</div>

				<!-- Exact (hero stat) -->
				<div class="text-center px-4 py-4 md:py-2">
					<p class="text-xs font-mono uppercase tracking-widest text-base-content/55 mb-2">
						Exact score
					</p>
					<p class="font-hero text-6xl text-success leading-none">+10 pts</p>
				</div>

				<!-- Rarity -->
				<div class="text-center md:text-right px-4 py-4 md:py-2">
					<p class="text-xs font-mono uppercase tracking-widest text-base-content/55 mb-2">
						Rarity bonus
					</p>
					<p class="font-hero text-4xl text-primary">up to +10 pts</p>
				</div>
			</div>

			<p class="text-sm text-base-content/65 mt-6 leading-relaxed text-center md:text-left">
				Knockout rounds scale from 20 pts (R32) up to 100 pts (Final). Bonus points can make the difference.
			</p>

			<div class="mt-3 text-center md:text-left">
				<a
					href="/rules"
					class="text-sm text-primary hover:opacity-80 transition-opacity inline-flex items-center gap-1"
					on:click={onRulesClick}
				>
					See full scoring rules →
				</a>
			</div>
		</div>
	</div>
</div>

<!--
	PrizeHero — sponsor prize callout at the very top of the landing page.
	Above LandingHero. Atlas Insurance is donating an Adidas TRIONDA match
	ball to a randomly-drawn confirmed entry. Image asset lives in
	frontend/static/atlas-trionda-prize.{webp,jpg} (WebP preferred, JPG
	fallback for older mail clients and Safari < 14).
-->
<script lang="ts">
	const heroImageWebp = '/atlas-trionda-prize.webp';
	const heroImageJpg = '/atlas-trionda-prize.jpg';
</script>

<section class="relative bg-base-200 border-b border-base-300/40" aria-labelledby="prize-hero-heading">
	<div
		class="relative max-w-[1200px] mx-auto mobile-padding py-8 sm:py-10 lg:py-14
			grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-12 items-center"
	>
		<!-- ── Left column — copy ───────────────────────────────────── -->
		<div>
			<p
				class="text-xs sm:text-sm font-mono uppercase tracking-[0.18em]
					text-primary mb-2 sm:mb-3"
			>
				Prize draw
			</p>
			<h2
				id="prize-hero-heading"
				class="font-display text-[clamp(24px,4.4vw,40px)] leading-[1.05]
					tracking-tight text-base-content"
			>
				Win an official Adidas TRIONDA<br />
				FIFA World Cup 2026 match ball.
			</h2>
			<p
				class="mt-4 sm:mt-5 text-base sm:text-lg text-base-content/80 leading-relaxed"
			>
				Sign up to enter the draw — kindly donated by
				<strong class="text-base-content">Atlas Insurance</strong>. €150 value.
			</p>
			<p class="mt-3 text-sm text-base-content/55">
				Only players with a confirmed entry are eligible.
			</p>
		</div>

		<!-- ── Right column — sponsor + ball photo ──────────────────── -->
		<div class="order-first lg:order-last flex justify-center lg:justify-end">
			<picture>
				<source srcset={heroImageWebp} type="image/webp" />
				<img
					src={heroImageJpg}
					alt="Atlas Insurance is donating an official Adidas TRIONDA FIFA World Cup 2026 match ball as a prize"
					width="600"
					height="500"
					class="w-full max-w-[480px] h-auto rounded-box shadow-card"
					loading="eager"
					decoding="async"
				/>
			</picture>
		</div>
	</div>
</section>

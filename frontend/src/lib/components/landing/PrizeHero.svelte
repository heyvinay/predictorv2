<!--
	PrizeHero — sponsor prize content fragment. Renders the Atlas TRIONDA
	image and the prize copy. Designed to sit inside the LandingHero
	left column (no outer section wrapper, so the parent owns the grid
	geometry). Image asset lives in frontend/static/atlas-trionda-prize.{webp,jpg}.
-->
<script lang="ts">
	const heroImageWebp = '/atlas-trionda-prize.webp';
	const heroImageJpg = '/atlas-trionda-prize.jpg';
</script>

<div class="flex flex-col gap-4 sm:gap-5">
	<picture class="block">
		<source srcset={heroImageWebp} type="image/webp" />
		<img
			src={heroImageJpg}
			alt="Atlas Insurance is donating an official Adidas TRIONDA FIFA World Cup 2026 match ball as a prize"
			width="600"
			height="500"
			class="w-full h-auto rounded-box shadow-card"
			loading="eager"
			decoding="async"
		/>
	</picture>
	<p
		class="text-base sm:text-lg text-base-content/85 leading-relaxed"
		id="prize-hero-copy"
	>
		<strong class="text-base-content font-semibold">Sign up to win</strong>
		— kindly donated by
		<strong class="text-base-content font-semibold">Atlas Insurance</strong>.
		€150 value. Only players with a confirmed entry are eligible.
	</p>
</div>

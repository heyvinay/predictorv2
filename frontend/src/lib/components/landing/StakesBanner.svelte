<!--
	StakesBanner — the page's editorial moment. Full-width centred,
	stadium-glow radial behind, solid gold rules top and bottom. Three
	Bebas Neue lines stack vertically; the theatrical title-card.

	No icons, no card backgrounds — just typography on the dark canvas.
	The clamp() sizing gives a huge desktop headline that scales
	gracefully down to mobile without overflowing.
-->
<script lang="ts">
	// Static section — no props, no logic. Copy lives inline per the
	// /rules-page precedent.
</script>

<div class="relative overflow-hidden bg-base-100 noise">
	<!-- Stadium-glow radial behind the type -->
	<div
		class="absolute inset-0 bg-[radial-gradient(ellipse_60%_80%_at_50%_50%,rgba(212,175,55,0.10),transparent_60%)] pointer-events-none"
		aria-hidden="true"
	></div>

	<!-- Solid gold rules top/bottom -->
	<div class="border-y-2 border-primary">
		<div class="max-w-[1100px] mx-auto mobile-padding py-24 sm:py-28 text-center relative">
			<h2
				class="font-hero text-[clamp(42px,6vw,98px)] leading-[0.92] tracking-[0.01em] text-base-content"
			>
				<span class="block">€600 LAST TIME.</span>
				<span class="block text-primary">A CUT TO CHARITY.</span>
				<span class="block">THE REST IS BRAGGING RIGHTS.</span>
			</h2>
		</div>
	</div>
</div>

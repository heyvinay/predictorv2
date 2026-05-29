<!--
	LandingFooter — thin closing row. Brand mark + tagline + minimal
	links. Visible at the bottom of every landing-page view.
-->
<script lang="ts">
	import { track } from '$lib/analytics';

	function onRulesClick() {
		track('rules_link_clicked', { placement: 'footer' });
	}
</script>

<footer class="border-t border-base-300/60 bg-base-100">
	<div class="max-w-[1200px] mx-auto mobile-padding py-10 flex flex-col items-center gap-4">
		<div class="flex items-center gap-2.5">
			<img
				src="/logo.png"
				alt=""
				class="w-7 h-7 rounded-full object-cover"
				aria-hidden="true"
			/>
			<span class="font-display text-sm tracking-[0.06em] text-base-content/70 lowercase">
				atlas world cup pools
			</span>
		</div>

		<p class="text-sm text-base-content/55 text-center">
			Built for fun and one trophy.
		</p>

		<nav
			class="flex items-center gap-5 text-xs font-mono uppercase tracking-widest text-base-content/55"
			aria-label="Footer"
		>
			<a href="/rules" class="hover:text-primary transition-colors" on:click={onRulesClick}>
				Rules
			</a>
			<span class="text-base-content/20" aria-hidden="true">·</span>
			<a href="/privacy" class="hover:text-primary transition-colors">Privacy</a>
			<span class="text-base-content/20" aria-hidden="true">·</span>
			<a href="mailto:hello@atlasinsurance.com.mt" class="hover:text-primary transition-colors">
				Contact
			</a>
		</nav>
	</div>
</footer>

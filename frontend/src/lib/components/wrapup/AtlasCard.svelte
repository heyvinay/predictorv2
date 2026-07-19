<script lang="ts">
	import { theme } from '$lib/stores/theme';
</script>

<div class="stadium-card no-glow grid h-full content-center gap-1.5 p-4 text-center">
	<img
		src={$theme === 'hybrid' ? '/atlas-logo.png' : '/atlas-logo-white.png'}
		alt="Atlas Insurance"
		class="mx-auto h-8 w-auto justify-self-center"
	/>
	<p class="font-display text-2xl font-extrabold leading-none text-primary">€500</p>
	<p class="text-[13px] text-base-content/60">
		donated to charity by <b class="text-base-content">Atlas Insurance</b>, topping up the pool's
		own Soup Kitchen donation.
	</p>
	<p class="text-[11px] text-base-content/40">
		…plus the Adidas Trionda match ball (€150), the runner-up side prize.
	</p>
</div>

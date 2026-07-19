<script lang="ts">
	import { theme } from '$lib/stores/theme';
</script>

<div class="stadium-card no-glow grid h-full content-center gap-1.5 p-4 text-center">
	<img
		src={$theme === 'hybrid' ? '/atlas-logo.png' : '/atlas-logo-white.png'}
		alt="Atlas Insurance"
		class="mx-auto h-8 w-auto justify-self-center"
	/>
	<p class="text-[13px] text-base-content/60">
		A big thank you to <b class="text-base-content">Atlas Insurance</b>, who topped up our Soup
		Kitchen contribution by €500.
	</p>
	<p class="text-[13px] text-base-content/60">
		They also provided the Adidas Trionda match ball (€150) as the runner-up side prize.
	</p>
</div>

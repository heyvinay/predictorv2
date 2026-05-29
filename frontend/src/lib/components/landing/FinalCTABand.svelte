<!--
	FinalCTABand — closing call-to-action at the bottom of the page.
	Mirrors the hero's auth-aware split but more theatrical: full-width
	centred, stadium-glow, narrower max-width (900px) so the headline
	dominates. End the scroll on the strongest action.

	Authenticated: large "Enter your predictions →" gold button.
	Unauthenticated: gold "Send me a link" → scrolls to #signin (where
	the embedded SignInCard handles the actual form), with a small
	"or continue with Google" ghost link below.
-->
<script lang="ts">
	import { isAuthenticated } from '$stores/auth';
	import Mail from 'lucide-svelte/icons/mail';
	import { track } from '$lib/analytics';

	function onPrimaryClick() {
		track('cta_clicked', {
			placement: 'final_band',
			cta_label: $isAuthenticated ? 'enter_predictions' : 'sign_up',
			auth_state: $isAuthenticated ? 'authenticated' : 'guest'
		});
	}

	function onGoogleClick() {
		track('cta_clicked', {
			placement: 'final_band',
			cta_label: 'google_cta',
			auth_state: 'guest'
		});
	}
</script>

<div class="relative overflow-hidden bg-base-200 border-y border-base-300/60 noise">
	<!-- Centred stadium-glow radial -->
	<div
		class="absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_50%_50%,rgba(13,151,72,0.12),transparent_70%)] pointer-events-none"
		aria-hidden="true"
	></div>

	<div
		class="relative max-w-[900px] mx-auto mobile-padding py-24 sm:py-28 text-center"
	>
		<h2
			class="font-hero text-[clamp(46px,6.4vw,90px)] leading-[0.95] tracking-[0.01em] text-base-content"
		>
			READY TO PICK?
		</h2>

		<p class="mt-5 text-base sm:text-lg text-base-content/75 max-w-xl mx-auto leading-relaxed">
			What are you waiting for? Click and let's get started!
		</p>

		<div class="mt-8 flex flex-col items-center gap-3">
			{#if $isAuthenticated}
				<a
					href="/entries"
					class="btn btn-primary btn-lg shadow-glow-gold"
					on:click={onPrimaryClick}
				>
					Enter your predictions →
				</a>
			{:else}
				<a
					href="#signin"
					class="btn btn-primary btn-lg shadow-glow-gold gap-2"
					on:click={onPrimaryClick}
				>
					<Mail size={18} strokeWidth={2.25} />
					Send me a link
				</a>
				<a
					href="#signin"
					class="text-xs font-mono uppercase tracking-widest text-base-content/55 hover:text-primary transition-colors"
					on:click={onGoogleClick}
				>
					or continue with Google
				</a>
			{/if}
		</div>
	</div>
</div>

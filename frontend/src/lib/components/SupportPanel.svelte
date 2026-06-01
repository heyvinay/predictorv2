<script lang="ts">
	import { onMount } from 'svelte';
	import { supportOpen } from '$stores/supportPanel';
	import { user } from '$stores/auth';
	import TallyEmbed from '$components/help/TallyEmbed.svelte';

	// Tally form ID — public form URL is https://tally.so/r/D4Mbo5.
	// The notification recipient is configured inside the Tally dashboard.
	// We pass the logged-in user's email as a hidden field (ref="email" on
	// the form) so it appears in the notification body — Tally free tier
	// doesn't expose Reply-To customisation, so this is how we know who
	// sent the message.
	const SUPPORT_TALLY_FORM_ID = 'D4Mbo5';

	function close() {
		supportOpen.set(false);
	}

	onMount(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape') close();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});
</script>

{#if $supportOpen}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm"
		on:click={close}
		on:keydown={(e) => e.key === 'Enter' && close()}
		role="button"
		tabindex="-1"
		aria-label="Close support panel"
	></div>

	<!-- Slide-in side panel (right) -->
	<aside
		class="fixed top-0 right-0 z-[61] h-screen w-full max-w-md bg-base-100 border-l border-base-300/50 shadow-2xl flex flex-col"
		aria-label="Support"
		aria-modal="true"
		role="dialog"
	>
		<header class="flex items-center justify-between px-5 h-14 border-b border-base-300/50">
			<h2 class="font-display text-lg tracking-wide">Support</h2>
			<button
				class="btn btn-ghost btn-sm btn-circle"
				on:click={close}
				aria-label="Close"
			>
				<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</header>

		<div class="flex-1 flex flex-col min-h-0 p-5">
			<p class="text-sm text-base-content/60 mb-4">
				Send us a message and we'll get back to you as soon as possible.
			</p>
			<TallyEmbed
				formId={SUPPORT_TALLY_FORM_ID}
				title="Support form"
				class="flex-1 min-h-0"
				hiddenFields={{ email: $user?.email }}
			/>
		</div>
	</aside>
{/if}

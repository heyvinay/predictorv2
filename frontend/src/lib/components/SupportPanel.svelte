<script lang="ts">
	import { onMount } from 'svelte';
	import { supportOpen } from '$stores/supportPanel';

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

		<div class="flex-1 overflow-y-auto p-5">
			<!-- Placeholder card. The future Tally embed drops in here:
			     <iframe src="https://tally.so/embed/…"> -->
			<div class="card bg-base-200 border border-base-300/50">
				<div class="card-body items-center text-center py-10">
					<div class="w-12 h-12 rounded-full bg-accent/20 grid place-items-center mb-2">
						<svg class="w-6 h-6 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093M12 17h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
					</div>
					<h3 class="font-display text-xl tracking-wide">Support form coming soon</h3>
					<p class="text-sm text-base-content/60 max-w-xs">
						We're wiring this up — for now please ping Vinay directly.
					</p>
				</div>
			</div>
		</div>
	</aside>
{/if}

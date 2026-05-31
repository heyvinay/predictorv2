<!--
	ErrorModal — generic save-failure surface.

	Used for unhandled API errors that aren't lifecycle conflicts
	(network failure, 5xx, fixture-locked 409s etc.). For HTTP 409 with
	"is in status" detail, the caller routes to LifecycleConflictModal
	instead.

	Layout mirrors ConfirmModal.svelte (same backdrop + Esc + ARIA
	idioms) but with a single dismiss button and an optional collapsible
	"technical details" block — surfaces the backend detail string for
	support without showing it by default.
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';

	export let open = false;
	export let title: string = "Couldn't save your edits";
	export let message: string =
		'Something went wrong on our end. Your changes are still in this tab — please try again.';
	export let details: string | null = null;
	export let dismissLabel: string = 'OK';
	export let onDismiss: () => void = () => {};

	let showDetails = false;

	function handleDismiss() {
		showDetails = false;
		onDismiss();
	}

	function handleKey(e: KeyboardEvent) {
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			handleDismiss();
		}
	}
</script>

<svelte:window on:keydown={handleKey} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="error-modal-title"
		aria-describedby="error-modal-message"
	>
		<!-- Backdrop: tappable to dismiss. -->
		<button
			type="button"
			class="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
			tabindex="-1"
			aria-label="Close dialog"
			on:click={handleDismiss}
			transition:fade={{ duration: 150 }}
		></button>

		<div
			class="relative bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 max-w-sm w-full p-6 text-center"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			<div class="text-5xl mb-3 leading-none" aria-hidden="true">⚠️</div>

			<h2 id="error-modal-title" class="text-xl font-display font-bold mb-2">
				{title}
			</h2>

			<p id="error-modal-message" class="text-sm text-base-content/80 mb-2 whitespace-pre-line">
				{message}
			</p>

			{#if details}
				<div class="mt-3 text-left">
					<button
						type="button"
						class="text-xs text-base-content/55 hover:text-base-content underline"
						on:click={() => (showDetails = !showDetails)}
					>
						{showDetails ? 'Hide' : 'Show'} technical details
					</button>
					{#if showDetails}
						<pre
							class="mt-2 text-xs text-base-content/70 bg-base-100 rounded-lg p-2 whitespace-pre-wrap break-words max-h-32 overflow-auto">{details}</pre>
					{/if}
				</div>
			{/if}

			<div class="flex gap-2 mt-4 flex-wrap">
				<button
					type="button"
					class="btn btn-error flex-1 min-h-11 basis-28"
					on:click={handleDismiss}
				>
					{dismissLabel}
				</button>
			</div>
		</div>
	</div>
{/if}

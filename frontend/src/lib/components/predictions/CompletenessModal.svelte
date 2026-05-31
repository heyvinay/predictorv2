<!--
	CompletenessModal — fires when the user clicks Continue on a section
	that is (or whose dependent section has become) incomplete.

	The wizard's Continue button is normally gated by `canContinue`
	(reactive on the current step's `complete` flag), so the modal is a
	defense-in-depth check. The case it actually catches: the
	Bonus → Submit transition when the user damaged a previously-complete
	bracket and walked back to Bonus.

	Two buttons: "Go fix it" (primary; either closes the modal if the
	user is already on the offending section, or jumps to it) and
	"Cancel" (secondary; stays put).
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';

	export let open = false;
	export let title: string = 'Section is incomplete';
	export let missing: string[] = [];
	export let goToLabel: string = 'Go fix it';
	export let onGoTo: () => void = () => {};
	export let onCancel: () => void = () => {};

	function handleGoTo() {
		onGoTo();
	}

	function handleCancel() {
		onCancel();
	}

	function handleKey(e: KeyboardEvent) {
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			handleCancel();
		}
	}
</script>

<svelte:window on:keydown={handleKey} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="completeness-modal-title"
		aria-describedby="completeness-modal-message"
	>
		<button
			type="button"
			class="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
			tabindex="-1"
			aria-label="Close dialog"
			on:click={handleCancel}
			transition:fade={{ duration: 150 }}
		></button>

		<div
			class="relative bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 max-w-sm w-full p-6 text-center"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			<div class="text-5xl mb-3 leading-none" aria-hidden="true">📝</div>

			<h2 id="completeness-modal-title" class="text-xl font-display font-bold mb-2">
				{title}
			</h2>

			<p
				id="completeness-modal-message"
				class="text-sm text-base-content/80 mb-3"
			>
				A few things still need your attention before you can move on:
			</p>

			{#if missing.length > 0}
				<ul class="text-sm text-base-content/80 text-left list-disc list-inside mb-2 space-y-1">
					{#each missing as item}
						<li>{item}</li>
					{/each}
				</ul>
			{/if}

			<div class="flex gap-2 mt-4 flex-wrap">
				<button
					type="button"
					class="btn btn-ghost flex-1 min-h-11 basis-20"
					on:click={handleCancel}
				>
					Cancel
				</button>

				<button
					type="button"
					class="btn btn-primary flex-1 min-h-11 basis-28"
					on:click={handleGoTo}
				>
					{goToLabel}
				</button>
			</div>
		</div>
	</div>
{/if}

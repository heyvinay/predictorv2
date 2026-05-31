<!--
	MultiTabConfirmModal — gates a save when the same `(userId, entryId)`
	is open in another tab of the same browser. The detector lives in
	`$lib/utils/tabPresence` (localStorage + heartbeats); this modal is
	the confirmation surface before the actual save fires.

	Honest copy: same-browser only. Cross-device collisions (same user,
	desktop + phone) are caught by the backend lifecycle guard +
	LifecycleConflictModal — not here.

	Layout mirrors ConfirmModal.svelte. Cancel + Save anyway buttons.
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';

	export let open = false;
	export let onConfirm: () => void = () => {};
	export let onCancel: () => void = () => {};

	function handleConfirm() {
		onConfirm();
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
		aria-labelledby="multi-tab-modal-title"
		aria-describedby="multi-tab-modal-message"
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
			<div class="text-5xl mb-3 leading-none" aria-hidden="true">🪟</div>

			<h2 id="multi-tab-modal-title" class="text-xl font-display font-bold mb-2">
				Another tab is editing this entry
			</h2>

			<p
				id="multi-tab-modal-message"
				class="text-sm text-base-content/80 mb-2 whitespace-pre-line"
			>
				We've detected another browser tab editing this same entry. Saving here
				could overwrite work you've done in the other tab.
			</p>

			<p class="text-xs text-base-content/55 mb-2">
				(This detection only catches sibling tabs in the same browser — it
				won't notice a session on another device.)
			</p>

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
					class="btn btn-warning flex-1 min-h-11 basis-28"
					on:click={handleConfirm}
				>
					Save anyway
				</button>
			</div>
		</div>
	</div>
{/if}

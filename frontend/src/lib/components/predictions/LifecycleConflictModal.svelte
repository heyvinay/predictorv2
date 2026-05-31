<!--
	LifecycleConflictModal — fires when the backend rejects a save
	because the entry is no longer DRAFT (typically: another tab already
	submitted it).

	Two recovery paths:
	  - Discard my changes — drops the in-memory unsaved state + this
	    tab's sessionStorage draft. UI re-renders showing the locked/
	    submitted view.
	  - Reopen for editing — pre-deadline only; calls editEntry to
	    revert the entry to DRAFT, then the caller retries the save
	    that triggered the modal.

	Layout mirrors ConfirmModal.svelte. Cancel always present (close
	without action). Reopen button is conditional on `canReopen`
	(false post-deadline since editEntry would reject anyway).
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';

	export let open = false;
	export let entryStatus: string = 'SUBMITTED';
	export let canReopen: boolean = true;
	export let onDiscard: () => void = () => {};
	export let onReopen: () => void = () => {};
	export let onCancel: () => void = () => {};

	$: title = `This entry is now ${entryStatus.toLowerCase()}`;
	$: message = canReopen
		? `Another tab (or device) ${entryStatus === 'SUBMITTED' ? 'submitted' : 'locked in'} this entry while you were editing. Discard your changes here, or reopen the entry to keep editing — the submit will need to happen again afterwards.`
		: `Another tab (or device) ${entryStatus === 'SUBMITTED' ? 'submitted' : 'locked in'} this entry, and the deadline has now passed. You can discard your unsaved changes here; reopening for editing is no longer possible.`;

	function handleDiscard() {
		onDiscard();
	}

	function handleReopen() {
		if (!canReopen) return;
		onReopen();
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
		aria-labelledby="lifecycle-conflict-title"
		aria-describedby="lifecycle-conflict-message"
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
			<div class="text-5xl mb-3 leading-none" aria-hidden="true">🔒</div>

			<h2 id="lifecycle-conflict-title" class="text-xl font-display font-bold mb-2">
				{title}
			</h2>

			<p
				id="lifecycle-conflict-message"
				class="text-sm text-base-content/80 mb-2 whitespace-pre-line"
			>
				{message}
			</p>

			<div class="flex gap-2 mt-4 flex-wrap">
				<button
					type="button"
					class="btn btn-ghost flex-1 min-h-11 basis-20"
					on:click={handleCancel}
				>
					Cancel
				</button>

				{#if canReopen}
					<button
						type="button"
						class="btn btn-primary flex-1 min-h-11 basis-28"
						on:click={handleReopen}
					>
						Reopen for editing
					</button>
				{/if}

				<button
					type="button"
					class="btn btn-warning flex-1 min-h-11 basis-28"
					on:click={handleDiscard}
				>
					Discard my changes
				</button>
			</div>
		</div>
	</div>
{/if}

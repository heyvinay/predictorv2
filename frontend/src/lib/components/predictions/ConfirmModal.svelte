<!--
	ConfirmModal — reusable confirmation dialog.

	Designed for four use cases without code changes — only props differ:
	  - lock      (Submit / Lock In an entry)
	  - unlock    (Edit / revert to draft)
	  - delete    (currently unused per resolved decision — no user-facing
	              delete action; admins are sole irreversible actors)
	  - smart fill (Prompt 11; uses secondaryAction for the 3-button
	                "Cancel | Fill blanks only | Overwrite all" choice)

	Visual layout:
	    [icon]
	    Title
	    Message body
	    Warning (optional, amber text)
	    [Cancel] [Secondary (optional)] [Confirm]

	Backdrop: dark + blurred. Tapping it triggers `onCancel`. Escape key
	also triggers `onCancel`. Tapping the dialog itself does nothing
	(clicks don't propagate to the backdrop).

	Variant -> button class is a STATIC lookup because Tailwind's
	compiler can't see dynamic class strings (`btn-${variant}` would
	be purged).

	Transitions: backdrop fades, dialog fades + slight scale, both 150ms.
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';
	import { createEventDispatcher } from 'svelte';

	type Variant = 'primary' | 'success' | 'warning' | 'error';

	export let open = false;
	export let icon: string = '';
	export let title: string = '';
	export let message: string = '';
	export let warning: string | null = null;
	export let confirmLabel: string = 'Confirm';
	export let confirmVariant: Variant = 'primary';
	export let secondaryAction: {
		label: string;
		variant: Variant;
		onClick: () => void;
	} | null = null;
	export let onConfirm: () => void = () => {};
	export let onCancel: () => void = () => {};

	const dispatch = createEventDispatcher<{ confirm: void; cancel: void }>();

	// Static class lookup so Tailwind's JIT compiler can see all
	// four variants at build time.
	const VARIANT_CLASS: Record<Variant, string> = {
		primary: 'btn-primary',
		success: 'btn-success',
		warning: 'btn-warning',
		error: 'btn-error'
	};

	function handleConfirm() {
		dispatch('confirm');
		onConfirm();
	}

	function handleCancel() {
		dispatch('cancel');
		onCancel();
	}

	function handleSecondary() {
		if (secondaryAction) secondaryAction.onClick();
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
		aria-labelledby="confirm-modal-title"
		aria-describedby="confirm-modal-message"
	>
		<!-- Backdrop: tappable to cancel. Using a button is semantically
		     correct (it's an interactive surface) and the linter is
		     happier. The visible cancel button inside is the canonical
		     cancel action so we don't focus the backdrop. -->
		<button
			type="button"
			class="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
			tabindex="-1"
			aria-label="Close dialog"
			on:click={handleCancel}
			transition:fade={{ duration: 150 }}
		></button>

		<!-- Dialog -->
		<div
			class="relative bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 max-w-sm w-full p-6 text-center"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			{#if icon}
				<div class="text-5xl mb-3 leading-none" aria-hidden="true">{icon}</div>
			{/if}

			<h2 id="confirm-modal-title" class="text-xl font-display font-bold mb-2">
				{title}
			</h2>

			<p id="confirm-modal-message" class="text-sm text-base-content/80 mb-2 whitespace-pre-line">
				{message}
			</p>

			{#if warning}
				<p class="text-sm text-warning mb-2 whitespace-pre-line">{warning}</p>
			{/if}

			<div class="flex gap-2 mt-4 flex-wrap">
				<button
					type="button"
					class="btn btn-ghost flex-1 min-h-11 basis-20"
					on:click={handleCancel}
				>
					Cancel
				</button>

				{#if secondaryAction}
					<button
						type="button"
						class="btn flex-1 min-h-11 basis-28 {VARIANT_CLASS[secondaryAction.variant]}"
						on:click={handleSecondary}
					>
						{secondaryAction.label}
					</button>
				{/if}

				<button
					type="button"
					class="btn flex-1 min-h-11 basis-28 {VARIANT_CLASS[confirmVariant]}"
					on:click={handleConfirm}
				>
					{confirmLabel}
				</button>
			</div>
		</div>
	</div>
{/if}

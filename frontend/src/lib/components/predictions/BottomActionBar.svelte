<!--
	BottomActionBar — sticky bottom CTA strip.

	Three states (driven by `status` + `completionPct`):

	  1. draft:
	     [ Save Draft ] [ Lock In (NN%) ]
	     - Save Draft: tap -> onSaveDraft + "✓ Saved" for 2s -> resets
	     - Lock In: disabled until completionPct === 100;
	       enabled state is btn-success "🔒 Lock In"

	  2. locked (pre-deadline):
	     [ 🔒 Locked In ]  [ Unlock ]

	  3. scored / missed (post-deadline):
	     [ ✓ On Leaderboard ]   (scored)
	     [ Not Submitted ]       (missed)

	Layout:
	  - position: fixed; bottom of viewport
	  - gradient fade from transparent (top) to base-100 (bottom)
	  - safe-area-inset-bottom padding (mobile)
	  - sits above the layout's mobile bottom-nav with extra clearance

	Wires straight into existing handlers via callback props rather
	than dispatching events — the parent already has handleSubmit /
	handleEdit / handleSaveAll for the modal-confirm flows.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	/**
	 * Whether the Submit button is enabled. True only when EVERY required
	 * prediction is in: all 72 group fixtures + the full knockout bracket
	 * + every bonus question. Caller computes this; we just render it.
	 */
	export let canSubmit: boolean = false;
	/**
	 * Short human-readable summary of what's still missing when canSubmit
	 * is false — shown in the disabled button's tooltip. e.g. "3 fixtures,
	 * 5 bracket picks, 2 bonus" or null when nothing is missing.
	 */
	export let incompleteSummary: string | null = null;
	export let hasUnsavedChanges: boolean = false;
	export let savingDraft: boolean = false;
	/**
	 * Number of unsaved prediction changes since the last save. Appears
	 * in brackets next to the Save Draft label and the Discard label so
	 * the user sees the count on the buttons they're about to press.
	 */
	export let unsavedCount: number = 0;

	const dispatch = createEventDispatcher<{
		saveDraft: void;
		submit: void;
		unlock: void;
		discard: void;
	}>();
	let savedFlash = false;

	async function handleSaveDraft() {
		dispatch('saveDraft');
		// Visual confirmation flashes regardless of API latency — parent
		// owns the actual save success/failure flow.
		savedFlash = true;
		setTimeout(() => {
			savedFlash = false;
		}, 2000);
	}

	function handleDiscard() {
		dispatch('discard');
	}
</script>

<div
	class="fixed bottom-0 left-0 right-0 z-30 pointer-events-none"
	style="padding-bottom: env(safe-area-inset-bottom)"
>
	<!-- Gradient fade ABOVE the bar so content scrolls under smoothly -->
	<div class="h-8 bg-gradient-to-t from-base-100 to-transparent"></div>

	<!-- The actual bar — sits above the mobile bottom nav (~64px).
	     When there are unsaved changes, a gold glow + thin gold border
	     pulls the eye to the bar without introducing a separate banner. -->
	<div
		class="bg-base-100 pb-16 sm:pb-3 pt-2 px-3 pointer-events-auto border-t border-base-300/40 transition-[box-shadow,border-color] duration-300 ease-out
			{hasUnsavedChanges
				? 'shadow-[0_-2px_18px_-2px_rgba(212,175,55,0.55)] border-primary/40'
				: ''}"
	>
		<div class="max-w-3xl mx-auto flex items-center justify-between gap-3">
			{#if status === 'draft'}
				<!-- Left: status text -->
				<span class="text-sm text-base-content/60 truncate">
					{#if savedFlash}
						<span class="text-success font-medium">✓ Saved</span>
					{:else if savingDraft}
						<span class="text-base-content/40">Saving…</span>
					{:else if unsavedCount > 0}
						{unsavedCount} unsaved {unsavedCount === 1 ? 'change' : 'changes'}
					{/if}
				</span>
				<!-- Right: action buttons -->
				<div class="flex items-center gap-2 flex-shrink-0">
					{#if hasUnsavedChanges && !savingDraft && !savedFlash}
						<button
							type="button"
							class="btn btn-ghost btn-sm"
							on:click={handleDiscard}
							title="Discard unsaved changes"
							aria-label="Discard {unsavedCount} unsaved {unsavedCount === 1 ? 'change' : 'changes'}"
						>
							Discard
						</button>
					{/if}
					<button
						type="button"
						class="btn {savedFlash ? 'btn-success' : 'btn-outline'} btn-sm"
						on:click={handleSaveDraft}
						disabled={savingDraft || (!hasUnsavedChanges && !savedFlash)}
					>
						{#if savingDraft}
							Saving…
						{:else if savedFlash}
							✓ Saved
						{:else}
							Save Draft
						{/if}
					</button>
					<button
						type="button"
						class="btn {canSubmit ? 'btn-success' : ''} btn-sm"
						on:click={() => canSubmit && dispatch('submit')}
						disabled={!canSubmit}
						title={canSubmit
							? 'Submit your predictions'
							: incompleteSummary
								? `Complete to submit: ${incompleteSummary}`
								: 'Complete all predictions to submit'}
					>
						Submit
					</button>
				</div>
			{:else if status === 'locked'}
				<div class="flex items-center gap-2 text-success font-semibold text-sm">
					🔒 Locked In
				</div>
				<button
					type="button"
					class="btn btn-outline btn-sm"
					on:click={() => dispatch('unlock')}
				>
					Unlock
				</button>
			{:else if status === 'scored'}
				<div class="flex items-center gap-2 text-success font-semibold text-sm">
					✓ On Leaderboard
				</div>
				<span></span>
			{:else if status === 'missed'}
				<div class="flex items-center gap-2 text-error font-semibold text-sm">
					Not Submitted
				</div>
				<span></span>
			{/if}
		</div>
	</div>
</div>

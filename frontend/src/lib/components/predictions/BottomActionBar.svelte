<!--
	BottomActionBar — sticky bottom CTA strip.

	Three states (driven by `status`):

	  1. draft:
	     - Wizard mode (when `activeStep` is set):
	       [← Back to <prev>]   [Discard] [Save Draft (N)] [Continue to <next> →]
	       Submit button is suppressed — it lives in <SubmitSummary> on the
	       last step. On the Submit step itself, the Continue button is
	       suppressed too (only Back + Save Draft remain).
	     - Legacy mode (no `activeStep`):
	       [status text] [Discard] [Save Draft] [Submit]
	       Same behaviour the bar has always had — back-compat for any caller
	       that doesn't pass step props.

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
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	/**
	 * Whether the legacy Submit button is enabled. Only consulted when
	 * `activeStep` is undefined (back-compat with non-wizard callers).
	 * In wizard mode, Submit lives inside <SubmitSummary>, not here.
	 */
	export let canSubmit: boolean = false;
	/**
	 * Short human-readable summary of what's still missing when canSubmit
	 * is false — shown in the disabled button's tooltip. Only used in
	 * legacy (non-wizard) mode.
	 */
	export let incompleteSummary: string | null = null;
	export let hasUnsavedChanges: boolean = false;
	export let savingDraft: boolean = false;
	/**
	 * Number of unsaved prediction changes since the last save. Appears
	 * in brackets next to the Save Draft label and the Discard label.
	 */
	export let unsavedCount: number = 0;

	// ── Wizard-navigation props (all optional for back-compat) ───────────
	/**
	 * Current wizard step. When set, the bar switches into wizard mode
	 * (renders Back/Continue instead of the legacy status text + Submit).
	 * Undefined → legacy mode.
	 */
	export let activeStep: string | undefined = undefined;
	/** Previous step id, or null when on the first step. */
	export let prevStep: string | null = null;
	/** Next step id, or null when on the last step (Submit). */
	export let nextStep: string | null = null;
	/** Display label for the previous step (used in the Back button text). */
	export let prevStepLabel: string = '';
	/** Display label for the next step (used in the Continue button text). */
	export let nextStepLabel: string = '';
	/**
	 * Whether the user can advance from the current step. Mirrors the
	 * step's `complete` flag in the wizard's `wizardSteps` array.
	 */
	export let canContinue: boolean = false;

	const dispatch = createEventDispatcher<{
		saveDraft: void;
		submit: void;
		unlock: void;
		discard: void;
		back: void;
		continue: void;
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

	// Wizard mode is engaged when the parent passed `activeStep`. In legacy
	// mode the bar renders exactly as before so non-wizard callers (if any
	// surface later) still work without a code change.
	$: wizardMode = activeStep !== undefined;
</script>

<div
	class="fixed bottom-0 left-0 right-0 z-30 pointer-events-none"
	style="padding-bottom: env(safe-area-inset-bottom)"
>
	<!-- Gradient fade ABOVE the bar so content scrolls under smoothly -->
	<div class="h-8 bg-gradient-to-t from-base-100 to-transparent"></div>

	<!-- The actual bar — sits above the mobile bottom nav (~64px).
	     Always carries a gold top border + soft glow so the bar reads as
	     a distinct surface against scrollable content. When there are
	     unsaved changes the intensity ramps up to pull the eye to Save. -->
	<div
		class="bg-base-100 pb-16 sm:pb-3 pt-2 px-3 pointer-events-auto border-t transition-[box-shadow,border-color] duration-300 ease-out
			{hasUnsavedChanges
				? 'shadow-[0_-2px_18px_-2px_rgba(212,175,55,0.55)] border-primary/55'
				: 'shadow-[0_-1px_10px_-4px_rgba(212,175,55,0.35)] border-primary/30'}"
	>
		<div class="max-w-3xl mx-auto flex items-center justify-between gap-2 sm:gap-3 flex-wrap">
			{#if status === 'draft'}
				{#if wizardMode}
					<!-- ─── WIZARD MODE: three zones so Save sits centred ─────────
					     [left flex-1: Back] [centre: Discard + Save] [right flex-1: Continue]
					     The flex-1 side zones keep the centre group optically
					     centred regardless of Back/Continue button widths. -->
					<!-- Left zone: Back (or empty to preserve centring). -->
					<div class="flex-1 flex justify-start min-w-0">
						{#if prevStep}
							<button
								type="button"
								class="btn btn-ghost btn-sm gap-1 whitespace-nowrap"
								on:click={() => dispatch('back')}
							>
								<span aria-hidden="true">←</span>
								<span class="hidden sm:inline">Back to {prevStepLabel}</span>
								<span class="sm:hidden">Back</span>
							</button>
						{/if}
					</div>

					<!-- Centre zone: Discard (quiet) + Save (prominent when dirty). -->
					<div class="flex items-center gap-2 flex-shrink-0">
						{#if hasUnsavedChanges && !savingDraft && !savedFlash}
							<button
								type="button"
								class="btn btn-ghost btn-xs font-normal text-base-content/50 hover:text-base-content"
								on:click={handleDiscard}
								title="Discard unsaved changes"
								aria-label="Discard {unsavedCount} unsaved {unsavedCount === 1 ? 'change' : 'changes'}"
							>
								Discard
							</button>
						{/if}
						<button
							type="button"
							class="btn btn-sm whitespace-nowrap {savedFlash
								? 'btn-success'
								: hasUnsavedChanges
									? 'btn-primary shadow-glow-gold'
									: 'btn-outline'}"
							on:click={handleSaveDraft}
							disabled={savingDraft || (!hasUnsavedChanges && !savedFlash)}
						>
							{#if savingDraft}
								Saving…
							{:else if savedFlash}
								✓ Saved
							{:else if unsavedCount > 0}
								Save&nbsp;({unsavedCount})
							{:else}
								Save
							{/if}
						</button>
					</div>

					<!-- Right zone: Continue button on intermediate steps. On the
					     Submit step (no nextStep), the explicit "Submit Entry"
					     button lives inside <SubmitSummary>, which sits below the
					     fold — show a small italic hint so users always know
					     where to find it even if the in-card scroll-cue misses. -->
					<div class="flex-1 flex justify-end min-w-0">
						{#if nextStep}
							<button
								type="button"
								class="btn btn-primary btn-sm gap-1 whitespace-nowrap"
								on:click={() => dispatch('continue')}
								disabled={!canContinue}
								title={canContinue
									? `Continue to ${nextStepLabel}`
									: 'Finish this step first'}
							>
								<span class="hidden sm:inline">Continue to {nextStepLabel}</span>
								<span class="sm:hidden">Continue</span>
								<span aria-hidden="true">→</span>
							</button>
						{:else}
							<span class="text-xs italic text-base-content/60 whitespace-nowrap">
								Scroll down to submit ↓
							</span>
						{/if}
					</div>
				{:else}
					<!-- ─── LEGACY MODE: status text on left, Save + Submit on right ───── -->
					<span class="text-sm text-base-content/60 truncate">
						{#if savedFlash}
							<span class="text-success font-medium">✓ Saved</span>
						{:else if savingDraft}
							<span class="text-base-content/40">Saving…</span>
						{:else if unsavedCount > 0}
							{unsavedCount} unsaved {unsavedCount === 1 ? 'change' : 'changes'}
						{/if}
					</span>
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
				{/if}
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

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
	export let completionPct: number = 0;
	export let hasUnsavedChanges: boolean = false;
	export let savingDraft: boolean = false;

	const dispatch = createEventDispatcher<{
		saveDraft: void;
		lockIn: void;
		unlock: void;
	}>();

	$: lockInEnabled = completionPct === 100;
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
</script>

<div
	class="fixed bottom-0 left-0 right-0 z-30 pointer-events-none"
	style="padding-bottom: env(safe-area-inset-bottom)"
>
	<!-- Gradient fade ABOVE the bar so content scrolls under smoothly -->
	<div class="h-8 bg-gradient-to-t from-base-100 to-transparent"></div>

	<!-- The actual bar — sits above the mobile bottom nav (~64px) -->
	<div class="bg-base-100 pb-16 sm:pb-3 pt-2 px-3 pointer-events-auto border-t border-base-300/40">
		<div class="max-w-3xl mx-auto flex gap-2">
			{#if status === 'draft'}
				<button
					type="button"
					class="btn flex-1 min-h-12 {savedFlash ? 'btn-success' : 'btn-outline'}"
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
					class="btn flex-1 min-h-12 {lockInEnabled ? 'btn-success' : 'btn-disabled'}"
					on:click={() => lockInEnabled && dispatch('lockIn')}
					disabled={!lockInEnabled}
					title={lockInEnabled ? 'Lock in your predictions' : `Complete all fixtures to unlock (${completionPct}%)`}
				>
					🔒 Lock In{lockInEnabled ? '' : ` (${completionPct}%)`}
				</button>
			{:else if status === 'locked'}
				<div
					class="flex-1 flex items-center justify-center gap-2 min-h-12 rounded-lg bg-success/10 border border-success/40 text-success font-semibold"
				>
					🔒 Locked In
				</div>
				<button
					type="button"
					class="btn btn-outline flex-1 min-h-12"
					on:click={() => dispatch('unlock')}
				>
					Unlock
				</button>
			{:else if status === 'scored'}
				<div
					class="flex-1 flex items-center justify-center gap-2 min-h-12 rounded-lg bg-success/10 border border-success/40 text-success font-semibold"
				>
					✓ On Leaderboard
				</div>
			{:else if status === 'missed'}
				<div
					class="flex-1 flex items-center justify-center gap-2 min-h-12 rounded-lg bg-error/10 border border-error/40 text-error font-semibold"
				>
					Not Submitted
				</div>
			{/if}
		</div>
	</div>
</div>

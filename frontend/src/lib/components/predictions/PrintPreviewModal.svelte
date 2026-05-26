<!--
	PrintPreviewModal — dual-use summary of all predictions.

	Used for:
	  (a) Pre-submission "confirm everything on one page" review
	  (b) Post-submission permanent record

	The recap body itself lives in EntryRecapBody.svelte so this modal and
	the in-page SubmitSummary stay in sync. This file owns only the modal
	chrome (backdrop, header bar, scroll container, Print button) and the
	print stylesheet target.

	Print: window.print() + @media print in app.css hides all chrome except
	the .print-preview-target div.
-->
<script lang="ts">
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';
	import EntryRecapBody from './EntryRecapBody.svelte';

	export let open: boolean = false;
	export let entryName: string = '';
	export let entryRef: string = '';
	export let playerName: string = '';
	export let groupFixtures: FixturesByGroup[] = [];
	/** Map of fixture_id → { home: string; away: string } (may be empty string for no pick) */
	export let scoreValueMap: Map<string, { home: string; away: string }> = new Map();
	export let displayBracket: BracketPrediction | null = null;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: Map<string, string> = new Map();
	export let onClose: () => void = () => {};

	function handlePrint() {
		window.print();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4"
		on:click|self={onClose}
		on:keydown={handleKeydown}
	>
		<!-- Modal shell -->
		<div class="bg-base-100 w-full sm:max-w-2xl sm:rounded-xl flex flex-col max-h-[90dvh] sm:max-h-[85dvh]">
			<!-- Header bar -->
			<div class="flex items-center justify-between px-4 py-3 border-b border-base-300/50 flex-shrink-0">
				<span class="font-display text-base tracking-wide">Prediction Summary</span>
				<button type="button" class="btn btn-ghost btn-sm btn-square" on:click={onClose} aria-label="Close">
					<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Scrollable content — this div gets the print-preview-target class
			     so the @media print stylesheet in app.css can scope to it. The
			     actual recap markup is delegated to EntryRecapBody (mode='print'). -->
			<div class="print-preview-target overflow-y-auto flex-1 px-4 py-4 text-sm">
				<EntryRecapBody
					mode="print"
					showEditLinks={false}
					{entryName}
					{entryRef}
					{playerName}
					{groupFixtures}
					{scoreValueMap}
					{displayBracket}
					{bonusQuestions}
					{bonusAnswers}
				/>
			</div>

			<!-- Footer: Close + Print -->
			<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/50 flex-shrink-0">
				<button type="button" class="btn btn-ghost btn-sm" on:click={onClose}>Close</button>
				<button type="button" class="btn btn-outline btn-sm gap-1" on:click={handlePrint}>
					🖨 Print
				</button>
			</div>
		</div>
	</div>
{/if}

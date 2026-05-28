<!--
	PrintPreviewModal — read-only recap of all predictions.

	The wizard's Submit step now hosts its own inline submission UI inside
	SubmitSummary (see plan R9). This modal is purely a printable receipt:
	the user clicks the "🖨 Print" button to open it, sees the full recap
	(R6: identity header + groups + knockouts as "Team A vs Team B" with
	the winner bolded + bonus), and either Close or Print.

	Print: window.print() + @media print in app.css hides all chrome except
	the .print-preview-target div (R8: visibility-based pattern).
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';
	import type { GroupStandingsMap } from '$lib/utils/bracketResolver';
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

	/** R6: resolve knockout fixtures into concrete "Team A vs Team B" rows. */
	export let groupStandings: GroupStandingsMap | null = null;

	/** R6: receipt-style header block (Ref / Status / Rendered on). */
	export let submissionMeta: {
		status: 'draft' | 'submitted' | 'withdrawn';
		statusAt: string;
	} | null = null;

	// Scroll-cue (still helpful for the modal's fixed-height scroll region).
	let scrollEl: HTMLDivElement | null = null;
	let arrowVisible = false;
	let arrowFading = false;

	function checkScrollable() {
		if (!scrollEl) return;
		arrowVisible = scrollEl.scrollHeight > scrollEl.clientHeight + 1;
		arrowFading = false;
	}

	function onScroll() {
		if (!scrollEl || !arrowVisible || arrowFading) return;
		if (scrollEl.scrollTop > 0) {
			arrowFading = true;
			setTimeout(() => {
				arrowVisible = false;
			}, 900);
		}
	}

	$: if (open) {
		void tick().then(checkScrollable);
	}

	// Print portal: the print target lives deep inside the modal shell, so
	// CSS-only print rules (display/visibility tricks) can't anchor it to
	// the page reliably — absolute positioning resolves to the modal's
	// centred container, which gives huge top whitespace and breaks grid
	// page-flow. Instead, on `beforeprint` we MOVE the .print-preview-target
	// node to be a direct body child, then restore it on `afterprint`.
	// The print CSS becomes trivial: hide every other body child.
	let originalParent: HTMLElement | null = null;
	let originalNextSibling: Node | null = null;

	function beforePrint() {
		if (!scrollEl || scrollEl.parentElement === document.body) return;
		originalParent = scrollEl.parentElement;
		originalNextSibling = scrollEl.nextSibling;
		document.body.appendChild(scrollEl);
	}

	function afterPrint() {
		if (scrollEl && originalParent) {
			originalParent.insertBefore(scrollEl, originalNextSibling);
			originalParent = null;
			originalNextSibling = null;
		}
	}

	onMount(() => {
		window.addEventListener('beforeprint', beforePrint);
		window.addEventListener('afterprint', afterPrint);
		return () => {
			window.removeEventListener('beforeprint', beforePrint);
			window.removeEventListener('afterprint', afterPrint);
		};
	});

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
		<div class="bg-base-100 w-full sm:max-w-2xl sm:rounded-xl flex flex-col max-h-[90dvh] sm:max-h-[85dvh] relative">
			<!-- Header bar -->
			<div class="flex items-center justify-between px-4 py-3 border-b border-base-300/50 flex-shrink-0 print:hidden">
				<span class="font-display text-base tracking-wide">Prediction Summary</span>
				<button type="button" class="btn btn-ghost btn-sm btn-square" on:click={onClose} aria-label="Close">
					<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Scrollable recap. `.print-preview-target` scopes the print CSS;
			     `scrollEl` doubles as the ref the beforeprint hook moves to body. -->
			<div
				class="print-preview-target overflow-y-auto flex-1 px-4 py-4 text-sm relative"
				bind:this={scrollEl}
				on:scroll={onScroll}
			>
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
					{groupStandings}
					{submissionMeta}
				/>
			</div>

			<!-- Scroll-cue arrow. -->
			{#if arrowVisible}
				<div
					class="scroll-cue print:hidden"
					class:fading={arrowFading}
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</div>
			{/if}

			<!-- Footer: Close + Print. Hidden on print. -->
			<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/50 flex-shrink-0 print:hidden">
				<button type="button" class="btn btn-ghost btn-sm" on:click={onClose}>Close</button>
				<button type="button" class="btn btn-outline btn-sm gap-1" on:click={handlePrint}>
					🖨 Print
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.scroll-cue {
		position: absolute;
		bottom: 70px; /* sit just above the bottom chrome footer */
		left: 50%;
		transform: translateX(-50%);
		width: 32px;
		height: 32px;
		color: rgba(255, 255, 255, 0.85);
		background-color: rgba(0, 0, 0, 0.35);
		border-radius: 9999px;
		display: grid;
		place-items: center;
		padding: 6px;
		pointer-events: none;
		opacity: 0.75;
		transition: opacity 800ms ease-out;
		animation: cue-bounce 1.5s ease-in-out infinite;
		z-index: 1;
	}
	.scroll-cue svg {
		width: 100%;
		height: 100%;
	}
	.scroll-cue.fading {
		opacity: 0;
	}
	@keyframes cue-bounce {
		0%, 100% {
			transform: translate(-50%, 0);
		}
		50% {
			transform: translate(-50%, 6px);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.scroll-cue {
			animation: none;
		}
	}
</style>

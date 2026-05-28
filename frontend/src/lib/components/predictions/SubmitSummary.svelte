<!--
	SubmitSummary — wizard Submit step body.

	**Draft state** is one tall scrollable card mirroring Print Preview:
	  · Embedded EntryRecapBody (header + groups + knockouts as "Team A vs
	    Team B" with the winner bolded + bonus).
	  · Disclaimer paragraphs.
	  · paid_to text input (pre-filled from $user.paid_to).
	  · Responsibility checkbox.
	  · Submit Entry button (disabled until paid_to + checkbox + completion
	    gate all clear).
	  · Scroll-cue chevron-down at the bottom edge of the scroll, fades on
	    first scroll, respects prefers-reduced-motion.

	**Other states** (locked / scored / missed) keep the simpler two-card
	layout: a recap card on top and a status panel below — no form is
	needed once the entry is past draft.

	Events dispatched:
	  · editStep — passthrough from EntryRecapBody when user clicks an Edit link
	  · submit   — user clicked Submit Entry; payload { paidTo: string }
	  · unlock   — user clicked Unlock to edit (locked state)
-->
<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';
	import type { GroupStandingsMap } from '$lib/utils/bracketResolver';
	import { user } from '$stores/auth';
	import { defaultPaidTo } from '$lib/utils/onboarding';
	import EntryRecapBody from './EntryRecapBody.svelte';

	// ── Recap data (passed straight through to EntryRecapBody) ────────────
	export let entryName: string = '';
	export let entryRef: string = '';
	export let playerName: string = '';
	export let groupFixtures: FixturesByGroup[] = [];
	export let scoreValueMap: Map<string, { home: string; away: string }> = new Map();
	export let displayBracket: BracketPrediction | null = null;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: Map<string, string> = new Map();

	// ── R6 props (knockout matchup resolution + identity-grid header) ─────
	export let groupStandings: GroupStandingsMap | null = null;
	export let submissionMeta: {
		status: 'draft' | 'submitted' | 'withdrawn';
		statusAt: string;
	} | null = null;

	// ── R9 props (inline submit form) ─────────────────────────────────────
	export let userPaidTo: string | null = null;
	export let submitBusy: boolean = false;

	// ── Submission state ──────────────────────────────────────────────────
	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	/** True only when every section is complete (mirrors `phase1AllComplete`). */
	export let canSubmit: boolean = false;
	/** ISO timestamp when the entry was last submitted (locked state). */
	export let submittedAt: string | null = null;
	/** Whether the user can still unlock to edit (true while deadline is in the future). */
	export let canUnlock: boolean = false;

	const dispatch = createEventDispatcher<{
		editStep: { step: 'groups' | 'knockout' | 'bonus' };
		submit: { paidTo: string };
		unlock: void;
	}>();

	function fmtSubmittedAt(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		return d.toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	// ── Inline submit form state ──────────────────────────────────────────
	// paidToInput is pre-filled from defaultPaidTo($user) — which falls back
	// to company_contact when employer === 'neither' (R10.4). The user can
	// override before submitting; we only persist what they keep.
	let paidToInput = '';
	let acknowledged = false;
	let initialised = false;
	$: if (!initialised && $user) {
		paidToInput = defaultPaidTo($user);
		initialised = true;
	}
	$: paidToTrimmed = paidToInput.trim();
	$: canConfirm =
		canSubmit && !!paidToTrimmed && acknowledged && !submitBusy;

	function handleSubmitClick() {
		if (!canConfirm) return;
		dispatch('submit', { paidTo: paidToTrimmed });
	}

	// ── Scroll-cue ────────────────────────────────────────────────────────
	// Inline-on-page content arrives over multiple ticks (group fixtures,
	// bonus questions, bracket state). A one-shot measurement runs before
	// the tree has fully grown → it would say "no overflow" and the arrow
	// never shows. A ResizeObserver on the scrollable element re-evaluates
	// every time content height changes, which is the real signal.
	let scrollEl: HTMLDivElement | null = null;
	let arrowVisible = false;
	let arrowFading = false;
	let resizeObserver: ResizeObserver | null = null;
	let userHasScrolled = false;

	function checkScrollable() {
		if (!scrollEl) return;
		// Don't re-show after the user has already scrolled — once dismissed,
		// it stays dismissed (otherwise content changes would re-trigger it
		// repeatedly, which is annoying).
		if (userHasScrolled) return;
		arrowVisible = scrollEl.scrollHeight > scrollEl.clientHeight + 1;
		arrowFading = false;
	}

	function onScroll() {
		if (!scrollEl || !arrowVisible || arrowFading) return;
		if (scrollEl.scrollTop > 0) {
			userHasScrolled = true;
			arrowFading = true;
			setTimeout(() => {
				arrowVisible = false;
			}, 900);
		}
	}

	onMount(() => {
		// Initial check after the first paint, in case ResizeObserver doesn't
		// fire because the element starts at its eventual size.
		requestAnimationFrame(checkScrollable);

		// Re-check whenever the scrollable's content height changes.
		if (typeof ResizeObserver !== 'undefined' && scrollEl) {
			resizeObserver = new ResizeObserver(() => checkScrollable());
			resizeObserver.observe(scrollEl);
			// Also observe the first child (the recap content) — height
			// changes there don't always trigger a ResizeObserver on the
			// scroll container itself when overflow is involved.
			const inner = scrollEl.firstElementChild;
			if (inner) resizeObserver.observe(inner);
		}

		return () => {
			resizeObserver?.disconnect();
			resizeObserver = null;
		};
	});
</script>

{#if status === 'draft'}
	<!-- Draft: one comprehensive scrollable card with recap + disclaimer + form. -->
	<div class="stadium-card no-glow p-0 relative">
		<div
			class="max-h-[80vh] overflow-y-auto relative p-4 sm:p-6"
			bind:this={scrollEl}
			on:scroll={onScroll}
		>
			<EntryRecapBody
				mode="review"
				showEditLinks={true}
				showStatus={false}
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
				on:editStep
			/>

			<!-- Disclaimer + form, anchored to the bottom of the scroll. -->
			<div class="mt-8 pt-6 border-t-2 border-base-content/20">
				<h3 class="font-display text-lg tracking-wide mb-3">Ready to submit?</h3>

				<p class="text-xs leading-relaxed text-base-content/70">
					You're about to lock in <strong>"{entryName}"</strong> for scoring. You can edit your
					submission any time before the competition starts. Once it begins, your submission is
					final — it cannot be edited, withdrawn, or replaced. Organisers are not responsible for
					any incorrect submissions. Points will be assigned based on your picks as submitted.
				</p>

				<div class="form-control mt-5">
					<label class="label py-1" for="submit-paid-to">
						<span class="label-text text-xs uppercase tracking-wider text-base-content/60 flex items-center gap-2">
							Name of the person you paid the fee to
							<span
								class="tooltip tooltip-top normal-case tracking-normal"
								data-tip="Atlas or JMFA staff: see the email you received and enter the name of the person you've paid (or plan to pay). Everyone else: enter the name of your Atlas or JMFA contact."
							>
								<span class="text-base-content/40 cursor-help text-sm" aria-label="Help">ⓘ</span>
							</span>
						</span>
					</label>
					<input
						id="submit-paid-to"
						type="text"
						class="input input-bordered w-full max-w-md"
						placeholder="Required"
						bind:value={paidToInput}
						maxlength="100"
						disabled={submitBusy}
					/>
				</div>

				<label class="flex items-start gap-2 mt-4 cursor-pointer">
					<input
						type="checkbox"
						class="checkbox checkbox-primary mt-0.5"
						bind:checked={acknowledged}
						disabled={submitBusy}
					/>
					<span class="text-sm leading-snug">
						I have reviewed my picks and take responsibility for this submission.
					</span>
				</label>

				{#if !canSubmit}
					<p class="text-sm text-warning mt-4">
						Please complete your predictions and bonus questions before submitting.
					</p>
				{/if}

				<div class="flex items-center justify-end mt-5">
					<button
						type="button"
						class="btn btn-primary btn-lg shadow-glow-gold whitespace-nowrap"
						disabled={!canConfirm}
						on:click={handleSubmitClick}
					>
						{#if submitBusy}
							<span class="loading loading-spinner loading-sm"></span>
							Submitting…
						{:else}
							Submit Entry
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- Scroll-cue chevron at the bottom edge of the scroll. -->
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
	</div>
{:else}
	<!-- Locked / scored / missed: simpler two-card layout (recap + status). -->
	<div class="space-y-6">
		<div class="stadium-card no-glow p-4 sm:p-6">
			<EntryRecapBody
				mode="review"
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
				on:editStep
			/>
		</div>

		<div class="stadium-card no-glow p-4 sm:p-6">
			{#if status === 'locked'}
				<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
					<div class="min-w-0">
						<h3 class="font-display text-lg tracking-wide text-success">
							✓ Submitted{#if submittedAt} · {fmtSubmittedAt(submittedAt)}{/if}
						</h3>
						<p class="text-sm text-base-content/60 mt-1">
							Your entry is locked in. {#if canUnlock}You can unlock to make changes until the deadline.{:else}The deadline has passed — predictions are final.{/if}
						</p>
					</div>
					{#if canUnlock}
						<button
							type="button"
							class="btn btn-outline btn-warning whitespace-nowrap"
							on:click={() => dispatch('unlock')}
						>
							Unlock to edit
						</button>
					{/if}
				</div>
			{:else if status === 'scored'}
				<div class="flex items-center gap-3">
					<span class="text-2xl">🏆</span>
					<div>
						<h3 class="font-display text-lg tracking-wide text-success">Live on the leaderboard</h3>
						<p class="text-sm text-base-content/60">
							Tournament has started — your predictions are being scored as results come in.
						</p>
					</div>
				</div>
			{:else if status === 'missed'}
				<div class="flex items-center gap-3">
					<span class="text-2xl text-error">⚠</span>
					<div>
						<h3 class="font-display text-lg tracking-wide text-error">Not submitted before the deadline</h3>
						<p class="text-sm text-base-content/60">
							This entry didn't make it in. No points will be awarded.
						</p>
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.scroll-cue {
		position: absolute;
		bottom: 18px;
		left: 50%;
		transform: translateX(-50%);
		width: 32px;
		height: 32px;
		color: rgba(255, 255, 255, 0.9);
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

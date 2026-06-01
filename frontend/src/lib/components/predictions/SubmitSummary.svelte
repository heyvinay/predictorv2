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
	  · newEntry — user clicked "+ New Entry" (locked state). Parent should
	               call createEntry() and navigate to the new entry. Only
	               fires when `canCreateNewEntry` prop is true (parent
	               computes from entries.length < max_entries_per_user).
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
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
	/** True when the user has room to create another entry under the
	 *  competition's max_entries_per_user cap. Computed by the parent from
	 *  entries.length < settings.max_entries_per_user. Drives whether the
	 *  "+ New Entry" CTA renders on the locked card. Default false so the
	 *  CTA stays hidden until the parent has loaded settings + entries. */
	export let canCreateNewEntry: boolean = false;

	const dispatch = createEventDispatcher<{
		editStep: { step: 'groups' | 'knockout' | 'bonus' };
		submit: { paidTo: string };
		unlock: void;
		newEntry: void;
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

	// Note: previously this component wrapped its content in a
	// `max-h-[80vh] overflow-y-auto` container with a ResizeObserver-driven
	// scroll-cue chevron. Removed 2026-06-01 — the inner scroll buried the
	// Submit Entry button below the fold and created a double-scrollbar UX.
	// Submit now flows with the page like every other wizard step.
</script>

{#if status === 'draft'}
	<!-- Draft: one comprehensive card with recap + disclaimer + form, flowing
	     with the page. No inner scroll — Submit Entry lives at natural page
	     bottom so a single page scroll reaches it. Panel composition matches
	     the new bonus-card lift (rounded-xl + bg-base-200 + shadow-card) so
	     the Submit step's surface reads consistently with the Bonus step. -->
	<div class="rounded-xl border bg-base-200 shadow-card p-4 sm:p-6 relative">
		<!-- Top-of-step warning banner: completing all four wizard steps does
		     NOT enter the user in the competition. Until they tick the
		     acknowledgement checkbox AND tap Submit Entry, the entry is a
		     draft. This message is restated by the disclaimer block at the
		     bottom of the card — surfacing it here means skim-readers hit it
		     at least once. Always rendered in the draft branch, regardless
		     of pick-completion state (covers both "early arrival on Submit"
		     and "all picks done, hovering on the button"). -->
		<div role="alert" class="alert alert-warning mb-6">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="stroke-current shrink-0 h-6 w-6"
				fill="none"
				viewBox="0 0 24 24"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4a2 2 0 00-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z"
				/>
			</svg>
			<div>
				<h4 class="font-semibold text-base">Almost there — but you're not entered yet.</h4>
				<p class="text-sm leading-snug mt-1">
					Your picks are saved but won't count for scoring or prizes until you tick the acknowledgement box and tap <strong>Submit Entry</strong> below. Until then, your entry is just a draft.
				</p>
			</div>
		</div>

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

		<!-- Disclaimer + form, anchored to the bottom of the card. -->
		<div class="mt-8 pt-6 border-t-2 border-base-content/20">
			<h3 class="font-display text-lg tracking-wide mb-3">Ready to submit?</h3>

			<p class="text-xs leading-relaxed text-base-content/70">
				Your picks are saved as a draft. To enter <strong>"{entryName}"</strong> in the
				competition you must tick the box below and tap <strong>Submit Entry</strong> —
				without both, your picks won't be scored and you're not eligible for prizes.
				You can edit any time before kickoff; after that, your submission is final.
				Organisers are not responsible for any incorrect submissions.
			</p>

			<div class="form-control mt-5">
				<label class="label py-1" for="submit-paid-to">
					<span class="label-text text-xs uppercase tracking-wider text-base-content/60 flex items-center gap-2">
						Name of the person you paid the fee to
						<!-- tooltip-left (not tooltip-top) because the trigger sits at
						     the right edge of the label row — a top-centered bubble
						     clips past the viewport. Left-anchored bubble extends into
						     the card's empty space and stays fully visible. -->
						<span
							class="tooltip tooltip-left normal-case tracking-normal"
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
				<p class="text-sm text-warning-text mt-4">
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
{:else}
	<!-- Locked / scored / missed: simpler two-card layout (recap + status). -->
	<div class="space-y-6">
		<div class="rounded-xl border bg-base-200 shadow-card p-4 sm:p-6">
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

		<div class="rounded-xl border bg-base-200 shadow-card p-4 sm:p-6">
			{#if status === 'locked'}
				<!-- Locked card: status text + action group. Up to three CTAs
				     (Back / Unlock / New Entry). Stack vertically on mobile,
				     row on desktop. Gold on "+ New Entry" makes the
				     forward-looking action the visual default; warning amber
				     reserved for the state-changing Unlock; ghost on Back so
				     the eye doesn't have to compete. -->
				<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
					<div class="min-w-0">
						<h3 class="font-display text-lg tracking-wide text-success">
							✓ Submitted{#if submittedAt} · {fmtSubmittedAt(submittedAt)}{/if}
						</h3>
						<p class="text-sm text-base-content/60 mt-1">
							Your entry is locked in. {#if canUnlock}You can unlock to make changes until the deadline.{:else}The deadline has passed — predictions are final.{/if}
						</p>
					</div>
					<div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:flex-wrap sm:justify-end">
						<a
							href="/entries"
							class="btn btn-ghost whitespace-nowrap"
						>
							Back to Entries
						</a>
						{#if canUnlock}
							<button
								type="button"
								class="btn btn-warning whitespace-nowrap"
								on:click={() => dispatch('unlock')}
							>
								Unlock to edit
							</button>
						{/if}
						{#if canCreateNewEntry}
							<button
								type="button"
								class="btn btn-primary shadow-glow-gold whitespace-nowrap"
								on:click={() => dispatch('newEntry')}
							>
								+ New Entry
							</button>
						{/if}
					</div>
				</div>
			{:else if status === 'scored'}
				<!-- Scored card: tournament has started. No more actions
				     possible; only return-to-list. Back gets the primary
				     gold treatment since it's the sole action. -->
				<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
					<div class="flex items-center gap-3 min-w-0">
						<span class="text-2xl">🏆</span>
						<div>
							<h3 class="font-display text-lg tracking-wide text-success">Live on the leaderboard</h3>
							<p class="text-sm text-base-content/60">
								Tournament has started — your predictions are being scored as results come in.
							</p>
						</div>
					</div>
					<a
						href="/entries"
						class="btn btn-primary shadow-glow-gold whitespace-nowrap"
					>
						Back to Entries
					</a>
				</div>
			{:else if status === 'missed'}
				<!-- Missed card: same shape as scored — entry didn't make
				     the deadline; only path back is to the list. -->
				<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
					<div class="flex items-center gap-3 min-w-0">
						<span class="text-2xl text-error">⚠</span>
						<div>
							<h3 class="font-display text-lg tracking-wide text-error">Not submitted before the deadline</h3>
							<p class="text-sm text-base-content/60">
								This entry didn't make it in. No points will be awarded.
							</p>
						</div>
					</div>
					<a
						href="/entries"
						class="btn btn-primary shadow-glow-gold whitespace-nowrap"
					>
						Back to Entries
					</a>
				</div>
			{/if}
		</div>
	</div>
{/if}

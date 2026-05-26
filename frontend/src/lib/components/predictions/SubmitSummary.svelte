<!--
	SubmitSummary — wizard Submit step body.

	Thin wrapper around EntryRecapBody (mode='review' with edit-links on) plus a
	submission-status panel that adapts to the entry's lifecycle:
	  draft  → "Ready to submit?" + Submit Entry button (disabled if incomplete)
	  locked → "Submitted at …" + Unlock to edit (gated on deadline)
	  scored → "On the leaderboard" muted state
	  missed → "Not submitted before deadline" error state

	Events dispatched:
	  · editStep — passthrough from EntryRecapBody when user clicks an Edit link
	  · submit   — user clicked the Submit Entry button
	  · unlock   — user clicked the Unlock to edit button
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';
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

	// ── Submission state ──────────────────────────────────────────────────
	/** Entry's lifecycle status. Drives the submission panel variant. */
	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	/** True only when every section is complete (mirrors `phase1AllComplete`). */
	export let canSubmit: boolean = false;
	/**
	 * Human-readable description of what's still missing — e.g.
	 * "3 fixtures, 5 bracket picks, 2 bonus answers". Used as the tooltip on
	 * the disabled Submit button so the user knows what's blocking them.
	 */
	export let incompleteSummary: string | null = null;
	/** ISO timestamp when the entry was last submitted (locked state). */
	export let submittedAt: string | null = null;
	/** Whether the user can still unlock to edit (true while deadline is in the future). */
	export let canUnlock: boolean = false;

	const dispatch = createEventDispatcher<{
		editStep: { step: 'groups' | 'knockout' | 'bonus' };
		submit: void;
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
</script>

<div class="space-y-6">
	<!-- The recap (groups + bracket + bonus) with Edit links per section. -->
	<div class="stadium-card no-glow p-4 sm:p-6">
		<EntryRecapBody
			mode="review"
			showEditLinks={status === 'draft'}
			{entryName}
			{entryRef}
			{playerName}
			{groupFixtures}
			{scoreValueMap}
			{displayBracket}
			{bonusQuestions}
			{bonusAnswers}
			on:editStep
		/>
	</div>

	<!-- Submission status panel — its content depends on the lifecycle. -->
	<div class="stadium-card no-glow p-4 sm:p-6">
		{#if status === 'draft'}
			<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
				<div class="min-w-0">
					<h3 class="font-display text-lg tracking-wide">Ready to submit?</h3>
					<p class="text-sm text-base-content/60 mt-1">
						Once submitted, your predictions lock until the global deadline. You can unlock to edit again any time before then.
					</p>
					{#if !canSubmit && incompleteSummary}
						<p class="text-xs text-warning mt-2">
							⚠ Still missing: {incompleteSummary}
						</p>
					{/if}
				</div>
				<button
					type="button"
					class="btn btn-primary btn-lg shadow-glow-gold whitespace-nowrap"
					disabled={!canSubmit}
					on:click={() => dispatch('submit')}
					title={canSubmit ? 'Submit this entry' : `Complete every section first${incompleteSummary ? ` — ${incompleteSummary}` : ''}`}
				>
					Submit Entry
				</button>
			</div>
		{:else if status === 'locked'}
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

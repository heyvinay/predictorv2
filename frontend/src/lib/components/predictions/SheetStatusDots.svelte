<!--
	SheetStatusDots — top-right of the predictions header.

	A horizontal row of small status dots, one per sheet (entry). The active
	sheet's dot is rendered as an elongated pill (roughly 2x width) so the
	current selection is unambiguous at a glance. Below the dots, a single
	line shows submitted/draft counts; once the competition deadline passes,
	the counts are replaced with "Deadline passed" in red.

	Color encodes status ONLY (no per-sheet color in this build — see
	`docs/prompt-1-i-need-eventual-thimble.md` for the resolved decision):
	  - amber (warning)  → draft, before deadline
	  - green (success)  → submitted
	  - red (error)      → withdrawn, OR draft past deadline ("missed")

	Opacity emphasizes lifecycle stage rather than visual weight:
	  - 50% → draft (in-progress)
	  - 100% → submitted / missed (final state)

	The component reads existing stores only — it never writes data. The
	only mutation is `setActiveEntry(entryId)` on dot tap, which is the
	same action `EntrySelector.svelte` already calls.

	Accessibility: each dot is a `<button>` with `aria-current="true"` on
	the active entry, and an accessible label that includes the sheet's
	display name plus its UI status. The dot itself is decorative
	(aria-hidden) — the button's label conveys the meaning.

	Tap-target ergonomics: the visible dot is small (10px) and the active
	pill is ~20px wide, but each button reserves a 44px vertical hit zone
	(28px horizontal). Vertical 44px meets the iOS HIG finger-target
	minimum; horizontal is tighter to keep the dots-row compact on 375px
	viewports where 8 max-square-44px buttons would consume half the
	screen width.
-->
<script lang="ts">
	import { entries, activeEntryId, setActiveEntry } from '$lib/stores/entries';
	import { isPhase1Locked } from '$lib/stores/phase';
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';

	/**
	 * UI-visible status — collapses `EntryStatus` + the deadline window into
	 * the three visual buckets the dots component cares about. A `draft`
	 * row that's past the deadline reads as `missed` immediately, even
	 * before the backend scheduler tick flips it to `withdrawn` (within
	 * ~60s). The badge never lies to the user while the system catches up.
	 */
	type UiStatus = 'draft' | 'submitted' | 'missed';

	function uiStatusFor(entry: Entry, deadlinePassed: boolean): UiStatus {
		const status = computeDisplayStatus(entry, 'phase_1');
		if (status === 'withdrawn') return 'missed';
		if (status === 'submitted') return 'submitted';
		// status === 'draft'
		return deadlinePassed ? 'missed' : 'draft';
	}

	// DaisyUI semantic fill classes — work in both `predictor` (dark) and
	// `premium` (light) themes because they reference theme tokens, not
	// hard-coded hex.
	const FILL: Record<UiStatus, string> = {
		draft: 'bg-warning',
		submitted: 'bg-success',
		missed: 'bg-error'
	};

	// Opacity per the design brief: drafts are de-emphasized to read as
	// "not finalized yet"; submitted/missed are final and full opacity.
	const OPACITY: Record<UiStatus, string> = {
		draft: 'opacity-50',
		submitted: 'opacity-100',
		missed: 'opacity-100'
	};

	$: deadlinePassed = $isPhase1Locked;

	$: submittedCount = $entries.filter(
		(e) => uiStatusFor(e, deadlinePassed) === 'submitted'
	).length;

	$: draftCount = $entries.filter(
		(e) => uiStatusFor(e, deadlinePassed) === 'draft'
	).length;

	function handleTap(entryId: string) {
		setActiveEntry(entryId);
	}
</script>

{#if $entries.length > 0}
	<div class="flex flex-col items-end gap-1.5">
		<!-- Dots row -->
		<div class="flex" role="group" aria-label="Prediction sheets">
			{#each $entries as e (e.id)}
				{@const ui = uiStatusFor(e, deadlinePassed)}
				{@const isActive = e.id === $activeEntryId}
				<button
					type="button"
					class="flex items-center justify-center w-7 h-11 -mx-0.5 rounded touch-manipulation focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
					on:click={() => handleTap(e.id)}
					aria-label="{e.display_name} — {ui}{isActive ? ' (active)' : ''}"
					aria-current={isActive ? 'true' : undefined}
				>
					<span
						aria-hidden="true"
						class="rounded-full transition-all duration-200 h-2.5 {FILL[ui]} {OPACITY[ui]} {isActive ? 'w-5' : 'w-2.5'}"
					></span>
				</button>
			{/each}
		</div>

		<!-- Counts / deadline-passed message -->
		<div class="text-xs font-mono whitespace-nowrap leading-none">
			{#if deadlinePassed}
				<span class="text-error">Deadline passed</span>
			{:else}
				<span class="text-success">{submittedCount} submitted</span>
				<span class="text-base-content/40"> · </span>
				<span class="text-warning-text">{draftCount} draft</span>
			{/if}
		</div>
	</div>
{/if}

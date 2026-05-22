<!--
	ProgressSection — fixture-completion bar + Smart Fill CTA.

	Renders:
	  - Top line: "X/Y fixtures" (left, muted) + "Z%" (right, success-green
	    at 100% / error-red on missed sheets / muted otherwise)
	  - Thin progress bar with status-toned fill
	  - Smart Fill button (dashed full-width) — only when editable AND
	    pre-deadline. Fires `smartfill` event; parent opens the modal.

	No per-sheet color encoding (resolved decision) — fill color follows
	the active sheet's status: amber for in-progress, green for complete /
	locked, red for missed/post-deadline-draft.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	// Three sub-progresses — caller computes each. The bar visualises
	// the COMBINED count so reaching 100% requires every group fixture
	// + every bracket pick + every bonus answer.
	export let groupProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let bracketProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let bonusProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let canSmartFill: boolean = false;
	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';

	const dispatch = createEventDispatcher<{ smartfill: void }>();

	$: done = groupProgress.done + bracketProgress.done + bonusProgress.done;
	$: total = groupProgress.total + bracketProgress.total + bonusProgress.total;
	$: pct = total > 0 ? Math.round((done / total) * 100) : 0;
	$: complete = total > 0 && done === total;

	// Per-segment color, computed from that segment's own completion + the
	// sheet's overall status. Static maps so Tailwind JIT keeps all classes.
	type SegmentKey = 'complete' | 'progress' | 'empty' | 'missed';
	const SEGMENT_CLASS: Record<SegmentKey, string> = {
		complete: 'bg-success',
		progress: 'bg-warning',
		empty: 'bg-base-content/15',
		missed: 'bg-error'
	};
	const SEGMENT_TEXT_CLASS: Record<SegmentKey, string> = {
		complete: 'text-success',
		progress: 'text-warning',
		empty: 'text-base-content/40',
		missed: 'text-error'
	};

	function segmentKey(done: number, total: number): SegmentKey {
		if (status === 'missed') return 'missed';
		if (total === 0) return 'empty';
		if (done === total) return 'complete';
		if (done > 0) return 'progress';
		return 'empty';
	}

	$: groupKey = segmentKey(groupProgress.done, groupProgress.total);
	$: bracketKey = segmentKey(bracketProgress.done, bracketProgress.total);
	$: bonusKey = segmentKey(bonusProgress.done, bonusProgress.total);

	// CSS Grid columns use the raw `total` counts as fractional units, so
	// segment widths AND label-row columns stay in lockstep (labels align
	// under their own segment, regardless of viewport width).
	$: gridCols = `${Math.max(1, groupProgress.total)}fr ${Math.max(1, bracketProgress.total)}fr ${Math.max(1, bonusProgress.total)}fr`;

	const PCT_TEXT_CLASS = {
		muted: 'text-base-content/60',
		complete: 'text-success',
		missed: 'text-error'
	} as const;
	$: pctKey =
		status === 'missed'
			? ('missed' as const)
			: complete
				? ('complete' as const)
				: ('muted' as const);
</script>

<div class="mb-3">
	<div class="flex items-center justify-between text-xs mb-1.5">
		<span class="text-base-content/60 font-mono tabular-nums">{done}/{total} picks</span>
		<span class="font-semibold tabular-nums {PCT_TEXT_CLASS[pctKey]}">{pct}%</span>
	</div>

	<!-- Three-segment bar — CSS Grid with fractional columns sized by each
	     area's total picks. Each segment is a muted backdrop pill with a
	     colored fill INSIDE sized to that area's own done/total. So 5/72
	     in Groups shows ~7% green-or-amber fill within the Groups pill,
	     not a fully-colored Groups segment. `gap-2` (8px) keeps the
	     three pills visually distinct. -->
	<div
		class="grid w-full h-2 gap-2"
		style="grid-template-columns: {gridCols}"
		aria-label="Prediction progress by area"
	>
		<div
			class="h-full rounded-full bg-base-content/15 overflow-hidden"
			title="Groups {groupProgress.done}/{groupProgress.total}"
		>
			<div
				class="h-full rounded-full transition-all duration-300 {SEGMENT_CLASS[groupKey]}"
				style="width: {groupProgress.total > 0 ? (groupProgress.done / groupProgress.total) * 100 : 0}%"
			></div>
		</div>
		<div
			class="h-full rounded-full bg-base-content/15 overflow-hidden"
			title="Bracket {bracketProgress.done}/{bracketProgress.total}"
		>
			<div
				class="h-full rounded-full transition-all duration-300 {SEGMENT_CLASS[bracketKey]}"
				style="width: {bracketProgress.total > 0 ? (bracketProgress.done / bracketProgress.total) * 100 : 0}%"
			></div>
		</div>
		<div
			class="h-full rounded-full bg-base-content/15 overflow-hidden"
			title="Bonus {bonusProgress.done}/{bonusProgress.total}"
		>
			<div
				class="h-full rounded-full transition-all duration-300 {SEGMENT_CLASS[bonusKey]}"
				style="width: {bonusProgress.total > 0 ? (bonusProgress.done / bonusProgress.total) * 100 : 0}%"
			></div>
		</div>
	</div>

	<!-- Per-segment labels, aligned under their own segment via the SAME
	     grid columns. Label name on top, count on the next line so
	     narrow columns (esp. Bonus at ~8% of bar width) don't blow out
	     the layout. -->
	<div class="grid gap-2 mt-2" style="grid-template-columns: {gridCols}">
		<div class="flex flex-col items-center text-center min-w-0">
			<span class="text-[10px] font-semibold {SEGMENT_TEXT_CLASS[groupKey]}">Groups</span>
			<span class="text-[9px] font-mono tabular-nums opacity-70">
				{groupProgress.done}/{groupProgress.total}
			</span>
		</div>
		<div class="flex flex-col items-center text-center min-w-0">
			<span class="text-[10px] font-semibold {SEGMENT_TEXT_CLASS[bracketKey]}">Bracket</span>
			<span class="text-[9px] font-mono tabular-nums opacity-70">
				{bracketProgress.done}/{bracketProgress.total}
			</span>
		</div>
		<div class="flex flex-col items-center text-center min-w-0">
			<span class="text-[10px] font-semibold {SEGMENT_TEXT_CLASS[bonusKey]}">Bonus</span>
			<span class="text-[9px] font-mono tabular-nums opacity-70">
				{bonusProgress.done}/{bonusProgress.total}
			</span>
		</div>
	</div>

	{#if canSmartFill}
		<button
			type="button"
			class="w-full mt-3 px-3 py-2 rounded-lg border border-dashed border-base-content/30 bg-base-200/30 hover:bg-base-200/60 text-sm font-medium text-base-content/80 min-h-11 transition-colors"
			on:click={() => dispatch('smartfill')}
		>
			⚡ Smart Fill from FIFA Rankings
		</button>
	{/if}
</div>

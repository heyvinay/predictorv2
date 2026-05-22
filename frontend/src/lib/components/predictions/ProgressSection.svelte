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
	// sheet's overall status. Static map so Tailwind JIT keeps all classes.
	type SegmentKey = 'complete' | 'progress' | 'empty' | 'missed';
	const SEGMENT_CLASS: Record<SegmentKey, string> = {
		complete: 'bg-success',
		progress: 'bg-warning',
		empty: 'bg-base-content/15',
		missed: 'bg-error'
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

	// Width share = each segment's TOTAL picks / overall total. Stable so
	// segments don't resize as picks fill in.
	$: groupShare = total > 0 ? (groupProgress.total / total) * 100 : 0;
	$: bracketShare = total > 0 ? (bracketProgress.total / total) * 100 : 0;
	$: bonusShare = total > 0 ? (bonusProgress.total / total) * 100 : 0;

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

	<!-- Three-segment bar. Segment widths are proportional to each area's
	     share of total picks; segment colors reflect that area's own
	     completion state (green=complete, amber=in progress, muted=empty,
	     red=sheet missed). Thin base-100 dividers keep the segments
	     visually distinct without breaking the bar shape. -->
	<div class="w-full h-2 rounded-full bg-base-300/60 overflow-hidden flex" aria-label="Prediction progress by area">
		<div
			class="h-full transition-colors duration-300 {SEGMENT_CLASS[groupKey]}"
			style="width: {groupShare}%"
			title="Groups {groupProgress.done}/{groupProgress.total}"
		></div>
		<div class="h-full w-px bg-base-100/40 flex-shrink-0" aria-hidden="true"></div>
		<div
			class="h-full transition-colors duration-300 {SEGMENT_CLASS[bracketKey]}"
			style="width: {bracketShare}%"
			title="Bracket {bracketProgress.done}/{bracketProgress.total}"
		></div>
		<div class="h-full w-px bg-base-100/40 flex-shrink-0" aria-hidden="true"></div>
		<div
			class="h-full transition-colors duration-300 {SEGMENT_CLASS[bonusKey]}"
			style="width: {bonusShare}%"
			title="Bonus {bonusProgress.done}/{bonusProgress.total}"
		></div>
	</div>

	<!-- Sub-breakdown: per-area progress so the user can see WHERE the
	     missing picks live (groups vs bracket vs bonus). Each segment
	     turns green when its area is complete; otherwise muted. -->
	<div class="flex items-center justify-center gap-2 text-[10px] font-mono tabular-nums mt-1.5 text-base-content/60">
		<span class={groupProgress.done === groupProgress.total && groupProgress.total > 0 ? 'text-success' : ''}>
			Groups {groupProgress.done}/{groupProgress.total}
		</span>
		<span class="opacity-30">·</span>
		<span class={bracketProgress.done === bracketProgress.total && bracketProgress.total > 0 ? 'text-success' : ''}>
			Bracket {bracketProgress.done}/{bracketProgress.total}
		</span>
		<span class="opacity-30">·</span>
		<span class={bonusProgress.done === bonusProgress.total && bonusProgress.total > 0 ? 'text-success' : ''}>
			Bonus {bonusProgress.done}/{bonusProgress.total}
		</span>
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

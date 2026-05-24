<!--
	ProgressSection — completion doughnut chip.

	Three-arc SVG ring sized by each section's WEIGHT in the 112-pick
	total (Groups 72/112, Knockout 31/112, Bonus 9/112). Within each arc,
	the colored fill represents that section's own done/total. Center
	text = overall percentage. Hover reveals a styled breakdown tooltip.

	The Smart Fill CTA used to live in this component; it now renders in
	the wizard parent so the doughnut can sit in the hero's top-right
	corner independently of the action button.

	Color taxonomy:
	  - success (green) — section fully complete
	  - warning (amber) — section in progress
	  - error   (red)   — entry is "missed" (post-deadline draft)
	  - muted           — section has no progress / no picks
-->
<script lang="ts">
	export let groupProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let bracketProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let bonusProgress: { done: number; total: number } = { done: 0, total: 0 };
	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	/** Tailwind size classes for the SVG, e.g. "w-12 h-12" or "w-10 h-10" */
	export let sizeClass: string = 'w-12 h-12';

	$: done = groupProgress.done + bracketProgress.done + bonusProgress.done;
	$: total = groupProgress.total + bracketProgress.total + bonusProgress.total;
	$: pct = total > 0 ? Math.round((done / total) * 100) : 0;
	$: complete = total > 0 && done === total;

	// Doughnut geometry. Circle perimeter is the unit we slice into
	// section arcs; everything else is computed from it so radius/stroke
	// tweaks only need to change here.
	const R = 40;
	const STROKE = 12;
	const C = 2 * Math.PI * R; // ≈ 251.327
	// Tiny gap between arcs so the segments read as distinct slices.
	const GAP = 2;

	$: gWeight = total > 0 ? groupProgress.total / total : 0;
	$: kWeight = total > 0 ? bracketProgress.total / total : 0;
	$: bWeight = total > 0 ? bonusProgress.total / total : 0;

	$: gArcLen = gWeight * C;
	$: kArcLen = kWeight * C;
	$: bArcLen = bWeight * C;

	// Visible backdrop length is shortened by GAP so the next slice has
	// breathing room. Clamp at 0 so a zero-weight section doesn't draw a
	// negative arc.
	$: gBackdropLen = Math.max(0, gArcLen - GAP);
	$: kBackdropLen = Math.max(0, kArcLen - GAP);
	$: bBackdropLen = Math.max(0, bArcLen - GAP);

	// Filled portion within each section's own slice, capped by the
	// section's backdrop length so the fill never bleeds past the gap.
	$: gFillLen =
		groupProgress.total > 0
			? Math.min(gBackdropLen, (groupProgress.done / groupProgress.total) * gArcLen)
			: 0;
	$: kFillLen =
		bracketProgress.total > 0
			? Math.min(kBackdropLen, (bracketProgress.done / bracketProgress.total) * kArcLen)
			: 0;
	$: bFillLen =
		bonusProgress.total > 0
			? Math.min(bBackdropLen, (bonusProgress.done / bonusProgress.total) * bArcLen)
			: 0;

	// Start angles in degrees. -90 = top of the circle. Each slice
	// starts where the previous one ended (weight-proportional).
	$: gStart = -90;
	$: kStart = gStart + gWeight * 360;
	$: bStart = kStart + kWeight * 360;

	type SegmentKey = 'complete' | 'progress' | 'empty' | 'missed';
	function segmentKey(sectionDone: number, sectionTotal: number): SegmentKey {
		if (status === 'missed') return 'missed';
		if (sectionTotal === 0) return 'empty';
		if (sectionDone === sectionTotal) return 'complete';
		if (sectionDone > 0) return 'progress';
		return 'empty';
	}

	// Tailwind JIT requires these class strings to appear literally in
	// source — keep them as plain string values in a const map.
	const SEG_STROKE: Record<SegmentKey, string> = {
		complete: 'stroke-success',
		progress: 'stroke-warning',
		empty: 'stroke-base-content/20',
		missed: 'stroke-error'
	};
	const SEG_TEXT: Record<SegmentKey, string> = {
		complete: 'text-success',
		progress: 'text-warning',
		empty: 'text-base-content/50',
		missed: 'text-error'
	};

	$: gKey = segmentKey(groupProgress.done, groupProgress.total);
	$: kKey = segmentKey(bracketProgress.done, bracketProgress.total);
	$: bKey = segmentKey(bonusProgress.done, bonusProgress.total);

	$: gPct = groupProgress.total > 0 ? Math.round((groupProgress.done / groupProgress.total) * 100) : 0;
	$: kPct = bracketProgress.total > 0 ? Math.round((bracketProgress.done / bracketProgress.total) * 100) : 0;
	$: bPct = bonusProgress.total > 0 ? Math.round((bonusProgress.done / bonusProgress.total) * 100) : 0;

	const PCT_TEXT_CLASS = {
		muted: 'fill-base-content',
		complete: 'fill-success',
		missed: 'fill-error'
	} as const;
	$: pctKey =
		status === 'missed'
			? ('missed' as const)
			: complete
				? ('complete' as const)
				: ('muted' as const);
</script>

<!-- Doughnut + breakdown popover. `group` exposes the SVG's hover state
     to the popover via group-hover. The component renders as a single
     compact chip — the parent decides where to place it. -->
<div class="relative group inline-block flex-shrink-0">
		<svg
			viewBox="0 0 100 100"
			class={sizeClass}
			role="img"
			aria-label="Predictions {pct}% complete. {groupProgress.done} of {groupProgress.total} group picks, {bracketProgress.done} of {bracketProgress.total} knockout picks, {bonusProgress.done} of {bonusProgress.total} bonus picks."
		>
			<!-- Backdrop arcs (muted) -->
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class="stroke-base-content/10"
				stroke-width={STROKE}
				stroke-dasharray="{gBackdropLen} {C}"
				transform="rotate({gStart} 50 50)"
			/>
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class="stroke-base-content/10"
				stroke-width={STROKE}
				stroke-dasharray="{kBackdropLen} {C}"
				transform="rotate({kStart} 50 50)"
			/>
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class="stroke-base-content/10"
				stroke-width={STROKE}
				stroke-dasharray="{bBackdropLen} {C}"
				transform="rotate({bStart} 50 50)"
			/>

			<!-- Filled arcs (status-toned) -->
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class={SEG_STROKE[gKey]}
				stroke-width={STROKE}
				stroke-dasharray="{gFillLen} {C}"
				transform="rotate({gStart} 50 50)"
			/>
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class={SEG_STROKE[kKey]}
				stroke-width={STROKE}
				stroke-dasharray="{kFillLen} {C}"
				transform="rotate({kStart} 50 50)"
			/>
			<circle
				cx="50"
				cy="50"
				r={R}
				fill="none"
				class={SEG_STROKE[bKey]}
				stroke-width={STROKE}
				stroke-dasharray="{bFillLen} {C}"
				transform="rotate({bStart} 50 50)"
			/>

			<!-- Overall percentage -->
			<text
				x="50"
				y="50"
				text-anchor="middle"
				dominant-baseline="central"
				class="font-display {PCT_TEXT_CLASS[pctKey]}"
				font-size="22"
			>{pct}%</text>
		</svg>

		<!-- Breakdown popover. Hidden until the doughnut is hovered.
		     Right-anchored (`right-0`) so the popover extends LEFTWARD from
		     the doughnut. The component lives in the hero's right corner;
		     a `left-0` anchor would push the 12rem-wide popover off the
		     right edge of the viewport. -->
		<div
			role="tooltip"
			class="absolute top-full right-0 mt-2 z-30 min-w-[12rem]
				opacity-0 invisible
				group-hover:opacity-100 group-hover:visible
				transition-opacity duration-150
				bg-base-200 border border-base-300/60 rounded-lg shadow-lg
				px-3 py-2 text-xs pointer-events-none"
		>
			<div class="flex items-center justify-between gap-4">
				<span class="font-semibold {SEG_TEXT[gKey]}">Groups</span>
				<span class="font-mono tabular-nums opacity-80"
					>{groupProgress.done}/{groupProgress.total} · {gPct}%</span
				>
			</div>
			<div class="flex items-center justify-between gap-4 mt-1">
				<span class="font-semibold {SEG_TEXT[kKey]}">Knockout</span>
				<span class="font-mono tabular-nums opacity-80"
					>{bracketProgress.done}/{bracketProgress.total} · {kPct}%</span
				>
			</div>
			<div class="flex items-center justify-between gap-4 mt-1">
				<span class="font-semibold {SEG_TEXT[bKey]}">Bonus</span>
				<span class="font-mono tabular-nums opacity-80"
					>{bonusProgress.done}/{bonusProgress.total} · {bPct}%</span
				>
			</div>
		<div class="flex items-center justify-between gap-4 mt-1 pt-1 border-t border-base-300/60">
			<span class="font-semibold opacity-70">Total</span>
			<span class="font-mono tabular-nums">{done}/{total} · {pct}%</span>
		</div>
	</div>
</div>

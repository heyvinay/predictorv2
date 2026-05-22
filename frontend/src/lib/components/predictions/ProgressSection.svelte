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

	export let done: number = 0;
	export let total: number = 0;
	export let canSmartFill: boolean = false;
	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';

	const dispatch = createEventDispatcher<{ smartfill: void }>();

	$: pct = total > 0 ? Math.round((done / total) * 100) : 0;
	$: complete = total > 0 && done === total;

	// Static class map so Tailwind JIT picks all variants up.
	const FILL_CLASS = {
		draft: 'bg-warning',
		complete: 'bg-success',
		missed: 'bg-error'
	} as const;
	$: fillKey =
		status === 'missed'
			? ('missed' as const)
			: complete || status === 'locked' || status === 'scored'
				? ('complete' as const)
				: ('draft' as const);

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
		<span class="text-base-content/60 font-mono tabular-nums"
			>{done}/{total} fixtures</span
		>
		<span class="font-semibold tabular-nums {PCT_TEXT_CLASS[pctKey]}">{pct}%</span>
	</div>

	<div class="w-full h-1.5 rounded-full bg-base-300/60 overflow-hidden">
		<div
			class="h-full {FILL_CLASS[fillKey]} transition-all duration-300"
			style="width: {pct}%"
		></div>
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

<!--
	SmartFillModal — checkbox form for the FIFA Rankings smart-fill.

	Three independent actions, any combination:
	  A. Overwrite existing picks   — replace fixture predictions that exist
	  B. Fill in blank fixtures      — fill fixtures with no current pick
	  C. Fill in Knock out brackets  — auto-fill the bracket (higher-ranked
	                                    team always wins; ties = seeded
	                                    coin flip per user/match)

	Gating:
	  - A disabled when `existingCount === 0` (nothing to overwrite)
	  - B disabled when `blankCount === 0` (nothing to fill)
	  - C disabled when, after applying A/B, some fixtures would remain
	    blank — i.e. when `!B-checked && blankCount > 0`. Tooltip explains
	    that the bracket needs every group fixture predicted.
	  - Apply disabled when no checkbox is checked.

	Dispatches:
	  - apply { overwrite, fillBlanks, fillBracket }
	  - cancel

	Backdrop click and Escape both trigger cancel (parity with ConfirmModal).
-->
<script lang="ts">
	import { fade, scale } from 'svelte/transition';
	import { createEventDispatcher } from 'svelte';

	export let open = false;
	/** Number of editable fixtures that ALREADY have a pick on this sheet. */
	export let existingCount: number = 0;
	/** Number of editable fixtures with no current pick. */
	export let blankCount: number = 0;
	/** Whether the bracket is currently fully filled (winner non-empty). */
	export let bracketAlreadyFilled: boolean = false;

	const dispatch = createEventDispatcher<{
		apply: { overwrite: boolean; fillBlanks: boolean; fillBracket: boolean };
		cancel: void;
	}>();

	// Defaults per the plan:
	//   A unchecked (don't overwrite)
	//   B checked (fill blanks — the most useful default)
	//   C unchecked (let the user opt in to bracket fill)
	let overwriteChecked = false;
	let fillBlanksChecked = true;
	let fillBracketChecked = false;

	$: aDisabled = existingCount === 0;
	$: bDisabled = blankCount === 0;

	// C is enabled when every editable fixture will have a pick after the
	// action: that means existing + (B-checked ? blanks : 0) covers them all,
	// OR there are no blanks to begin with.
	$: cDisabled = !(blankCount === 0 || fillBlanksChecked);
	$: cTooltip = cDisabled
		? `All group fixtures must have picks before the bracket can be filled. Also check "Fill in blank fixtures" to enable.`
		: bracketAlreadyFilled
			? 'Bracket is currently filled — applying will overwrite it.'
			: 'Auto-fill the bracket: higher-ranked team always wins.';

	// Auto-uncheck each box when its enable-gate fails. Prevents a
	// checked-but-disabled visual state (which would happen e.g. on a
	// fully-filled sheet where bDisabled=true but the default was checked).
	$: if (aDisabled && overwriteChecked) overwriteChecked = false;
	$: if (bDisabled && fillBlanksChecked) fillBlanksChecked = false;
	$: if (cDisabled && fillBracketChecked) fillBracketChecked = false;

	$: applyDisabled = !(overwriteChecked || fillBlanksChecked || fillBracketChecked);

	function handleApply() {
		dispatch('apply', {
			overwrite: overwriteChecked,
			fillBlanks: fillBlanksChecked,
			fillBracket: fillBracketChecked
		});
	}

	function handleCancel() {
		dispatch('cancel');
	}

	function handleKey(e: KeyboardEvent) {
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			handleCancel();
		}
	}
</script>

<svelte:window on:keydown={handleKey} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="smartfill-title"
		aria-describedby="smartfill-body"
	>
		<!-- Backdrop -->
		<button
			type="button"
			class="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
			tabindex="-1"
			aria-label="Close dialog"
			on:click={handleCancel}
			transition:fade={{ duration: 150 }}
		></button>

		<!-- Dialog -->
		<div
			class="relative bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 max-w-sm w-full p-6"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			<div class="text-center mb-4">
				<div class="text-5xl mb-3 leading-none" aria-hidden="true">⚡</div>
				<h2 id="smartfill-title" class="text-xl font-display font-bold mb-2">
					Smart Fill from FIFA Rankings
				</h2>
				<p id="smartfill-body" class="text-sm text-base-content/70">
					Pick what to fill based on each team's FIFA ranking points.
				</p>
			</div>

			<div class="space-y-2 mb-5">
				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {aDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
				>
					<input
						type="checkbox"
						class="checkbox checkbox-warning mt-0.5 flex-shrink-0"
						bind:checked={overwriteChecked}
						disabled={aDisabled}
					/>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium">Overwrite existing picks</div>
						<div class="text-xs text-base-content/60 mt-0.5">
							{existingCount === 0
								? 'No existing picks to overwrite.'
								: `${existingCount} fixture${existingCount === 1 ? '' : 's'} would be replaced.`}
						</div>
					</div>
				</label>

				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {bDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
				>
					<input
						type="checkbox"
						class="checkbox checkbox-primary mt-0.5 flex-shrink-0"
						bind:checked={fillBlanksChecked}
						disabled={bDisabled}
					/>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium">Fill in blank fixtures</div>
						<div class="text-xs text-base-content/60 mt-0.5">
							{blankCount === 0
								? 'No blank fixtures.'
								: `${blankCount} blank fixture${blankCount === 1 ? '' : 's'} would be filled.`}
						</div>
					</div>
				</label>

				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {cDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
					title={cTooltip}
				>
					<input
						type="checkbox"
						class="checkbox checkbox-primary mt-0.5 flex-shrink-0"
						bind:checked={fillBracketChecked}
						disabled={cDisabled}
					/>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium">Fill in Knock out brackets</div>
						<div class="text-xs text-base-content/60 mt-0.5">
							{cDisabled
								? 'Needs all group fixtures predicted first.'
								: bracketAlreadyFilled
									? 'Bracket currently filled — will be overwritten.'
									: 'Higher-ranked team always wins.'}
						</div>
					</div>
				</label>
			</div>

			<div class="flex gap-2">
				<button
					type="button"
					class="btn btn-ghost flex-1 min-h-11"
					on:click={handleCancel}
				>
					Cancel
				</button>
				<button
					type="button"
					class="btn btn-primary flex-1 min-h-11"
					on:click={handleApply}
					disabled={applyDisabled}
				>
					Apply
				</button>
			</div>
		</div>
	</div>
{/if}

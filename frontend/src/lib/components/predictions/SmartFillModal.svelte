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
	/** Whether Betting Odds are usable (ODDS_API_KEY set + cache loaded). */
	export let oddsAvailable: boolean = false;
	/** Cache metadata, displayed under the Betting Odds radio subtitle. */
	export let oddsCacheInfo: { fetchedAt: string; matchCount: number; remaining: number } | null =
		null;

	const dispatch = createEventDispatcher<{
		apply: {
			overwrite: boolean;
			fillBlanks: boolean;
			fillBracket: boolean;
			method: 'fifa' | 'odds';
		};
		cancel: void;
	}>();

	// Defaults per the plan:
	//   A unchecked (don't overwrite)
	//   B checked (fill blanks — the most useful default)
	//   C unchecked (let the user opt in to bracket fill)
	let overwriteChecked = false;
	let fillBlanksChecked = true;
	let fillBracketChecked = false;

	// Method picker — no default; user must explicitly pick FIFA or Odds.
	// Apply stays disabled until one is selected.
	let method: 'fifa' | 'odds' | null = null;

	// Auto-revert to null if odds become unavailable mid-session (mirrors
	// the auto-uncheck pattern below — never silently fall through to FIFA).
	$: if (!oddsAvailable && method === 'odds') method = null;
	// Reset on modal close so each open is a fresh decision.
	$: if (open === false) method = null;

	// Until the user picks a method, none of the three actions are clickable.
	// This makes the two-step flow explicit: pick HOW first, then pick WHAT.
	// Kept separate from a/b/c-Disabled so the existing contextual subtitles
	// (e.g. "Needs all group fixtures predicted first") stay accurate.
	$: actionsDisabled = !method;

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

	// Apply is disabled unless: at least one action is checked AND a method
	// is picked. Both gates compose.
	$: applyDisabled =
		!method || !(overwriteChecked || fillBlanksChecked || fillBracketChecked);

	function handleApply() {
		if (!method) return; // applyDisabled gate should already prevent this
		dispatch('apply', {
			overwrite: overwriteChecked,
			fillBlanks: fillBlanksChecked,
			fillBracket: fillBracketChecked,
			method
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
					{method === 'odds'
						? 'Smart Fill from Betting Odds'
						: method === 'fifa'
							? 'Smart Fill from FIFA Rankings'
							: 'Smart Fill'}
				</h2>
				<p id="smartfill-body" class="text-sm text-base-content/70">
					{method === 'odds'
						? "Pick what to fill based on each team's live betting odds."
						: method === 'fifa'
							? "Pick what to fill based on each team's FIFA ranking points."
							: 'Choose a method, then pick what to fill.'}
				</p>
			</div>

			<!-- Method radios — mirror the checkbox label wrapper below.
			     Only `radio radio-primary` is a new class (DaisyUI form-control,
			     same family as the existing `checkbox checkbox-primary`). -->
			<div class="space-y-2 mb-4">
				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer"
				>
					<input
						type="radio"
						class="radio radio-primary mt-0.5 flex-shrink-0"
						bind:group={method}
						value="fifa"
					/>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium">FIFA Rankings</div>
						<div class="text-xs text-base-content/60 mt-0.5">
							Predicts from each team's world ranking.
						</div>
					</div>
				</label>

				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {!oddsAvailable
						? 'opacity-50 cursor-not-allowed'
						: ''}"
					title={oddsAvailable
						? ''
						: 'Betting odds unavailable — ODDS_API_KEY not set or fetch failed.'}
				>
					<input
						type="radio"
						class="radio radio-primary mt-0.5 flex-shrink-0"
						bind:group={method}
						value="odds"
						disabled={!oddsAvailable}
					/>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium">Betting Odds</div>
						<div class="text-xs text-base-content/60 mt-0.5">
							{#if oddsCacheInfo}
								Refreshed {new Date(oddsCacheInfo.fetchedAt).toLocaleString(undefined, {
									dateStyle: 'medium',
									timeStyle: 'short'
								})} · {oddsCacheInfo.remaining} req left
							{:else if !oddsAvailable}
								Unavailable
							{:else}
								Loading…
							{/if}
						</div>
					</div>
				</label>
			</div>

			<!-- Help paragraph — uses only existing text-xs / text-base-content/60. -->
			{#if method === 'fifa'}
				<div class="text-xs text-base-content/60 mb-4">
					<p>
						We look at each team's official FIFA world ranking. The higher-ranked team
						usually wins, but we add a bit of natural variation tied to your account —
						so your picks won't be identical to other players. Running Smart Fill again
						gives you the same result, so it's safe to experiment.
					</p>
					<p class="mt-2">
						Smart Fill is just a starting point — you can edit any prediction before you submit.
					</p>
				</div>
			{:else if method === 'odds'}
				<div class="text-xs text-base-content/60 mb-4">
					<p>
						We pull live odds from international bookmakers. Betting markets often beat
						pure rankings at picking winners because they factor in current form,
						injuries, and recent results. Odds are refreshed every 24 hours. If a match
						doesn't have odds listed, it'll be skipped — you can fill those in manually.
					</p>
					<p class="mt-2">
						Smart Fill is just a starting point — you can edit any prediction before you submit.
					</p>
				</div>
			{/if}

			<!-- Bracket-with-odds note (plain text — no italic / icon / border). -->
			{#if method === 'odds' && fillBracketChecked}
				<div class="text-xs text-base-content/60 mb-3">
					Bracket rounds use FIFA rankings regardless of method.
				</div>
			{/if}

			<!-- Step 2: actions. Divider + greyed state make the two-step flow
			     clear — checkboxes only become interactive after a method is
			     picked (actionsDisabled = !method). -->
			<div
				class="space-y-2 mb-5 pt-4 border-t border-base-content/10"
			>
				<label
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {aDisabled ||
					actionsDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
				>
					<input
						type="checkbox"
						class="checkbox checkbox-primary [&:not(:checked)]:opacity-60 mt-0.5 flex-shrink-0"
						bind:checked={overwriteChecked}
						disabled={aDisabled || actionsDisabled}
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
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {bDisabled ||
					actionsDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
				>
					<input
						type="checkbox"
						class="checkbox checkbox-primary [&:not(:checked)]:opacity-60 mt-0.5 flex-shrink-0"
						bind:checked={fillBlanksChecked}
						disabled={bDisabled || actionsDisabled}
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
					class="flex items-start gap-3 p-2 rounded-lg hover:bg-base-300/30 cursor-pointer {cDisabled ||
					actionsDisabled
						? 'opacity-50 cursor-not-allowed'
						: ''}"
					title={cTooltip}
				>
					<input
						type="checkbox"
						class="checkbox checkbox-primary [&:not(:checked)]:opacity-60 mt-0.5 flex-shrink-0"
						bind:checked={fillBracketChecked}
						disabled={cDisabled || actionsDisabled}
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

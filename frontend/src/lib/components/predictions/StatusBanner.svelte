<!--
	StatusBanner — full-width contextual notice between hero and groups.

	Two variants:
	  - locked / scored: green-tinted card. 🔒 icon + "Predictions
	    locked - eligible for leaderboard". Unlock button on the right
	    only when deadline has not passed.
	  - missed: red-tinted card. ⚠️ icon + "Draft not submitted before
	    deadline". No action button.

	Hidden for editable draft sheets (the wizard is the action; no
	banner needed). The component returns nothing in that case.

	`status` is the UI-status from the existing mapping
	(draft / locked / scored / missed). Caller passes which deadline
	state applies.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let status: 'draft' | 'locked' | 'scored' | 'missed' = 'draft';
	export let canUnlock: boolean = false;

	const dispatch = createEventDispatcher<{ unlock: void }>();
</script>

{#if status === 'locked' || status === 'scored'}
	<div
		class="mb-4 p-3 sm:p-4 rounded-xl border border-success/40 bg-success/10 flex items-center gap-3 flex-wrap"
		role="status"
	>
		<div class="text-2xl leading-none flex-shrink-0" aria-hidden="true">🔒</div>
		<div class="flex-1 min-w-0">
			<div class="font-semibold text-sm text-success">
				{status === 'scored' ? 'Predictions scoring' : 'Predictions locked'}
			</div>
			<div class="text-xs text-base-content/70 mt-0.5">
				{status === 'scored'
					? 'Your picks are official and being scored on the leaderboard.'
					: 'Your picks are official — eligible for the leaderboard.'}
			</div>
		</div>
		{#if canUnlock}
			<button
				type="button"
				class="btn btn-sm btn-outline btn-success min-h-11 flex-shrink-0"
				on:click={() => dispatch('unlock')}
			>
				Unlock
			</button>
		{/if}
	</div>
{:else if status === 'missed'}
	<div
		class="mb-4 p-3 sm:p-4 rounded-xl border border-error/40 bg-error/10 flex items-center gap-3"
		role="status"
	>
		<div class="text-2xl leading-none flex-shrink-0" aria-hidden="true">⚠️</div>
		<div class="flex-1 min-w-0">
			<div class="font-semibold text-sm text-error">Draft not submitted</div>
			<div class="text-xs text-base-content/70 mt-0.5">
				The competition has started and this sheet was never locked in. It won't be scored.
			</div>
		</div>
	</div>
{/if}

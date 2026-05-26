<!--
	WizardStepper — horizontal 4-step indicator for the predictions wizard.

	A row of circular badges (one per step) connected by thin lines.
	Each step has a number/check inside its circle and a label beneath.

	Badge variants:
	  · complete — filled success-green circle with check icon
	  · active   — primary ring with the step number, bold label
	  · visited  — warning-tone ring with the step number ("needs attention")
	  · locked   — muted grey ring; click is a no-op

	Connector lines between consecutive badges colour-flip to success-green
	when the LEFT side is complete — visualising forward progress.

	Mobile (< sm): labels are hidden under each badge; only the active
	step's label is shown beneath the strip as a single centered line.

	Props:
	  steps: { id, label, complete, locked, visited? }[]
	  activeStep: string  — id of the currently active step

	Event:
	  navigate: { step: string }
	    Fires only when the user clicks a NON-locked badge. The parent
	    decides whether to honour it (e.g. update active step + add to
	    visitedSteps set).
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let steps: Array<{
		id: string;
		label: string;
		complete: boolean;
		locked: boolean;
		visited?: boolean;
	}> = [];
	export let activeStep: string = '';

	const dispatch = createEventDispatcher<{ navigate: { step: string } }>();

	function handleClick(step: typeof steps[number]) {
		if (step.locked) return;
		if (step.id === activeStep) return;
		dispatch('navigate', { step: step.id });
	}

	// Base variant — the badge's underlying look (fill + icon). "active" is
	// NOT a base variant; it's an orthogonal overlay applied separately so
	// the gold glow can sit on top of ANY base (including complete). This
	// means an active+complete step keeps its green check AND gains the
	// gold halo — "done, and you're here".
	function variantOf(step: typeof steps[number]): 'complete' | 'visited' | 'locked' | 'future' {
		if (step.complete) return 'complete';
		if (step.visited) return 'visited';
		if (step.locked) return 'locked';
		return 'future';
	}
</script>

<div class="wizard-stepper">
	<ol class="flex items-start justify-between gap-1 sm:gap-3 w-full">
		{#each steps as step, i (step.id)}
			{@const variant = variantOf(step)}
			{@const isActive = step.id === activeStep}
			{@const isLast = i === steps.length - 1}
			{@const nextComplete = !isLast && steps[i + 1].complete}
			<li class="flex-1 flex flex-col items-center min-w-0 relative">
				<!-- Connector line — sits BEHIND the badge, runs from current
				     badge centre to the next badge centre. Hidden on the last
				     step. Colour reflects this side's completion. -->
				{#if !isLast}
					<div
						class="absolute top-4 sm:top-5 left-1/2 right-[-50%] h-0.5 -z-0
							{step.complete && nextComplete ? 'bg-success' : step.complete ? 'bg-success/60' : 'bg-base-content/15'}"
						aria-hidden="true"
					></div>
				{/if}

				<!-- Badge: base look from `variant` (fill + icon), then the
				     active OVERLAY (gold ring + glow) layered on top so the
				     "you are here" halo follows the active step even when it's
				     already complete. -->
				<button
					type="button"
					class="relative z-10 w-8 h-8 sm:w-10 sm:h-10 rounded-full grid place-items-center font-mono text-sm transition-all
						{variant === 'complete'
							? 'bg-success text-success-content cursor-pointer hover:brightness-110'
							: variant === 'visited'
								? 'bg-base-100 text-warning cursor-pointer hover:brightness-110'
								: variant === 'locked'
									? 'bg-base-100 text-base-content/40 ring-base-content/20 cursor-not-allowed'
									: 'bg-base-100 text-base-content/40 ring-base-content/20'}
						{isActive
							? 'ring-2 ring-primary shadow-glow-gold'
							: variant === 'complete'
								? 'ring-2 ring-success'
								: variant === 'visited'
									? 'ring-2 ring-warning'
									: 'ring-2 ring-base-content/20'}"
					on:click={() => handleClick(step)}
					disabled={step.locked && !isActive}
					aria-current={isActive ? 'step' : undefined}
					aria-label={step.label + (step.complete ? ' (complete)' : step.locked ? ' (locked)' : '')}
				>
					{#if variant === 'complete'}
						<!-- Check icon — kept even when active so completion stays visible. -->
						<svg class="w-4 h-4 sm:w-5 sm:h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
					{:else}
						{i + 1}
					{/if}
				</button>

				<!-- Label below every badge, on all viewports. Truncates with
				     ellipsis if it can't fit its slot. Active wins the label
				     colour (gold/bold) regardless of completion, matching the
				     badge's active glow. -->
				<span
					class="mt-1.5 text-[9px] sm:text-xs font-medium text-center uppercase tracking-wider truncate max-w-full block w-full px-0.5
						{isActive
							? 'text-primary font-bold'
							: variant === 'complete'
								? 'text-success'
								: variant === 'visited'
									? 'text-warning'
									: 'text-base-content/40'}"
				>
					{step.label}
				</span>
			</li>
		{/each}
	</ol>
</div>

<style>
	/* Keep the connector lines behind the buttons. The negative z-index on
	   the line + positive z-index on the button avoids overlapping click
	   targets. */
	.wizard-stepper :global(.-z-0) {
		z-index: 0;
	}
</style>

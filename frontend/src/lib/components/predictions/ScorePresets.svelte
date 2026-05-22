<!--
	ScorePresets — three-pill quick-score chooser.

	Renders centered "1 - 0", "0 - 0", "0 - 1" pills in monospace.
	Tapping fires `onSelect(home, away)`.

	Slide-down + fade IN, instant OUT — we use Svelte's `in:` directive
	(entering animation only) rather than `transition:` so the row
	disappears immediately when a preset is picked (no awkward
	out-animation between "user picked 1-0" and "stepper now shows 1-0").

	Designed to be rendered conditionally: caller wraps in `{#if expanded}`.
	The `show` prop is a no-op marker — kept for API symmetry but the
	`{#if expanded}` in the caller handles visibility.

	Used by FixtureRow (Prompt 8) below empty editable fixtures.
-->
<script lang="ts">
	import { fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	/**
	 * Called when a preset is tapped. Receives (home, away) scores
	 * so the caller can plug them into its own state / store.
	 */
	export let onSelect: (home: number, away: number) => void = () => {};

	const PRESETS: ReadonlyArray<{ home: number; away: number; label: string }> = [
		{ home: 1, away: 0, label: '1 – 0' },
		{ home: 0, away: 0, label: '0 – 0' },
		{ home: 0, away: 1, label: '0 – 1' }
	] as const;
</script>

<div
	class="flex items-center justify-center gap-2 py-2"
	in:fly={{ y: -8, duration: 200, easing: cubicOut, opacity: 0 }}
	role="group"
	aria-label="Quick score presets"
>
	{#each PRESETS as p (p.label)}
		<button
			type="button"
			class="btn btn-outline btn-sm font-mono tabular-nums min-h-11 px-4"
			on:click={() => onSelect(p.home, p.away)}
			aria-label="Set score to {p.label}"
		>
			{p.label}
		</button>
	{/each}
</div>

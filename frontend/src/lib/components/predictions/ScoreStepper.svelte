<!--
	ScoreStepper — inline [−] H [+] – [−] A [+] score chooser.

	Compact horizontal stepper for two scores (home / away). Designed to
	sit between two team names in a fixture row.

	Behavior:
	  - − disabled at `min` (default 0); + disabled at `max` (default 15
	    per CLAUDE.md spec — "Score inputs are capped at 15 goals per side")
	  - Each button fires onChange with the FULL (home, away) pair so the
	    caller can write to the predictions store in one call
	  - Numbers reserve 1.75ch tabular-nums width so 10–15 don't shift the
	    layout vs. 0–9
	  - Disabled propagates to all buttons (fixture locked, sheet not
	    editable, etc.)

	A11y:
	  - Each button has an explicit aria-label
	  - Score numbers are aria-live="polite" so the readout announces
	    after each tap (but only when focus is on the stepper, so it's
	    not noisy)
-->
<script lang="ts">
	export let home: number = 0;
	export let away: number = 0;
	export let min: number = 0;
	export let max: number = 15;
	export let disabled: boolean = false;

	/**
	 * Fired with the FULL pair (home, away) — caller plugs straight into
	 * the predictions store without merging.
	 */
	export let onChange: (home: number, away: number) => void = () => {};

	function clamp(n: number): number {
		return Math.max(min, Math.min(max, n));
	}

	function bump(side: 'home' | 'away', delta: number): void {
		if (disabled) return;
		if (side === 'home') {
			const next = clamp(home + delta);
			if (next !== home) onChange(next, away);
		} else {
			const next = clamp(away + delta);
			if (next !== away) onChange(home, next);
		}
	}

	$: homeMinusDisabled = disabled || home <= min;
	$: homePlusDisabled = disabled || home >= max;
	$: awayMinusDisabled = disabled || away <= min;
	$: awayPlusDisabled = disabled || away >= max;
</script>

<div class="inline-flex items-center gap-0.5 select-none" aria-label="Score">
	<button
		type="button"
		class="btn btn-ghost btn-sm btn-square min-h-9 h-9 w-9 px-0"
		disabled={homeMinusDisabled}
		on:click={() => bump('home', -1)}
		aria-label="Decrease home score"
	>−</button>
	<span
		class="font-mono font-bold text-lg tabular-nums text-center"
		style="min-width: 1.75ch;"
		aria-live="polite">{home}</span
	>
	<button
		type="button"
		class="btn btn-ghost btn-sm btn-square min-h-9 h-9 w-9 px-0"
		disabled={homePlusDisabled}
		on:click={() => bump('home', +1)}
		aria-label="Increase home score"
	>+</button>

	<span class="text-base-content/30 px-1.5 select-none" aria-hidden="true">–</span>

	<button
		type="button"
		class="btn btn-ghost btn-sm btn-square min-h-9 h-9 w-9 px-0"
		disabled={awayMinusDisabled}
		on:click={() => bump('away', -1)}
		aria-label="Decrease away score"
	>−</button>
	<span
		class="font-mono font-bold text-lg tabular-nums text-center"
		style="min-width: 1.75ch;"
		aria-live="polite">{away}</span
	>
	<button
		type="button"
		class="btn btn-ghost btn-sm btn-square min-h-9 h-9 w-9 px-0"
		disabled={awayPlusDisabled}
		on:click={() => bump('away', +1)}
		aria-label="Increase away score"
	>+</button>
</div>

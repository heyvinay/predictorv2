<script lang="ts">
	/** "For the nerds" ℹ popover — plain-English background on how points
	 *  and ranking actually work, for users confused by things like two
	 *  same-total entries ranking #21/#22 instead of tying. Same popover
	 *  pattern as PointsHelpButton.svelte (results/v4); numbers come from
	 *  ScoringRules so a YAML change updates this copy too.
	 *
	 *  `iconOnly` drops the "For the nerds" label for tight inline use
	 *  (next to the Total column header) — just the ⓘ badge, same click
	 *  target and popover. `align` controls which edge the popover hangs
	 *  from; right-aligned callers (like Total, near the row's right
	 *  edge) should pass "right" so the panel doesn't overflow. */
	import type { ScoringRules } from '$lib/types/results';

	export let rules: ScoringRules;
	export let iconOnly = false;
	export let align: 'left' | 'right' = 'left';

	let open = false;
	let containerEl: HTMLSpanElement;

	$: exactTotal = rules.match.correct_outcome + rules.match.exact_score;

	function onWindowClick(e: MouseEvent) {
		if (!open || !containerEl) return;
		if (!containerEl.contains(e.target as Node)) open = false;
	}
	function onKey(e: KeyboardEvent) {
		if (open && e.key === 'Escape') open = false;
	}
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<span bind:this={containerEl} class="relative inline-flex">
	<button
		type="button"
		class="inline-flex items-center gap-1 text-[11px] font-semibold text-base-content/55 transition-colors hover:text-primary"
		aria-expanded={open}
		aria-label={iconOnly ? 'How points & ranking work' : undefined}
		on:click|stopPropagation={() => (open = !open)}
	>
		<span
			class="grid h-3.5 w-3.5 place-items-center rounded-full bg-base-300/60 text-[10px] leading-none"
			aria-hidden="true">ⓘ</span
		>
		{#if !iconOnly}For the nerds{/if}
	</button>

	{#if open}
		<div
			class="absolute top-[calc(100%+6px)] z-30 w-[300px] rounded-box border border-primary/30 bg-base-200 p-3 text-left text-[12px] font-normal normal-case leading-relaxed text-base-content/85 shadow-card {align ===
			'right'
				? 'right-0'
				: 'left-0'}"
			role="dialog"
		>
			<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">
				How points &amp; ranking work
			</div>
			<p>
				<b>Group</b>: +{rules.match.correct_outcome} for the right winner/draw, +{exactTotal} if
				you nail the exact score{#if rules.mode === 'logarithmic'}, plus a small <b>rarity bonus</b>
					when your correct pick was one few others made{:else} — no rarity bonus while it's paused{/if}.
			</p>
			<p class="mt-1.5">
				<b>Knockout</b>: points bank the moment your bracket pick reaches a round — up to +{rules
					.advancement.winner} for correctly picking the champion. Once banked, they're yours even
				if that team loses later.
			</p>
			<p class="mt-1.5">
				<b>Total</b> = Group + Knockout + bonus-question points.
			</p>
			<p class="mt-1.5">
				<b>Ties</b>: if two entries land on the same Total, whoever called more exact scorelines
				ranks higher — that's why you'll sometimes see back-to-back entries with the same Total
				but different rank numbers.
			</p>
		</div>
	{/if}
</span>

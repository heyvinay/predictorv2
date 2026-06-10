<script lang="ts">
	/** Top points-summary card — three big numbers: Group / Knockout /
	 *  Total. Each non-total cell carries a small sub-line for the bonus
	 *  questions that belong to that half of the tournament (bonus 1+2 →
	 *  group, bonus 3+4 → knockout). The Total cell wears the page's gold
	 *  accent (the single Tournament-total glow lives on the Summary tab;
	 *  this header card stays subtle). */
	export let groupTotal: number;
	export let knockoutTotal: number;
	export let bonusGroup = 0;
	export let bonusKnockout = 0;
	/** Stretches full-width for single-entry users (parent toggles). */
	export let fullWidth = false;

	$: grandTotal = groupTotal + knockoutTotal + bonusGroup + bonusKnockout;
</script>

<div
	class="flex items-center gap-1.5 rounded-btn border border-base-300/60 bg-base-200 px-2.5 py-1 {fullWidth
		? 'w-full justify-between'
		: ''}"
>
	<div class="flex items-baseline gap-1.5 pr-2 sm:pr-3">
		<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
			Group
		</span>
		<span class="font-display text-[13px] leading-none text-base-content">{groupTotal}</span>
		{#if bonusGroup > 0}
			<span class="text-[9px] font-bold leading-none text-base-content/55"
				>+{bonusGroup}b</span
			>
		{/if}
	</div>
	<div class="flex items-baseline gap-1.5 border-l border-base-300/40 px-2 sm:px-3">
		<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
			Knockout
		</span>
		<span class="font-display text-[13px] leading-none text-base-content">{knockoutTotal}</span>
		{#if bonusKnockout > 0}
			<span class="text-[9px] font-bold leading-none text-base-content/55"
				>+{bonusKnockout}b</span
			>
		{/if}
	</div>
	<div class="ml-auto flex items-baseline gap-1.5 border-l border-base-300/40 pl-2 sm:pl-3">
		<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
			>Total</span
		>
		<span class="font-display text-[14px] leading-none text-primary">{grandTotal}</span>
	</div>
</div>

<script lang="ts">
	/** Round cell: stage chip (KO gold-soft / group neutral) + context
	 *  label ("Group D" or "9 Jul"). Label hides on the tightest
	 *  viewports — the chip alone still identifies the round. */
	import type { DashRoundChip } from '$lib/types/dashboard';

	export let chip: DashRoundChip;
</script>

<span class="flex min-w-0 items-center gap-1.5">
	<span
		class="flex-none rounded-badge px-1.5 py-0.5 text-[10px] font-extrabold leading-none {chip.isGroup
			? 'bg-base-300/50 text-base-content/70'
			: 'bg-primary/15 text-primary'}">{chip.chip}</span
	>
	<span class="hidden truncate text-[10px] font-semibold text-base-content/55 sm:block"
		>{chip.sub}</span
	>
</span>

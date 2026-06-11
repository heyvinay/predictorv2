<script lang="ts">
	/** "Your call" chip for finished fixtures.
	 *  Group rows grade the score prediction — exact (gold ✓✓), result
	 *  (green ✓), miss (dim ✗). Knockout rows grade the bracket call. */
	import type { DashCall } from '$lib/types/dashboard';

	export let call: DashCall;
</script>

{#if call.kind === 'score'}
	{#if call.grade === 'exact'}
		<span
			class="rounded-md bg-primary/15 px-1.5 py-0.5 font-mono text-[10.5px] font-medium tabular-nums text-primary"
			title="Exact score">{call.label} ✓✓</span
		>
	{:else if call.grade === 'result'}
		<span
			class="rounded-md bg-success/20 px-1.5 py-0.5 font-mono text-[10.5px] font-medium tabular-nums text-success"
			title="Correct result">{call.label} ✓</span
		>
	{:else}
		<span
			class="rounded-md bg-base-300/40 px-1.5 py-0.5 font-mono text-[10.5px] font-medium tabular-nums text-base-content/45"
			title="Missed">{call.label} ✗</span
		>
	{/if}
{:else if call.kind === 'team'}
	<span
		class="rounded-badge px-2 py-0.5 font-display text-[10px] font-extrabold {call.hit
			? 'bg-success/20 text-success'
			: 'bg-base-300/40 text-base-content/45'}"
		title={call.team}>{call.tla} {call.hit ? '✓' : '✗'}</span
	>
{:else}
	<span class="text-[11px] text-base-content/30">—</span>
{/if}

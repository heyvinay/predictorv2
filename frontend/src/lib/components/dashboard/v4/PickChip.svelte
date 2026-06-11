<script lang="ts">
	/** "Your pick" chip for unfinished fixtures: score chip (group rows),
	 *  team-TLA chip (knockout bracket call), or a muted dash. */
	import type { DashPick } from '$lib/types/dashboard';

	export let pick: DashPick;
</script>

{#if pick.kind === 'score'}
	<span
		class="rounded-md bg-base-300/40 px-1.5 py-0.5 font-mono text-[10.5px] font-medium tabular-nums text-base-content/85"
		>{pick.label}</span
	>
{:else if pick.kind === 'team'}
	<span
		class="rounded-badge bg-success/20 px-2 py-0.5 font-display text-[10px] font-extrabold text-success"
		title={pick.team}>{pick.tla}</span
	>
{:else}
	<span class="text-[11px] text-base-content/30">—</span>
{/if}

<!--
	DeadlineBanner — single-phase deadline banner.

	The competition uses ONE global deadline (config-driven). Every
	prediction — group-stage scores, knockout bracket, bonus questions —
	must be submitted before it. After it passes, all entries lock at
	once. There is no per-match lock window and no separate Phase II.

	Two variants driven by `isLocked`:
	  - Live countdown (still editable)
	  - Locked state (no more changes)

	Currently not imported anywhere — kept as the canonical single-phase
	component for any future surface that needs the same banner.
-->
<script lang="ts">
	import Icon from '$components/Icon.svelte';

	export let countdown: string;
	export let isLocked: boolean;

	$: showCountdown = !isLocked && countdown !== 'Not set' && countdown !== 'Locked';
</script>

{#if showCountdown}
	<div class="flex items-center gap-3 px-4 py-3 rounded-xl bg-primary/10 border border-primary/20">
		<Icon name="clock" class="w-5 h-5 flex-shrink-0 text-primary" />
		<div class="flex-1 min-w-0">
			<p class="text-sm font-medium text-primary">
				Predictions lock in <span class="font-mono">{countdown}</span>
			</p>
			<p class="text-xs text-base-content/50">
				Complete your group-stage scores, knockout bracket, and bonus questions
			</p>
		</div>
	</div>
{/if}

{#if isLocked}
	<div class="flex items-center gap-3 px-4 py-3 bg-base-300/50 border border-base-300 rounded-xl">
		<Icon name="lock" class="w-5 h-5 text-base-content/50 flex-shrink-0" />
		<div class="flex-1">
			<p class="text-sm font-medium text-base-content/70">
				Predictions are locked
			</p>
			<p class="text-xs text-base-content/50">
				Entries can no longer be changed
			</p>
		</div>
	</div>
{/if}

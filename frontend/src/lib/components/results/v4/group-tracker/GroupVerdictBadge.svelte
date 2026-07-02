<script lang="ts">
	import type { GroupVerdict } from '$lib/utils/groupTracker';

	export let verdict: GroupVerdict;

	const TONE_CLASS: Record<GroupVerdict['tone'], string> = {
		good: 'bg-success/10 text-success',
		warn: 'bg-warning/10 text-warning-text',
		miss: 'bg-error/10 text-error',
		pend: 'bg-base-300/50 text-base-content/60'
	};
	const TONE_ICON: Record<GroupVerdict['tone'], string> = {
		good: '✓',
		warn: '!',
		miss: '!',
		pend: '·'
	};
</script>

<div class="flex flex-col gap-1 rounded-lg px-3 py-2 text-xs {TONE_CLASS[verdict.tone]}">
	<div class="flex items-center justify-between gap-2">
		<span class="flex items-center gap-1.5 font-semibold">
			<span class="font-bold">{TONE_ICON[verdict.tone]}</span>
			{verdict.label}
		</span>
		<span class="opacity-75">{verdict.detail}</span>
	</div>
	{#if verdict.needs}
		<div class="flex items-start gap-1.5 border-t border-current/15 pt-1 text-[11px] text-base-content/85">
			<span class="font-bold text-primary">→</span>
			<span>{verdict.needs}</span>
		</div>
	{/if}
</div>

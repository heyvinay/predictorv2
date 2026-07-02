<script lang="ts">
	import type { QDotState } from '$lib/utils/groupTracker';

	export let dots: [QDotState, QDotState];

	function dotClass(state: QDotState): string {
		if (state === 'hit') return 'bg-success';
		if (state === 'swap') return 'bg-warning';
		return 'bg-error';
	}
</script>

<span class="inline-flex items-center gap-1 rounded-full bg-base-300/60 px-2 py-1" title="Your two picks' status">
	{#each dots as dot}
		<span class="h-2 w-2 rounded-full {dotClass(dot)}"></span>
	{/each}
</span>

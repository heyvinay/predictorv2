<script lang="ts">
	import type { LbEntryV4 } from '$lib/types/leaderboard';

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined;
</script>

<div class="rounded-xl border border-base-300/60 bg-base-200 p-5">
	<h2 class="font-hero text-2xl tracking-[0.04em]">The Race</h2>
	<p class="mt-1 text-xs text-base-content/55">
		{rows.length} entries · {userId ? 'yours in gold' : ''} — chart loading…
	</p>
</div>

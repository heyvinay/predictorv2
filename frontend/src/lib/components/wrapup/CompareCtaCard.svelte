<script lang="ts">
	import { track } from '$lib/analytics';

	export let championEntryId: string | null;
	export let myEntryId: string | null;

	$: href =
		myEntryId && championEntryId ? `/compare?a=${myEntryId}&b=${championEntryId}` : '/compare';
</script>

<div class="grid h-full content-center gap-2 rounded-box border border-primary/45 stadium-card p-4 text-center">
	<span class="text-2xl">🤔</span>
	<h2 class="font-display font-extrabold">Why didn't I win?</h2>
	<p class="text-[13px] text-base-content/55">
		Put your entry side-by-side with the champion's — every pick, every point, and the exact
		moments the title slipped away.
	</p>
	<a
		{href}
		class="btn btn-primary btn-sm justify-self-center"
		on:click={() => track('wrapup_compare_cta_clicked', {})}
	>Compare my entry →</a>
</div>

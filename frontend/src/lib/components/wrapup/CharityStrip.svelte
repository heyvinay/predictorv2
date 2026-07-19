<script lang="ts">
	import { track } from '$lib/analytics';

	export let isMember: boolean;
</script>

<div class="stadium-card no-glow h-full p-4 text-center text-[13px] text-base-content/60">
	❤️ Where the money went: <b class="text-base-content">€595</b> to the champion ·
	<b class="text-base-content">€183</b> to the group-stage winner ·
	<b class="text-primary">€137</b> Soup Kitchen donation.<br />
	<span class="text-xs">Thank you for playing. See you at the next one.</span>
	<div class="mt-2.5 flex flex-wrap justify-center gap-2">
		<a
			href="/leaderboard"
			class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary"
			on:click={() => track('wrapup_footer_link_clicked', { target: 'leaderboard' })}>Final leaderboard</a
		>
		{#if isMember}
			<a
				href="/compare"
				class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary"
				on:click={() => track('wrapup_footer_link_clicked', { target: 'compare' })}>Head-to-head compare</a
			>
		{/if}
		<a
			href="/results"
			class="rounded-badge border border-primary/35 px-4 py-1 text-xs font-bold text-primary"
			on:click={() => track('wrapup_footer_link_clicked', { target: 'results' })}>Results archive</a
		>
	</div>
</div>

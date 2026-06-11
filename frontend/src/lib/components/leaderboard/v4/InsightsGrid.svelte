<script lang="ts">
	import type { Fixture } from '$types';
	import type { LbEntryV4, LbStage } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';

	export let rows: LbEntryV4[];
	export let rules: ScoringRules | null;
	export let userId: string | null | undefined;
	export let fixtures: Fixture[];
	export let stage: LbStage;
</script>

<div class="rounded-xl border border-base-300/60 bg-base-200 p-5">
	<h2 class="font-hero text-2xl tracking-[0.04em]">Insights</h2>
	<p class="mt-1 text-xs text-base-content/55">
		{rows.length} entries · {fixtures.length} fixtures · {stage} stage
		{#if rules}· {rules.mode} scoring{/if}{#if userId}&nbsp;{/if}
	</p>
</div>

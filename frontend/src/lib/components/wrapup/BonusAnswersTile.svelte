<script lang="ts">
	import type { BonusAnswerOut } from '$lib/types/wrapup';

	export let bonus: BonusAnswerOut[];

	$: hardest = bonus.length ? bonus.reduce((a, b) => (a.hit_pct <= b.hit_pct ? a : b)) : null;
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display text-[15px] font-extrabold">Bonus questions — pool hit rate</h2>
	<p class="mb-2 text-xs text-base-content/50">
		The four pre-tournament questions, their answers, and how much of the pool called each.
	</p>
	{#each bonus as q (q.question_id)}
		<div class="mt-1.5 grid grid-cols-[110px_1fr_34px] items-center gap-2 text-[13px]">
			<span class="min-w-0">
				<span class="block truncate">{q.label}</span>
				<span class="block truncate text-[10px] font-bold text-primary">{q.answer_label} ✓</span>
			</span>
			<div class="h-2.5 overflow-hidden rounded-full bg-base-300/60">
				<div class="h-full rounded-full bg-success" style={`width:${Math.round(q.hit_pct * 100)}%`}></div>
			</div>
			<span class="text-right text-xs tabular-nums text-base-content/55">{Math.round(q.hit_pct * 100)}%</span>
		</div>
	{/each}
	{#if hardest}
		<p class="mt-2 text-[11px] text-base-content/40">
			Gold = the correct answer. {hardest.label} was the pool's hardest — {Math.round(hardest.hit_pct * 100)}% got it.
		</p>
	{/if}
</div>

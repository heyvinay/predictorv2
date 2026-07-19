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
		<div class="mt-2.5 first:mt-1.5">
			<div class="flex items-baseline justify-between gap-2">
				<span class="text-[13px]">{q.label}</span>
				<span class="flex-none text-right text-xs tabular-nums text-base-content/55"
					>{Math.round(q.hit_pct * 100)}%</span
				>
			</div>
			<p class="text-[11px] font-bold text-primary">{q.answer_label} ✓</p>
			<div class="mt-1 h-2 overflow-hidden rounded-full bg-base-300/60">
				<div class="h-full rounded-full bg-success" style={`width:${Math.round(q.hit_pct * 100)}%`}></div>
			</div>
		</div>
	{/each}
	{#if hardest}
		<p class="mt-2 text-[11px] text-base-content/40">
			Gold = the correct answer. {hardest.label} was the pool's hardest — {Math.round(hardest.hit_pct * 100)}% got it.
		</p>
	{/if}
</div>

<script lang="ts">
	/** Future Cone — small visual locating this fixture in the bracket.
	 *
	 *  A simplified path-to-the-trophy strip: current stage highlighted,
	 *  downstream stages dimmed. Doesn't try to resolve specific
	 *  downstream matchups (the bracket-tree visualisation belongs on the
	 *  bracket page); the job here is to make "where am I in the bracket"
	 *  tangible without leaving the match-detail page. */
	import type { Fixture } from '$types';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;

	const STAGES = [
		{ id: 'round_of_32', short: 'R32', long: 'Round of 32' },
		{ id: 'round_of_16', short: 'R16', long: 'Round of 16' },
		{ id: 'quarter_final', short: 'QF', long: 'Quarter-finals' },
		{ id: 'semi_final', short: 'SF', long: 'Semi-finals' },
		{ id: 'final', short: 'F', long: 'Final' },
		{ id: 'winner', short: 'W', long: 'Champion' }
	] as const;

	$: currentIdx = STAGES.findIndex((s) => s.id === fixture.stage);
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">Path to glory</span>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
			>where this leads</span
		>
	</div>

	<p class="mb-3 text-[12px] text-base-content/65">
		<TeamName name={fixture.home_team} /> vs <TeamName name={fixture.away_team} /> · winner
		moves on to {STAGES[currentIdx + 1]?.long ?? 'lift the trophy'}.
	</p>

	<div class="flex flex-col gap-1.5">
		{#each STAGES as stage, i}
			{@const isCurrent = i === currentIdx}
			{@const isPast = i < currentIdx}
			{@const isFuture = i > currentIdx}
			<div
				class="flex items-center justify-between rounded-btn border px-3 py-2 text-[12px] {isCurrent
					? 'border-primary/50 bg-primary/15 font-bold text-primary'
					: isPast
						? 'border-base-300/30 bg-base-300/10 text-base-content/35 line-through'
						: 'border-base-300/40 bg-base-300/15 text-base-content/55'}"
			>
				<div class="flex items-center gap-2">
					<span class="font-mono text-[10.5px] font-bold {isCurrent ? 'text-primary' : 'opacity-60'}"
						>{stage.short}</span
					>
					<span>{stage.long}</span>
				</div>
				{#if isCurrent}
					<span class="text-[10px] font-bold uppercase tracking-[0.12em]">You are here</span>
				{:else if isFuture}
					<span class="text-[10px] opacity-50">{stage.short} →</span>
				{/if}
			</div>
		{/each}
	</div>

	<div class="mt-3 text-[10.5px] leading-relaxed text-base-content/45">
		Stages dim as the tournament progresses; the highlighted row is the round this fixture
		belongs to.
	</div>
</div>

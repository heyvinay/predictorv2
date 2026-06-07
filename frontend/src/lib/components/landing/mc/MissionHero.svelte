<!--
  MissionHero — eyebrow greeting + entry-name + rank ordinal headline.
  Mockup-original (no upstream equivalent). Thin component; just the
  hero header above the KPI row.
-->
<script lang="ts">
	import { user } from '$stores/auth';
	import { activeEntry } from '$stores/entries';
	import { activeRank, bestEntryId, isOnlyEntry } from '$stores/missionDerived';
	import { activeEntryId } from '$stores/entries';
	import { totalParticipants } from '$stores/leaderboard';
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';

	function ordSuffix(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return s[(v - 20) % 10] || s[v] || s[0];
	}

	function greeting(): string {
		const h = new Date().getHours();
		if (h < 12) return 'Good morning';
		if (h < 18) return 'Good afternoon';
		return 'Good evening';
	}

	$: firstName = ($user?.name ?? '').trim().split(/\s+/)[0] || 'Player';
	$: entry = $activeEntry as Entry | null;
	$: isBest = $activeEntryId === $bestEntryId;
	$: draft = entry ? computeDisplayStatus(entry, 'phase_1') === 'draft' : false;
</script>

<div class="mb-5">
	<p class="text-xs font-mono uppercase tracking-[0.16em] text-base-content/60 mb-2">
		{greeting()}, {firstName}
		{#if !$isOnlyEntry}
			· {isBest ? 'viewing your best entry' : 'viewing 1 entry'}
		{/if}
	</p>
	<h1
		class="font-display font-extrabold leading-tight tracking-tight flex flex-wrap items-baseline gap-x-3 gap-y-1"
		style="font-size: clamp(22px, 3.2vw, 32px);"
	>
		<span class="text-primary whitespace-nowrap">
			{entry?.reference ?? 'Your entry'}
		</span>
		<span class="text-base-content/70 font-bold whitespace-nowrap">
			{#if $activeRank != null}
				{$activeRank}{ordSuffix($activeRank)} of {$totalParticipants}
			{:else}
				ranking pending
			{/if}
		</span>
		{#if !$isOnlyEntry && isBest}
			<span
				class="text-[10px] font-bold uppercase tracking-[0.04em] px-2.5 py-1 rounded-full text-primary"
				style:background="rgba(212,175,55,0.16)"
			>
				★ Your best
			</span>
		{/if}
		{#if draft}
			<span
				class="text-[10px] font-bold uppercase tracking-[0.04em] px-2.5 py-1 rounded-full"
				style:background="rgba(217,119,6,0.20)"
				style:color="var(--warning-text, #fbbf24)"
			>
				DRAFT · incomplete at lock
			</span>
		{/if}
	</h1>
</div>

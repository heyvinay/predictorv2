<!--
  MissionVsField — Top 5 of the pool leaderboard plus any of the user's
  entries that rank below top 5 (with a "···" gap indicator). Active
  entry highlighted with primary-soft fill. Sibling entries marked with
  gold left-border + "● also yours" suffix. Clicking a sibling row
  switches the active entry — propagates the lens change to every other
  Mission section via $activeEntryId.

  Ported from upstream's DwTop5 + extended for our multi-entry model.
-->
<script lang="ts">
	import { entries, activeEntryId, setActiveEntry } from '$stores/entries';
	import { leaderboard } from '$stores/leaderboard';
	import { activeLeaderboardRow } from '$stores/missionDerived';

	$: myEntryIds = new Set(
		$entries.filter((e) => !e.is_disabled && !e.withdrawn_at).map((e) => e.id)
	);
	$: top5 = ($leaderboard ?? []).slice(0, 5);
	$: siblings = ($leaderboard ?? []).filter(
		(r) => myEntryIds.has(r.entry_id) && !top5.some((t) => t.entry_id === r.entry_id)
	);
	$: combined = [...top5, ...siblings];

	$: activeRow = $activeLeaderboardRow;
	$: leaderRow = ($leaderboard ?? [])[0] ?? null;
	$: gapTo1st =
		activeRow && leaderRow ? Math.max(0, leaderRow.total_points - activeRow.total_points) : 0;
	$: gapAbove = (() => {
		if (!activeRow || !$leaderboard) return 0;
		const above = $leaderboard.find((r) => r.position === activeRow.position - 1);
		return above ? Math.max(0, above.total_points - activeRow.total_points) : 0;
	})();

	function onRowClick(entryId: string | null) {
		if (entryId && myEntryIds.has(entryId)) setActiveEntry(entryId);
	}
</script>

<section class="stadium-card no-glow p-6">
	<div class="flex items-center justify-between mb-3">
		<h2 class="font-display font-extrabold text-lg">You vs. the field</h2>
		<a href="/leaderboard" class="text-xs font-semibold text-primary hover:underline">
			Standings →
		</a>
	</div>

	<div class="flex flex-col">
		{#each combined as r, i (r.entry_id)}
			{@const isActive = r.entry_id === $activeEntryId}
			{@const isMine = myEntryIds.has(r.entry_id)}
			{@const showGap = i > 0 && r.position - combined[i - 1].position > 1}
			{#if showGap}
				<div class="text-center text-[10px] tracking-[0.2em] text-base-content/55 py-1">···</div>
			{/if}
			<button
				type="button"
				class="grid items-center gap-2 py-2 px-2 rounded-btn text-left mb-0.5 transition-colors"
				style="grid-template-columns: 24px 1fr auto auto;"
				style:background={isActive ? 'rgba(212,175,55,0.16)' : 'transparent'}
				style:border={isActive ? '1px solid rgba(212,175,55,0.40)' : '1px solid transparent'}
				style:border-left={isMine && !isActive ? '3px solid rgba(212,175,55,0.7)' : undefined}
				on:click={() => onRowClick(r.entry_id)}
				disabled={!isMine}
			>
				<span
					class="font-display text-sm"
					style:color={isActive ? 'var(--p, #D4AF37)' : 'rgba(226,232,240,0.72)'}
				>
					{r.position}
				</span>
				<div class="min-w-0">
					<div class="text-sm font-semibold whitespace-nowrap overflow-hidden text-ellipsis">
						{#if isMine && !isActive}<span class="text-primary mr-1">●</span>{/if}
						{r.entry_name}
						{#if isActive}
							<span
								class="ml-1.5 text-[10px] font-bold uppercase tracking-[0.04em] px-2 py-0.5 rounded-full text-primary"
								style:background="rgba(212,175,55,0.16)"
							>VIEWING</span>
						{:else if isMine}
							<span class="text-[10.5px] font-semibold ml-1.5 text-base-content/55">· also yours</span>
						{/if}
					</div>
					<div class="text-[11px] text-base-content/55">{r.user_name}</div>
				</div>
				<span class="font-display text-base">{r.total_points}</span>
				<span class="text-[11px] font-bold">
					{#if r.movement > 0}
						<span class="text-success">▲{r.movement}</span>
					{:else if r.movement < 0}
						<span class="text-error">▼{Math.abs(r.movement)}</span>
					{:else}
						<span class="text-base-content/55">—</span>
					{/if}
				</span>
			</button>
		{/each}
	</div>

	{#if activeRow}
		<p class="text-xs text-base-content/55 mt-3 pt-3 border-t border-base-300/50">
			{#if activeRow.position === 1}
				<strong class="text-base-content">{activeRow.entry_name}</strong> leads the pool.
			{:else}
				<strong class="text-base-content">{activeRow.entry_name}</strong> is
				<strong class="text-base-content">{gapAbove}</strong> off the place above,
				<strong class="text-base-content">{gapTo1st}</strong> off top.
			{/if}
		</p>
	{/if}
</section>

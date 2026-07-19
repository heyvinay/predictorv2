<script lang="ts">
	import DnaBar from '$lib/components/leaderboard/v4/DnaBar.svelte';
	import { dnaOf, rowDisplayName, multiEntryUserIds } from '$lib/utils/leaderboardV4';
	import type { LbEntryV4 } from '$lib/types/leaderboard';

	export let rows: LbEntryV4[];
	export let myUserId: string | null;

	$: multiOwners = multiEntryUserIds(rows);
	$: own = rows.filter((r) => r.user_id === myUserId);
	$: dnaRows = [...rows.slice(0, 8), ...own.filter((r) => r.position > 8)];
	$: leaderTotal = Math.max(1, rows[0]?.total_points ?? 1);

	function isOwn(r: LbEntryV4): boolean {
		return r.user_id === myUserId;
	}
</script>

<div class="stadium-card no-glow p-4">
	<h2 class="font-display font-extrabold uppercase tracking-wide">Points DNA</h2>
	<p class="mb-2 text-xs text-base-content/50">
		The anatomy of a winning entry — each bar splits an entry's total into exact scores, results,
		rarity, bracket rounds and bonuses. The top entries built on the same group-stage base; the
		bracket columns are where they pulled apart.
	</p>
	{#each dnaRows as r (r.entry_id)}
		<div
			class="grid grid-cols-[30px_1fr_52px] items-center gap-2 py-1 min-[720px]:grid-cols-[30px_200px_1fr_52px] {isOwn(
				r
			)
				? 'rounded-lg bg-primary/5 px-1'
				: ''}"
		>
			<span class="font-display text-xs font-extrabold text-base-content/40">#{r.position}</span>
			<span class="truncate text-[13px] {isOwn(r) ? 'font-bold' : ''}">{rowDisplayName(r, multiOwners)}</span>
			<span class="col-span-3 block min-[720px]:col-span-1" style="width:{(r.total_points / leaderTotal) * 100}%">
				<DnaBar split={dnaOf(r.breakdown)} labels />
			</span>
			<span class="hidden text-right font-display text-sm font-extrabold tabular-nums min-[720px]:block">{r.total_points}</span>
		</div>
	{/each}
	<p class="mt-1.5 text-[11px] text-base-content/40">
		Each segment shows its points where there's room — narrower slivers omit the label.
	</p>
</div>

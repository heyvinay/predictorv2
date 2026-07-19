<script lang="ts">
	import { track } from '$lib/analytics';
	import { rowDisplayName, groupPtsOf, koPtsOf, multiEntryUserIds } from '$lib/utils/leaderboardV4';
	import FlagCode from '$lib/components/leaderboard/v4/FlagCode.svelte';
	import type { LbEntryV4 } from '$lib/types/leaderboard';

	export let rows: LbEntryV4[];
	export let championTeam: string | null;
	export let myUserId: string | null;

	$: multiOwners = multiEntryUserIds(rows);
	$: top10 = rows.slice(0, 10);
</script>

<div class="stadium-card no-glow h-full p-4">
	<div class="mb-1 flex items-center justify-between">
		<h2 class="font-display font-extrabold">Leaderboard</h2>
		<span
			class="rounded-badge border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary"
			>🏁 Final</span
		>
	</div>
	<p class="mb-2 text-xs text-base-content/50">
		The board the prizes were paid on — every entry's split and the champion it backed.
	</p>

	<div
		class="grid grid-cols-[20px_1fr_40px_44px_48px] items-center gap-1.5 border-b border-base-300/60 pb-1 text-[9px] uppercase tracking-wider text-base-content/40"
	>
		<span></span><span></span><span class="text-right">Grp</span><span class="text-right">KO</span
		><span class="text-right">Total</span>
	</div>
	{#each top10 as r (r.entry_id)}
		<div
			class="grid grid-cols-[20px_1fr_40px_44px_48px] items-center gap-1.5 border-b border-base-300/40 py-1 text-[13px] {r.user_id ===
			myUserId
				? 'rounded-md bg-primary/5'
				: ''}"
		>
			<span class="font-display font-extrabold text-base-content/50">{r.position}</span>
			<span class="min-w-0">
				<span class="block truncate {r.position === 1 ? 'font-bold text-primary' : ''}"
					>{rowDisplayName(r, multiOwners)}{r.position === 1 ? ' 🏆' : ''}</span
				>
				<span
					class="flex items-center gap-1 text-[10px] {r.champion_pick === championTeam
						? 'font-bold text-primary'
						: 'text-base-content/40'}"
				>
					{#if r.champion_pick}
						<FlagCode team={r.champion_pick} size="sm" />
					{:else}
						—
					{/if}
					{#if championTeam}
						{r.champion_pick === championTeam ? '✓' : '✗'}
					{/if}
				</span>
			</span>
			<span class="text-right text-xs tabular-nums text-base-content/55"
				>{groupPtsOf(r, r.bonus_group_points ?? 0)}</span
			>
			<span class="text-right text-xs tabular-nums text-base-content/55"
				>{koPtsOf(r, r.bonus_knockout_points ?? 0)}</span
			>
			<span class="text-right font-display font-extrabold tabular-nums">{r.total_points}</span>
		</div>
	{/each}
	<p class="mt-2 text-center text-[11px] text-base-content/40">
		champion pick under each name · {rows.length} entries ·
		<a
			href="/leaderboard"
			class="text-primary"
			on:click={() => track('wrapup_leaderboard_full_clicked', {})}>standings are final → full table</a
		>
	</p>
</div>

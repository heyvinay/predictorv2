<script lang="ts">
	/** One standings row. Whole row is a button — Enter/click opens the
	 *  entry drawer (a11y per ACCEPTANCE). Own entries get the gold glow
	 *  highlight + YOU tag + gold total. */
	import type { LbEntryV4, LbStage } from '$lib/types/leaderboard';
	import { groupPtsOf, initialsOf, koPtsOf } from '$lib/utils/leaderboardV4';
	import FlagCode from './FlagCode.svelte';
	import RankCell from './RankCell.svelte';
	import YouTag from './YouTag.svelte';

	export let row: LbEntryV4;
	export let stage: LbStage;
	export let isOwn: boolean;
	export let gridClass: string;
	export let onOpen: (row: LbEntryV4) => void;

	$: bonusG = row.bonus_group_points ?? 0;
	$: bonusK = row.bonus_knockout_points ?? 0;
	$: groupPts = groupPtsOf(row, bonusG);
	$: koPts = koPtsOf(row, bonusK);
	$: groupTitle = `Group: ${groupPts - bonusG} match pts${
		bonusG ? ` + ${bonusG} bonus` : ' · no bonus questions hit yet'
	}`;
	$: koTitle = `Knockout: ${koPts - bonusK} bracket pts${
		bonusK ? ` + ${bonusK} bonus` : ' · no bonus questions hit yet'
	}`;
	$: finalists = row.finalist_picks ?? [];
	$: finAlive = row.finalists_alive ?? 0;
</script>

<button
	class="grid w-full items-center gap-3 border-t border-base-300/40 px-4 py-1.5 text-left transition-colors hover:bg-base-content/5 {gridClass} {isOwn
		? 'bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-[inset_3px_0_0_theme(colors.primary)]'
		: ''}"
	on:click={() => onOpen(row)}
>
	<span><RankCell rank={row.position} move={row.daily_movement} /></span>

	<span class="flex min-w-0 items-center gap-2.5">
		<span
			class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full font-display text-[10px] font-extrabold {isOwn
				? 'bg-primary/15 text-primary ring-[1.5px] ring-primary'
				: 'bg-base-300 text-base-content/70'}">{initialsOf(row.entry_name)}</span
		>
		<span class="flex min-w-0 flex-col leading-tight">
			<span class="flex items-center gap-1.5 truncate text-[13px] font-bold text-base-content">
				<span class="truncate">{row.entry_name}</span>
				{#if isOwn}<YouTag />{/if}
			</span>
			<span class="truncate text-[10.5px] text-base-content/55"
				>{isOwn ? 'your entry' : row.user_name}</span
			>
		</span>
	</span>

	<span class="flex">
		{#if row.champion_pick}
			<FlagCode team={row.champion_pick} alive={row.champion_alive ?? true} dot size="md" />
		{:else}
			<span class="text-xs text-base-content/30">—</span>
		{/if}
	</span>

	{#if stage === 'knockout'}
		<span
			class="flex justify-center gap-1"
			title="{finAlive} of {finalists.length || 2} finalist picks still alive"
		>
			{#each [0, 1] as i}
				<span
					class="h-2 w-2 rounded-full {i < finAlive
						? 'bg-success shadow-[0_0_6px_theme(colors.success/50%)]'
						: 'bg-base-300/80'}"
				></span>
			{/each}
		</span>
	{/if}

	<span
		class="hidden text-right font-display text-[13px] font-bold text-base-content/70 min-[880px]:block"
		title={groupTitle}
	>
		{groupPts}{#if bonusG}<span class="ml-0.5 align-super text-[8.5px] text-primary">+B</span>{/if}
	</span>
	<span
		class="hidden text-right font-display text-[13px] font-bold text-base-content/70 min-[880px]:block"
		title={koTitle}
	>
		{koPts}{#if bonusK}<span class="ml-0.5 align-super text-[8.5px] text-primary">+B</span>{/if}
	</span>

	<span
		class="text-right font-display text-[15px] font-extrabold {isOwn
			? 'text-primary'
			: 'text-base-content'}">{row.total_points}</span
	>
</button>

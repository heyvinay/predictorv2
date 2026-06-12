<script lang="ts">
	/** One standings row. Whole row is a button — Enter/click opens the
	 *  entry drawer (a11y per ACCEPTANCE). Own entries get the gold glow
	 *  highlight + YOU tag + gold total. */
	import type { LbEntryV4, LbStage } from '$lib/types/leaderboard';
	import { groupPtsOf, koPtsOf, rowDisplayName } from '$lib/utils/leaderboardV4';
	import FlagCode from './FlagCode.svelte';
	import RankCell from './RankCell.svelte';
	import Sparkline from './Sparkline.svelte';
	import YouTag from './YouTag.svelte';

	export let row: LbEntryV4;
	export let stage: LbStage;
	export let isOwn: boolean;
	export let gridClass: string;
	/** Users with >1 entries (computed from the UNFILTERED board). */
	export let multiOwners: Set<string>;
	/** Points-over-time series for this entry (≥2 to draw). */
	export let trajectory: number[] = [];
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

<!-- role="row"/"cell" pair with StandingsTable's role="table" grid —
     the element stays a real <button> (click/Enter open the drawer);
     the role gives screen readers row/column navigation. -->
<button
	role="row"
	class="group grid w-full items-center gap-2 border-t border-base-300/40 px-3 py-1.5 text-left transition-colors hover:bg-base-content/5 min-[880px]:gap-3 min-[880px]:px-4 {gridClass} {isOwn
		? 'bg-gradient-to-r from-primary/10 via-primary/[0.03] to-transparent shadow-[inset_3px_0_0_theme(colors.primary)]'
		: ''}"
	title="View this entry's predictions"
	on:click={() => onOpen(row)}
>
	<span role="cell"><RankCell rank={row.position} move={row.daily_movement} /></span>

	<span
		role="cell"
		class="flex min-w-0 items-center gap-1.5 text-[13px] font-bold text-base-content"
	>
		<span class="truncate">{rowDisplayName(row, multiOwners)}</span>
		{#if isOwn}<YouTag />{/if}
	</span>

	<span role="cell" class="hidden min-[880px]:flex">
		{#if row.champion_pick}
			<FlagCode team={row.champion_pick} alive={row.champion_alive ?? true} dot size="md" />
		{:else}
			<span class="text-xs text-base-content/30">—</span>
		{/if}
	</span>

	{#if stage === 'knockout'}
		<span
			role="cell"
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
		role="cell"
		class="hidden text-right font-display text-[13px] font-bold text-base-content/70 min-[880px]:block"
		title={groupTitle}
	>
		{groupPts}{#if bonusG}<span class="ml-0.5 align-super text-[8.5px] text-primary">+B</span>{/if}
	</span>
	<span
		role="cell"
		class="hidden text-right font-display text-[13px] font-bold text-base-content/70 min-[880px]:block"
		title={koTitle}
	>
		{koPts}{#if bonusK}<span class="ml-0.5 align-super text-[8.5px] text-primary">+B</span>{/if}
	</span>

	<span role="cell" class="hidden justify-self-center min-[880px]:flex">
		<Sparkline points={trajectory} />
	</span>

	<span
		role="cell"
		class="text-right font-display text-[15px] font-extrabold {isOwn
			? 'text-primary'
			: 'text-base-content'}">{row.total_points}</span
	>

	<span
		role="cell"
		class="text-center text-sm font-bold text-base-content/25 transition-colors group-hover:text-primary"
		aria-hidden="true">›</span
	>
</button>

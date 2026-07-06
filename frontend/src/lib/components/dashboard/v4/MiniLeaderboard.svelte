<script lang="ts">
	/** Right-column leaderboard card: the user's entries pinned on top
	 *  (real global ranks), then the overall top 10.
	 *
	 *  Compact single-line rows (user feedback, v2.165.0): one
	 *  "Person — Entry" label per row via rowDisplayName (THE naming
	 *  rule), light weight, tight padding. Section headers carry a
	 *  stronger band so the Your-entries / Top-of-the-table split
	 *  doesn't get lost between zebra rows. */
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { miniLbRows } from '$lib/utils/dashboardV4';
	import { displayRank, displayTotal, multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import MoveChip from '$lib/components/leaderboard/v4/MoveChip.svelte';
	import ProvisionalPill from '$lib/components/ProvisionalPill.svelte';
	import LiveProjectionPill from '$lib/components/LiveProjectionPill.svelte';

	export let rows: LbEntryV4[];
	export let userId: string | null;
	export let activeEntryId: string | null;
	export let totalEntries: number;
	/** "BRA 5–0 UZB" style label for the most-recently-finished fixture,
	 *  computed by the parent from the fixtures store. Surfaces under the
	 *  "X entries" footer as the freshness cue — "this is the last game
	 *  that contributed points to this board." */
	export let lastResult: string | null = null;
	export let live = false;

	$: ({ yours, top } = miniLbRows(rows, userId, 15, live));
	// Computed from the FULL board so the label can't flip with filters.
	$: multiOwners = multiEntryUserIds(rows);

	const MEDALS: Record<number, string> = {
		1: 'bg-primary/20 text-primary',
		2: 'bg-base-content/15 text-base-content/85',
		3: 'bg-warning/25 text-warning-text'
	};

	const HEAD_CLASS =
		'border-y border-base-300/60 bg-base-300/40 px-3.5 py-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.16em] text-base-content/80';
</script>

<section>
	<div class="mb-2 flex items-baseline justify-between gap-3">
		<h2 class="flex items-center gap-2 font-display text-lg font-bold tracking-wide text-base-content">
			Leaderboard
			<ProvisionalPill />
			{#if live}
				<span class="relative"><LiveProjectionPill /></span>
			{/if}
		</h2>
		<a
			href="/leaderboard"
			class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
			>Full table →</a
		>
	</div>

	<div class="overflow-hidden rounded-box border border-base-300/70 bg-base-200">
		{#if yours.length > 0}
			<div class="{HEAD_CLASS} border-t-0">Your entries</div>
			{#each yours as e, i (e.entry_id)}
				{@const isCurrent = e.entry_id === activeEntryId}
				<div
					class="relative grid grid-cols-[56px_minmax(0,1fr)_48px] items-center gap-2 px-3.5 py-1.5 {i >
					0
						? 'border-t border-base-300/30'
						: ''} {isCurrent ? 'bg-primary/10' : 'bg-primary/5'}"
				>
					<span
						class="absolute bottom-0 left-0 top-0 w-[3px] {isCurrent
							? 'bg-primary'
							: 'bg-primary/40'}"
					></span>
					<span class="flex items-center gap-1.5">
						<span
							class="grid h-[18px] min-w-[18px] place-items-center rounded-badge px-1 font-display text-[12px] font-bold {MEDALS[
								displayRank(e, live)
							] ?? 'text-base-content/75'}">{displayRank(e, live)}</span
						>
						<MoveChip move={e.daily_movement} />
					</span>
					<span class="truncate text-[12px] font-medium text-base-content/90"
						>{rowDisplayName(e, multiOwners)}</span
					>
					<span class="text-right font-display text-[12.5px] font-semibold tabular-nums text-primary"
						>{displayTotal(e, live)}</span
					>
				</div>
			{/each}
		{/if}

		<div class={HEAD_CLASS}>Top of the table</div>
		{#each top as e, i (e.entry_id)}
			{@const isOwn = userId != null && e.user_id === userId}
			<div
				class="relative grid grid-cols-[56px_minmax(0,1fr)_48px] items-center gap-2 px-3.5 py-1.5 {i >
				0
					? 'border-t border-base-300/30'
					: ''} {isOwn ? 'bg-primary/5' : ''}"
			>
				{#if isOwn}
					<span class="absolute bottom-0 left-0 top-0 w-[3px] bg-primary/40"></span>
				{/if}
				<span class="flex items-center gap-1.5">
					<span
						class="grid h-[18px] min-w-[18px] place-items-center rounded-badge px-1 font-display text-[12px] font-bold {MEDALS[
							displayRank(e, live)
						] ?? 'text-base-content/75'}">{displayRank(e, live)}</span
					>
					<MoveChip move={e.daily_movement} />
				</span>
				<span class="flex min-w-0 items-center gap-1.5">
					<span class="truncate text-[12px] font-medium text-base-content/90"
						>{rowDisplayName(e, multiOwners)}</span
					>
					{#if isOwn}
						<span
							class="flex-none rounded-badge bg-primary/20 px-1.5 py-px text-[8px] font-extrabold uppercase tracking-[0.14em] text-primary"
							>You</span
						>
					{/if}
				</span>
				<span
					class="text-right font-display text-[12.5px] font-semibold tabular-nums {isOwn
						? 'text-primary'
						: 'text-base-content/90'}">{displayTotal(e, live)}</span
				>
			</div>
		{/each}

		<div
			class="border-t border-base-300/60 bg-base-300/40 px-3.5 py-1.5 text-center text-[10.5px] font-semibold text-base-content/55"
		>
			{totalEntries} entries{#if lastResult}
				<span class="text-base-content/40"> · last result: </span>
				<b class="text-base-content/75">{lastResult}</b>
			{/if}
		</div>
	</div>
</section>

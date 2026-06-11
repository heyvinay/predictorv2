<script lang="ts">
	/** Right-column leaderboard card: the user's entries pinned on top
	 *  (real global ranks), then the overall top 10. Own rows get the
	 *  gold tint + left bar; the currently-selected entry gets the
	 *  stronger treatment. */
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import { miniLbRows } from '$lib/utils/dashboardV4';
	import MoveChip from '$lib/components/leaderboard/v4/MoveChip.svelte';

	export let rows: LbEntryV4[];
	export let userId: string | null;
	export let activeEntryId: string | null;
	export let totalEntries: number;

	$: ({ yours, top } = miniLbRows(rows, userId, 10));

	const MEDALS: Record<number, string> = {
		1: 'bg-primary/20 text-primary',
		2: 'bg-base-content/15 text-base-content/85',
		3: 'bg-warning/25 text-warning-text'
	};
</script>

<section>
	<div class="mb-2 flex items-baseline justify-between gap-3">
		<h2 class="font-display text-lg font-bold tracking-wide text-base-content">Leaderboard</h2>
		<a
			href="/leaderboard"
			class="whitespace-nowrap font-display text-[12px] font-extrabold text-primary transition-opacity hover:opacity-75"
			>Full table →</a
		>
	</div>

	<div class="overflow-hidden rounded-box border border-base-300/70 bg-base-200">
		{#if yours.length > 0}
			<div
				class="bg-base-300/20 px-3.5 py-1.5 text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
			>
				Your entries
			</div>
			{#each yours as e (e.entry_id)}
				{@const isCurrent = e.entry_id === activeEntryId}
				<div
					class="relative grid grid-cols-[64px_minmax(0,1fr)_52px] items-center gap-2 border-t border-base-300/40 px-3.5 py-2 {isCurrent
						? 'bg-primary/10'
						: 'bg-primary/5'}"
				>
					<span
						class="absolute bottom-0 left-0 top-0 w-[3px] {isCurrent
							? 'bg-primary'
							: 'bg-primary/40'}"
					></span>
					<span class="flex items-center gap-1.5">
						<span
							class="grid h-5 min-w-5 place-items-center rounded-badge px-1 font-display text-[13px] font-extrabold {MEDALS[
								e.position
							] ?? 'text-base-content/85'}">{e.position}</span
						>
						<MoveChip move={e.daily_movement} />
					</span>
					<span class="flex min-w-0 flex-col leading-tight">
						<span class="flex items-center gap-1.5">
							<span class="truncate text-[12.5px] font-bold text-base-content">{e.user_name}</span>
							<span
								class="flex-none rounded-badge bg-primary/20 px-1.5 py-px text-[8.5px] font-extrabold uppercase tracking-[0.14em] text-primary"
								>You</span
							>
						</span>
						<span class="truncate text-[10.5px] font-semibold text-base-content/55"
							>{e.entry_name}</span
						>
					</span>
					<span class="text-right font-display text-[13.5px] font-extrabold tabular-nums text-primary"
						>{e.total_points}</span
					>
				</div>
			{/each}
		{/if}

		<div
			class="bg-base-300/20 px-3.5 py-1.5 text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55 {yours.length >
			0
				? 'border-t border-base-300/40'
				: ''}"
		>
			Top of the table
		</div>
		{#each top as e (e.entry_id)}
			{@const isOwn = userId != null && e.user_id === userId}
			<div
				class="relative grid grid-cols-[64px_minmax(0,1fr)_52px] items-center gap-2 border-t border-base-300/40 px-3.5 py-2 {isOwn
					? 'bg-primary/5'
					: ''}"
			>
				{#if isOwn}
					<span class="absolute bottom-0 left-0 top-0 w-[3px] bg-primary/40"></span>
				{/if}
				<span class="flex items-center gap-1.5">
					<span
						class="grid h-5 min-w-5 place-items-center rounded-badge px-1 font-display text-[13px] font-extrabold {MEDALS[
							e.position
						] ?? 'text-base-content/85'}">{e.position}</span
					>
					<MoveChip move={e.daily_movement} />
				</span>
				<span class="flex min-w-0 flex-col leading-tight">
					<span class="flex items-center gap-1.5">
						<span class="truncate text-[12.5px] font-bold text-base-content">{e.user_name}</span>
						{#if isOwn}
							<span
								class="flex-none rounded-badge bg-primary/20 px-1.5 py-px text-[8.5px] font-extrabold uppercase tracking-[0.14em] text-primary"
								>You</span
							>
						{/if}
					</span>
					<span class="truncate text-[10.5px] font-semibold text-base-content/55"
						>{e.entry_name}</span
					>
				</span>
				<span
					class="text-right font-display text-[13.5px] font-extrabold tabular-nums {isOwn
						? 'text-primary'
						: 'text-base-content'}">{e.total_points}</span
				>
			</div>
		{/each}

		<div
			class="border-t border-base-300/40 bg-base-300/20 px-3.5 py-1.5 text-center text-[10.5px] font-semibold text-base-content/55"
		>
			{totalEntries} entries
		</div>
	</div>
</section>

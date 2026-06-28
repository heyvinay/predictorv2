<script lang="ts">
	/** Full pool roll for a knockout fixture.
	 *
	 *  Same purpose as the existing PoolPickedWhat (the score-pick variant)
	 *  but pivoted to advancement-by-team. Tabbed by side; your row is
	 *  always rendered at the top of its tab when present. */
	import { goto } from '$app/navigation';
	import type { Fixture } from '$types';
	import type { KoMatchDetailResponse, KoPoolRollEntry } from '$lib/types/results';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;
	export let youReference: string | null = null;

	type SideKey = 'all' | 'home' | 'away';
	let activeSide: SideKey = 'all';

	$: filtered = (() => {
		if (activeSide === 'all') return bundle.pool_roll;
		const team = activeSide === 'home' ? bundle.home_team : bundle.away_team;
		return bundle.pool_roll.filter((r) => r.pick === team);
	})();

	// Surface YOU row at the top of whichever tab is active.
	$: ordered = (() => {
		if (!youReference) return filtered;
		const you = filtered.find((r) => r.entry_reference === youReference);
		if (!you) return filtered;
		const rest = filtered.filter((r) => r.entry_reference !== youReference);
		return [you, ...rest];
	})();

	$: homeCount = bundle.pool_roll.filter((r) => r.pick === bundle.home_team).length;
	$: awayCount = bundle.pool_roll.filter((r) => r.pick === bundle.away_team).length;

	function openEntry(row: KoPoolRollEntry) {
		void goto(`/leaderboard?entry=${row.entry_id}`);
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-3 flex items-center justify-between">
		<span class="font-display text-[15px]">Who picked what</span>
		<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
			>tap to filter</span
		>
	</div>

	<!-- Side tabs -->
	<div class="mb-3 flex flex-wrap gap-1.5">
		<button
			type="button"
			class="rounded-full border px-3 py-1 text-[11px] font-semibold transition {activeSide ===
			'all'
				? 'border-primary/40 bg-primary/15 text-primary'
				: 'border-base-300/40 text-base-content/55 hover:text-base-content'}"
			on:click={() => (activeSide = 'all')}
		>
			All {bundle.pool_roll.length}
		</button>
		<button
			type="button"
			class="rounded-full border px-3 py-1 text-[11px] font-semibold transition {activeSide ===
			'home'
				? 'border-primary/40 bg-primary/15 text-primary'
				: 'border-base-300/40 text-base-content/55 hover:text-base-content'}"
			on:click={() => (activeSide = 'home')}
		>
			<TeamName name={bundle.home_team} /> · {homeCount}
		</button>
		<button
			type="button"
			class="rounded-full border px-3 py-1 text-[11px] font-semibold transition {activeSide ===
			'away'
				? 'border-primary/40 bg-primary/15 text-primary'
				: 'border-base-300/40 text-base-content/55 hover:text-base-content'}"
			on:click={() => (activeSide = 'away')}
		>
			<TeamName name={bundle.away_team} /> · {awayCount}
		</button>
	</div>

	{#if ordered.length === 0}
		<div class="rounded-btn bg-base-300/15 px-3 py-3 text-center text-[12px] text-base-content/55">
			No entries on this side yet.
		</div>
	{:else}
		<!-- 3-column entry grid on desktop, single column on mobile -->
		<div
			class="grid grid-cols-1 gap-x-3 gap-y-1 text-[12px] sm:grid-cols-2 lg:grid-cols-3"
		>
			{#each ordered as row (row.entry_id)}
				{@const isYou = youReference !== null && row.entry_reference === youReference}
				<button
					type="button"
					on:click={() => openEntry(row)}
					class="flex items-center justify-between gap-2 rounded-btn px-2 py-1 text-left transition {isYou
						? 'bg-primary/15 font-bold text-primary'
						: 'hover:bg-base-300/25'}"
				>
					<span class="min-w-0 flex-1 truncate">
						{#if row.rank !== null && row.rank <= 10}<span class="text-primary">★</span> {/if}{row.user_name}{#if isYou}<span class="opacity-70"> (you)</span>{/if}
					</span>
					{#if activeSide === 'all'}
						<span
							class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold {row.pick ===
							bundle.home_team
								? 'bg-amber-400/20 text-amber-300'
								: 'bg-emerald-400/20 text-emerald-300'}"
						>
							<TeamName name={row.pick} forceCode />
						</span>
					{/if}
				</button>
			{/each}
		</div>

		<div class="mt-3 text-[10.5px] text-base-content/45">
			Sorted by current leaderboard rank · your row pinned to top
		</div>
	{/if}
</div>

<script lang="ts">
	/** Upcoming: "Who picked what" with All/{Home}/Draw/{Away} filter chips.
	 *  Rows ordered by overall rank (B.3). */
	import type { Fixture } from '$types';
	import type { CommunityPredictionWithRank, OutcomePayout } from '$lib/types/results';
	import type { Side } from '$lib/utils/matchDetailV4';
	import { sideOf } from '$lib/utils/matchDetailV4';
	import { displayTeamName } from '$lib/utils/teamName';

	export let fixture: Fixture;
	export let preds: CommunityPredictionWithRank[];
	export let payouts: Record<Side, OutcomePayout>;
	export let youReference: string | null;

	let filter: 'all' | Side = 'all';

	$: filters = [
		{ k: 'all' as const, label: 'All' },
		{ k: 'home' as const, label: displayTeamName(fixture.home_team) },
		{ k: 'draw' as const, label: 'Draw' },
		{ k: 'away' as const, label: displayTeamName(fixture.away_team) }
	];
	$: sorted = [...preds].sort((a, b) => (a.rank ?? 9999) - (b.rank ?? 9999));
	$: filtered = sorted.filter(
		(p) => filter === 'all' || sideOf(p.home_score, p.away_score) === filter
	);

	function ordinal(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}
	function initials(name: string): string {
		return name
			.split(/\s+/)
			.map((w) => w[0])
			.join('')
			.slice(0, 2)
			.toUpperCase();
	}
	function sideLabel(side: Side): string {
		return side === 'draw'
			? 'DRAW'
			: side === 'home'
			? displayTeamName(fixture.home_team).slice(0, 3).toUpperCase()
			: displayTeamName(fixture.away_team).slice(0, 3).toUpperCase();
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2 flex items-center justify-between">
		<span class="font-display text-[16px]">Who picked what</span>
		<span class="text-[11px] text-base-content/55">by overall standing</span>
	</div>

	<div class="mb-2 flex flex-wrap gap-1.5">
		{#each filters as f (f.k)}
			<button
				class="rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors {filter === f.k
					? 'bg-primary/15 text-primary ring-1 ring-primary/40'
					: 'bg-base-300/30 text-base-content/70 hover:bg-base-300/50'}"
				on:click={() => (filter = f.k)}
			>
				{f.label}
			</button>
		{/each}
	</div>

	{#each filtered as p (p.entry_reference)}
		{@const side = sideOf(p.home_score, p.away_score)}
		{@const you = youReference !== null && p.entry_reference === youReference}
		<div
			class="flex items-center gap-2.5 rounded-btn px-2 py-1.5 {you
				? 'bg-primary/10 ring-1 ring-primary/40'
				: ''}"
		>
			<span
				class="grid h-[28px] w-[28px] flex-none place-items-center rounded-full bg-base-300/50 text-[10px] font-extrabold {you
					? 'bg-primary/30 text-primary'
					: 'text-base-content/70'}">{initials(p.user_name)}</span
			>
			<div class="min-w-0 flex-1">
				<div class="flex items-center gap-2 truncate text-[12.5px] font-semibold">
					{p.user_name}
					{#if you}
						<span
							class="rounded-badge bg-primary/20 px-1.5 py-px text-[9px] font-extrabold tracking-[0.08em] text-primary"
							>YOU</span
						>
					{/if}
				</div>
				<div class="text-[11px] text-base-content/55">
					{p.rank != null ? `${ordinal(p.rank)} overall` : '—'}
				</div>
			</div>
			<span class="font-display text-[13px]">{p.home_score}-{p.away_score}</span>
			<span
				class="rounded-badge px-1.5 py-0.5 text-[9.5px] font-extrabold tracking-[0.04em] {payouts[side]
					.rarity > 0
					? 'bg-primary/15 text-primary'
					: 'bg-base-300/30 text-base-content/55'}"
			>
				{payouts[side].band.toUpperCase()} · {sideLabel(side)}
			</span>
		</div>
	{:else}
		<div class="px-4 py-5 text-center text-[12.5px] text-base-content/55">
			No entries matching this filter.
		</div>
	{/each}

	<div class="mt-2 border-t border-base-300/40 pt-2 text-center text-[10.5px] text-base-content/40">
		Points are provisional — they lock in the instant the final whistle blows.
	</div>
</div>

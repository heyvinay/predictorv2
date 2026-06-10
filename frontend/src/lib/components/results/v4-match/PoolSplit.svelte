<script lang="ts">
	/** Upcoming: 3-segment outcome bar + per-outcome payout cards.
	 *  All point values template from scoring-rules via payouts (C.1). */
	import type { Fixture } from '$types';
	import type { OutcomePayout } from '$lib/types/results';
	import type { Side } from '$lib/utils/matchDetailV4';
	import { displayTeamName } from '$lib/utils/teamName';

	export let fixture: Fixture;
	export let payouts: Record<Side, OutcomePayout>;
	export let yourSide: Side | null;

	$: total = payouts.home.count + payouts.draw.count + payouts.away.count;
	$: home3 = displayTeamName(fixture.home_team).slice(0, 3).toUpperCase();
	$: away3 = displayTeamName(fixture.away_team).slice(0, 3).toUpperCase();

	const CARDS: { side: Side; cls: string }[] = [
		{ side: 'home', cls: 'bg-warning/25 text-warning-text' },
		{ side: 'draw', cls: 'bg-base-300/60 text-base-content/70' },
		{ side: 'away', cls: 'bg-error/25 text-error' }
	];

	function cardLabel(side: Side): string {
		return side === 'home'
			? `${displayTeamName(fixture.home_team)} win`
			: side === 'away'
			? `${displayTeamName(fixture.away_team)} win`
			: 'Draw';
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2.5 flex items-center justify-between">
		<span class="font-display text-[15px]">How the pool is split</span>
		<span class="text-[11px] text-base-content/55">{total} entries · outcome</span>
	</div>

	<div class="flex h-7 overflow-hidden rounded-btn text-[10px] font-extrabold">
		{#if payouts.home.pct > 0}
			<div
				class="flex items-center justify-center bg-warning/30 text-warning-text"
				style="flex-basis: {payouts.home.pct}%"
			>
				{home3} {payouts.home.pct}
			</div>
		{/if}
		{#if payouts.draw.pct > 0}
			<div
				class="flex items-center justify-center bg-base-300/70 text-base-content/70"
				style="flex-basis: {payouts.draw.pct}%"
			>
				DRAW {payouts.draw.pct}
			</div>
		{/if}
		{#if payouts.away.pct > 0}
			<div
				class="flex items-center justify-center bg-error/30 text-error"
				style="flex-basis: {payouts.away.pct}%"
			>
				{away3} {payouts.away.pct}
			</div>
		{/if}
	</div>

	<div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
		{#each CARDS as c (c.side)}
			{@const p = payouts[c.side]}
			<div
				class="rounded-btn border border-base-300/50 bg-base-300/15 p-2.5 {yourSide === c.side
					? 'ring-1 ring-primary/60'
					: ''}"
			>
				<div class="flex items-center justify-between gap-1">
					<span class="text-[10.5px] font-bold text-base-content/70"
						>{cardLabel(c.side)} · {p.count} {p.count === 1 ? 'pick' : 'picks'}</span
					>
					{#if yourSide === c.side}
						<span
							class="rounded-badge bg-primary/20 px-1.5 text-[9px] font-extrabold tracking-[0.06em] text-primary"
							>you</span
						>
					{/if}
				</div>
				<div
					class="mt-1.5 inline-block rounded-badge px-1.5 py-px text-[9px] font-extrabold tracking-[0.06em] {p.rarity >
					0
						? 'bg-primary/15 text-primary'
						: 'bg-base-300/40 text-base-content/55'}"
				>
					{p.band.toUpperCase()}
				</div>
				<div class="mt-1.5 text-[11.5px]">
					<span class="text-base-content/55">would pay </span>
					<b class="font-display text-[14px]">+{p.total}</b>
					<span class="text-[10.5px] text-base-content/55"> (+{p.rarity} rarity)</span>
				</div>
			</div>
		{/each}
	</div>
</div>

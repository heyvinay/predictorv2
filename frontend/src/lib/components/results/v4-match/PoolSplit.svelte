<script lang="ts">
	/** Upcoming: 3-segment outcome bar + per-outcome payout cards.
	 *  All point values template from scoring-rules via payouts (C.1). */
	import type { Fixture } from '$types';
	import type { OutcomePayout } from '$lib/types/results';
	import type { Side } from '$lib/utils/matchDetailV4';
	import { teamCode } from '$lib/utils/teamCodes';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let payouts: Record<Side, OutcomePayout>;
	export let yourSide: Side | null;

	$: total = payouts.home.count + payouts.draw.count + payouts.away.count;
	// Real FIFA codes (KOR), not first-3-letters pseudo-codes (SOU).
	$: home3 = teamCode(fixture.home_team);
	$: away3 = teamCode(fixture.away_team);

	const SIDES: Side[] = ['home', 'draw', 'away'];

	function cardTeam(side: Side): string | null {
		return side === 'home' ? fixture.home_team : side === 'away' ? fixture.away_team : null;
	}
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2.5 flex items-center justify-between">
		<span class="font-display text-[15px]">How the pool is split</span>
		<span class="text-[11px] text-base-content/55">{total} entries · outcome</span>
	</div>

	<!-- Chart fills use the Tailwind palette, NOT surface tokens — the
	     warning/error/base fills rendered nearly invisible on the dark
	     card (the "surface tokens are not chart fills" rule). Same
	     home=amber / draw=slate / away=emerald mapping as ScorelineSpread
	     so the two cards on this page read as one system. -->
	<div class="flex h-7 overflow-hidden rounded-btn text-[10px] font-extrabold">
		{#if payouts.home.pct > 0}
			<div
				class="flex items-center justify-center bg-amber-400 text-slate-900"
				style="flex-basis: {payouts.home.pct}%"
			>
				{home3} {payouts.home.pct}
			</div>
		{/if}
		{#if payouts.draw.pct > 0}
			<div
				class="flex items-center justify-center bg-slate-400 text-slate-900"
				style="flex-basis: {payouts.draw.pct}%"
			>
				DRAW {payouts.draw.pct}
			</div>
		{/if}
		{#if payouts.away.pct > 0}
			<div
				class="flex items-center justify-center bg-emerald-400 text-emerald-950"
				style="flex-basis: {payouts.away.pct}%"
			>
				{away3} {payouts.away.pct}
			</div>
		{/if}
	</div>

	<div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
		{#each SIDES as side (side)}
			{@const p = payouts[side]}
			<div
				class="rounded-btn border border-base-300/50 bg-base-300/15 p-2.5 {yourSide === side
					? 'ring-1 ring-primary/60'
					: ''}"
			>
				<div class="flex items-center justify-between gap-1">
					<span class="text-[10.5px] font-bold text-base-content/70"
						>{#if cardTeam(side)}<TeamName name={cardTeam(side)} /> win{:else}Draw{/if} · {p.count}
						{p.count === 1 ? 'pick' : 'picks'}</span
					>
					{#if yourSide === side}
						<span
							class="rounded-badge bg-primary/20 px-1.5 text-[9px] font-extrabold tracking-[0.06em] text-primary"
							>you</span
						>
					{/if}
				</div>
				<!-- band is null while rarity is paused — no chip, no rarity
				     suffix, just the flat payout. -->
				{#if p.band}
					<div
						class="mt-1.5 inline-block rounded-badge px-1.5 py-px text-[9px] font-extrabold tracking-[0.06em] {p.rarity >
						0
							? 'bg-primary/15 text-primary'
							: 'bg-base-300/40 text-base-content/55'}"
					>
						{p.band.toUpperCase()}
					</div>
				{/if}
				<div class="mt-1.5 text-[11.5px]">
					<b class="font-display text-[14px]">+{p.total} pts</b>
					{#if p.band}
						<span class="text-[10.5px] text-base-content/55"> · +{p.rarity} rarity</span>
					{/if}
				</div>
			</div>
		{/each}
	</div>
</div>

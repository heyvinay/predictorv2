<!--
  Single match card for the bidirectional Mission carousel.

  Renders status badge (LIVE+clock / FULL TIME / date+kickoff), group or
  round label, both teams (flag + name + score with loser dimmed), the
  locked pick, a points/state chip, and either:
    - finished: rarity payoff line "Rare exact · only X% of the pool"
                (uses matchBreakdown.computeBreakdown for chip set + tier)
    - live/upcoming: 3-segment MissionCrowdBar from community predictions

  No editable pick affordance — single-phase tournament locks everything
  at the deadline.
-->
<script lang="ts">
	import type { Fixture, MatchPrediction, CommunityPredictionsResponse } from '$types';
	import type { FixtureAgreement } from '$api/predictions';
	import type { ScoringConfig } from '$api/competition';
	import { computeBreakdown, matchState } from '$lib/utils/matchBreakdown';
	import { teamCode, flagIsoCode } from '$lib/utils/teamCodes';
	import MissionCrowdBar from './MissionCrowdBar.svelte';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined;
	export let agreement: FixtureAgreement | undefined;
	export let community: CommunityPredictionsResponse | undefined;
	export let scoringConfig: ScoringConfig;

	$: state = matchState(fixture);
	$: bd = computeBreakdown(fixture, prediction, agreement, scoringConfig);

	$: homeWin = fixture.score ? fixture.score.outcome === '1' : false;
	$: awayWin = fixture.score ? fixture.score.outcome === '2' : false;

	$: homeCode = teamCode(fixture.home_team);
	$: awayCode = teamCode(fixture.away_team);
	$: homeIso = flagIsoCode(homeCode);
	$: awayIso = flagIsoCode(awayCode);

	function outcomeOf(home: number, away: number): 'home' | 'draw' | 'away' {
		if (home > away) return 'home';
		if (home < away) return 'away';
		return 'draw';
	}

	$: yourBucket = prediction ? outcomeOf(prediction.home_score, prediction.away_score) : null;
	$: yourPickLabel = yourBucket === 'home' ? homeCode : yourBucket === 'away' ? awayCode : 'draw';

	function formatKickoff(iso: string): string {
		const d = new Date(iso);
		const day = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase();
		const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
		return `${day} · ${time}`;
	}

	$: statusLabel =
		state === 'live'
			? `LIVE ${fixture.minute ?? ''}'`
			: state === 'finished'
				? 'FULL TIME'
				: formatKickoff(fixture.kickoff);

	$: stageLabel = fixture.group ? `GROUP ${fixture.group}` : fixture.stage.replace(/_/g, ' ').toUpperCase();

	// Rarity payoff (finished cards). Uses agreement counts as the crowd %.
	$: rarityCrowdPct =
		agreement && agreement.total > 0
			? Math.round((agreement.agrees_outcome / agreement.total) * 100)
			: null;
</script>

<div
	class="rounded-box border bg-base-200 p-3.5 shadow-card flex flex-col gap-2 cursor-pointer hover:-translate-y-0.5 hover:border-primary/50 transition-all h-full"
	class:border-error={state === 'live'}
	style:border-color={state === 'live' ? 'rgba(185,28,28,0.55)' : undefined}
	on:click={() => (window.location.href = `/results/${fixture.id}`)}
	on:keydown={(e) => e.key === 'Enter' && (window.location.href = `/results/${fixture.id}`)}
	role="button"
	tabindex="0"
>
	<!-- Top row: status badge + stage/group -->
	<div class="flex justify-between items-center text-[10.5px] font-bold uppercase tracking-[0.06em] text-base-content/55">
		<span class:text-error={state === 'live'} class="flex items-center gap-1.5">
			{#if state === 'live'}
				<span class="w-1.5 h-1.5 rounded-full bg-error animate-pulse"></span>
			{/if}
			{statusLabel}
		</span>
		<span>{stageLabel}</span>
	</div>

	<!-- Teams -->
	<div class="flex flex-col gap-1">
		<div class="flex items-center gap-2.5 py-0.5" class:opacity-50={awayWin}>
			{#if homeIso}
				<span class="fi fi-{homeIso} w-[22px] h-4 rounded-sm flex-none shadow-[0_0_0_1px_rgba(0,0,0,0.25)]"></span>
			{:else}
				<span class="w-[22px] h-4 rounded-sm bg-base-300 flex-none"></span>
			{/if}
			<span class="text-sm font-semibold flex-1 truncate">{fixture.home_team}</span>
			{#if fixture.score}
				<span class="font-display font-extrabold text-lg">{fixture.score.home_score}</span>
			{:else}
				<span class="font-display font-extrabold text-lg text-base-content/30">–</span>
			{/if}
		</div>
		<div class="flex items-center gap-2.5 py-0.5" class:opacity-50={homeWin}>
			{#if awayIso}
				<span class="fi fi-{awayIso} w-[22px] h-4 rounded-sm flex-none shadow-[0_0_0_1px_rgba(0,0,0,0.25)]"></span>
			{:else}
				<span class="w-[22px] h-4 rounded-sm bg-base-300 flex-none"></span>
			{/if}
			<span class="text-sm font-semibold flex-1 truncate">{fixture.away_team}</span>
			{#if fixture.score}
				<span class="font-display font-extrabold text-lg">{fixture.score.away_score}</span>
			{:else}
				<span class="font-display font-extrabold text-lg text-base-content/30">–</span>
			{/if}
		</div>
	</div>

	<!-- Context strip: crowd bar (live/upcoming) or rarity payoff (finished) -->
	{#if state === 'finished' && prediction}
		<div class="mt-2 pt-2 border-t border-base-300/60 flex items-center gap-2">
			{#if bd.tier === 'tier-exact'}
				<span
					class="font-mono font-bold text-[10px] uppercase tracking-[0.04em] px-1.5 py-0.5 rounded"
					style:background="rgba(5,150,105,0.18)"
					style:color="#34d399"
				>
					{bd.rarityPill.lab} exact
				</span>
				{#if rarityCrowdPct != null}
					<span class="text-[10.5px] text-base-content/55">only {rarityCrowdPct}% of the pool</span>
				{/if}
			{:else if bd.tier === 'tier-outcome'}
				<span
					class="font-mono font-bold text-[10px] uppercase tracking-[0.04em] px-1.5 py-0.5 rounded"
					style:background="rgba(217,119,6,0.20)"
					style:color="var(--warning-text, #fbbf24)"
				>
					Right winner
				</span>
				{#if rarityCrowdPct != null}
					<span class="text-[10.5px] text-base-content/55">only {rarityCrowdPct}% of the pool</span>
				{/if}
			{:else}
				<span
					class="font-mono font-bold text-[10px] uppercase tracking-[0.04em] text-base-content/55 px-1.5 py-0.5 rounded bg-base-300/40"
				>
					Missed
				</span>
				{#if rarityCrowdPct != null}
					<span class="text-[10.5px] text-base-content/55">{rarityCrowdPct}% backed your call</span>
				{/if}
			{/if}
		</div>
	{:else if community || state === 'live' || state === 'locked' || state === 'open'}
		<MissionCrowdBar community={community ?? null} yourPickBucket={yourBucket} yourPickLabel={yourPickLabel} />
	{/if}

	<!-- Footer: locked pick + points chip -->
	<div class="mt-2 pt-2.5 border-t border-base-300/60 flex justify-between items-center text-[11px]">
		<span class="text-base-content/55">
			Your pick: <strong class="text-base-content/72">{prediction ? `${prediction.home_score}-${prediction.away_score}` : '—'}</strong>
		</span>
		{#if state === 'finished'}
			<span
				class="font-mono font-bold text-[11px] px-1.5 py-0.5 rounded"
				class:bg-success={false}
				style:background={bd.tier === 'tier-exact' ? 'rgba(5,150,105,0.18)' : bd.tier === 'tier-outcome' ? 'rgba(217,119,6,0.20)' : 'rgba(42,53,82,0.55)'}
				style:color={bd.tier === 'tier-exact' ? '#34d399' : bd.tier === 'tier-outcome' ? 'var(--warning-text, #fbbf24)' : 'rgba(226,232,240,0.55)'}
			>
				{bd.totalDisplay}
			</span>
		{:else if state === 'live'}
			<span
				class="font-mono font-bold text-[11px] px-1.5 py-0.5 rounded"
				style:background={bd.liveResult ? 'rgba(217,119,6,0.20)' : 'rgba(42,53,82,0.55)'}
				style:color={bd.liveResult ? 'var(--warning-text, #fbbf24)' : 'rgba(226,232,240,0.55)'}
			>
				{bd.liveResult ? `+${bd.totalPts} so far` : 'pending'}
			</span>
		{/if}
	</div>
</div>

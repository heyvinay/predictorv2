<script lang="ts">
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { track } from '$lib/analytics';
	import PointsCellGroup from './PointsCellGroup.svelte';

	export let fixture: Fixture;
	export let prediction: MatchPredictionWithPoints | undefined;
	export let striped = false;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: score = fixture.score;
	$: homeLoses = !!score && score.home_score < score.away_score;
	$: awayLoses = !!score && score.away_score < score.home_score;
	$: pickLabel = prediction ? `${prediction.home_score}-${prediction.away_score}` : null;
	$: dateLabel = new Date(fixture.kickoff).toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short'
	});
</script>

<a
	href={`/results/${fixture.id}`}
	on:click={() => track('match_detail_opened', { fixture_id: fixture.id, source: 'results_group_row' })}
	class="block border-t border-base-300/45 transition-colors first:border-t-0 hover:bg-primary/5
		{striped && !isLive ? 'bg-base-300/15 lg:bg-transparent' : ''}
		{isLive ? 'border-l-4 border-l-success bg-success/5' : ''}"
	aria-label={`Open match detail for ${displayTeamName(fixture.home_team)} vs ${displayTeamName(fixture.away_team)}`}
>
	<!-- Desktop grid -->
	<div
		class="hidden items-center gap-2 px-3 py-1.5 sm:grid sm:grid-cols-[minmax(90px,1fr)_70px_minmax(90px,1fr)_56px_92px]"
	>
		<div class="flex items-center justify-end gap-2 {homeLoses ? 'opacity-60' : ''}">
			<span class="truncate text-[13px] font-semibold">{displayTeamName(fixture.home_team)}</span>
			{#if hasFlag(fixture.home_team)}
				<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{/if}
		</div>
		<div class="text-center">
			{#if score}
				<span
					class="font-display text-[15px] {isLive
						? 'inline-block rounded-md bg-success px-1.5 py-0.5 text-white'
						: ''}"
				>
					<b class={homeLoses ? 'opacity-60' : ''}>{score.home_score}</b>
					<span class="px-0.5 {isLive ? 'text-white/70' : 'text-base-content/40'}">–</span>
					<b class={awayLoses ? 'opacity-60' : ''}>{score.away_score}</b>
				</span>
			{:else}
				<span class="text-base-content/30">———</span>
			{/if}
			<div class="text-[10px] text-base-content/55">
				{#if isLive}
					<span class="inline-block rounded bg-success px-1.5 py-0.5 font-bold text-white">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}{fixture.group ? ` · GRP ${fixture.group}` : ''}
				{/if}
			</div>
		</div>
		<div class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
			{#if hasFlag(fixture.away_team)}
				<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{/if}
			<span class="truncate text-[13px] font-semibold">{displayTeamName(fixture.away_team)}</span>
		</div>
		<div class="text-center">
			{#if pickLabel}
				<span class="font-display text-[13px]">{pickLabel}</span>
			{:else}
				<span class="text-[11px] text-base-content/30">No pick</span>
			{/if}
		</div>
		<div class="text-right">
			<PointsCellGroup points={prediction?.points ?? null} />
		</div>
	</div>

	<!-- Mobile stacked card (HANDOVER §7.5) -->
	<div class="flex flex-col gap-1 px-3 py-1.5 sm:hidden">
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {homeLoses ? 'opacity-60' : ''}">
				{#if hasFlag(fixture.home_team)}
					<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.home_team)}
					>{teamCode(fixture.home_team)}</span
				>
			</span>
			<span
				class="font-display text-[15px] {isLive
					? 'inline-block min-w-[1.5rem] rounded-md bg-success px-1.5 py-0.5 text-center text-white'
					: ''}"
			>
				{#if score}{score.home_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
				{#if hasFlag(fixture.away_team)}
					<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.away_team)}
					>{teamCode(fixture.away_team)}</span
				>
			</span>
			<!-- v2.181.0: away_score wears the same solid-success chip as
			     home_score during LIVE. Was 'text-success' only — visible
			     asymmetry where the top score had a green pill background
			     and the bottom didn't. FixtureRowKo was already symmetric;
			     this brings FixtureRowGroup in line. -->
			<span
				class="font-display text-[15px] {isLive
					? 'inline-block min-w-[1.5rem] rounded-md bg-success px-1.5 py-0.5 text-center text-white'
					: ''}"
			>
				{#if score}{score.away_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div
			class="mt-0.5 flex items-center justify-between gap-2 border-t border-dashed border-base-300/40 pt-1.5 text-[12px]"
		>
			<span class="text-base-content/55">
				{#if isLive}
					<span class="inline-block rounded bg-success px-1.5 py-0.5 font-bold text-white">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}
				{/if}
				· Your pick: <span class="font-display">{pickLabel ?? '—'}</span>
			</span>
			<PointsCellGroup points={prediction?.points ?? null} />
		</div>
	</div>
</a>

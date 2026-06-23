<script lang="ts">
	import type { Fixture } from '$types';
	import { displayTeamName } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { track } from '$lib/analytics';
	import BracketChip from './BracketChip.svelte';
	import PointsCellKo from './PointsCellKo.svelte';

	export let fixture: Fixture;
	export let roundPicks: Set<string>;
	export let stagePoints: number;
	export let striped = false;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: score = fixture.score;
	$: homeLoses = !!score && score.home_score < score.away_score;
	$: awayLoses = !!score && score.away_score < score.home_score;
	$: isThirdPlace = fixture.stage === 'third_place';
	$: seeded = !/\d/.test(fixture.home_team) && !/\d/.test(fixture.away_team);
	$: homePicked = seeded && !isThirdPlace && roundPicks.has(fixture.home_team);
	$: awayPicked = seeded && !isThirdPlace && roundPicks.has(fixture.away_team);
	$: hits = (homePicked ? 1 : 0) + (awayPicked ? 1 : 0);
	$: dateLabel = new Date(fixture.kickoff).toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short'
	});
</script>

<a
	href={`/results/${fixture.id}`}
	on:click={() => track('match_detail_opened', { fixture_id: fixture.id, source: 'results_ko_row' })}
	class="block border-t border-base-300/45 transition-colors first:border-t-0 hover:bg-primary/5
		{striped && !isLive ? 'bg-base-300/15' : ''}
		{isLive ? 'border-l-4 border-l-success bg-success/5' : ''}"
	aria-label={`Open match detail for ${displayTeamName(fixture.home_team)} vs ${displayTeamName(fixture.away_team)}`}
>
	<!-- Desktop grid -->
	<div
		class="hidden items-center gap-2 px-3 py-1.5 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="flex items-center justify-end gap-2 {homeLoses ? 'opacity-60' : ''}">
			<span class="truncate text-[13px] font-semibold">
				{seeded ? displayTeamName(fixture.home_team) : 'TBD'}
			</span>
			{#if seeded && hasFlag(fixture.home_team)}
				<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{:else if !seeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[9px] font-extrabold text-base-content/55"
					>?</span
				>
			{/if}
		</div>
		<div class="text-center">
			{#if score}
				<span class="font-display text-[15px] {isLive ? 'text-success' : ''}">
					<b class={homeLoses ? 'opacity-60' : ''}>{score.home_score}</b>
					<span class="px-0.5 text-base-content/40">–</span>
					<b class={awayLoses ? 'opacity-60' : ''}>{score.away_score}</b>
				</span>
			{:else}
				<span class="text-base-content/30">———</span>
			{/if}
			<div class="text-[10px] text-base-content/55">
				{#if isLive}
					<span class="font-bold text-success">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}
				{/if}
			</div>
		</div>
		<div class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
			{#if seeded && hasFlag(fixture.away_team)}
				<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{:else if !seeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[9px] font-extrabold text-base-content/55"
					>?</span
				>
			{/if}
			<span class="truncate text-[13px] font-semibold">
				{seeded ? displayTeamName(fixture.away_team) : 'TBD'}
			</span>
		</div>
		<div class="flex items-center justify-center gap-1">
			{#if !seeded || isThirdPlace}
				<span class="text-xs text-base-content/30">—</span>
			{:else}
				<BracketChip team={fixture.home_team} picked={homePicked} />
				<BracketChip team={fixture.away_team} picked={awayPicked} />
			{/if}
		</div>
		<div class="text-right">
			<PointsCellKo {stagePoints} {hits} applicable={seeded && !isThirdPlace} />
		</div>
	</div>

	<!-- Mobile stacked card -->
	<div class="flex flex-col gap-1 px-3 py-1.5 sm:hidden">
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {homeLoses ? 'opacity-60' : ''}">
				{#if seeded && hasFlag(fixture.home_team)}
					<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.home_team)}
					>{seeded ? teamCode(fixture.home_team) : 'TBD'}</span
				>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-success' : ''}">
				{#if score}{score.home_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
				{#if seeded && hasFlag(fixture.away_team)}
					<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.away_team)}
					>{seeded ? teamCode(fixture.away_team) : 'TBD'}</span
				>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-success' : ''}">
				{#if score}{score.away_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div
			class="mt-0.5 flex items-center justify-between gap-2 border-t border-dashed border-base-300/40 pt-1.5"
		>
			<span class="flex items-center gap-1 text-[12px] text-base-content/55">
				{#if isLive}
					<span class="font-bold text-success">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
					<span>·</span>
				{/if}
				{#if !seeded || isThirdPlace}
					<span class="text-base-content/30">—</span>
				{:else}
					<BracketChip team={fixture.home_team} picked={homePicked} />
					<BracketChip team={fixture.away_team} picked={awayPicked} />
				{/if}
			</span>
			<PointsCellKo {stagePoints} {hits} applicable={seeded && !isThirdPlace} />
		</div>
	</div>
</a>

<script lang="ts">
	import type { Fixture } from '$types';
	import { displayTeamName } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { koLoserSide } from '$lib/utils/matchDetailV4';
	import { track } from '$lib/analytics';
	import BracketChip from './BracketChip.svelte';
	import PointsCellKo from './PointsCellKo.svelte';

	export let fixture: Fixture;
	export let roundPicks: Set<string>;
	export let stagePoints: number;
	export let striped = false;
	/** When false the Points cell renders the dash regardless of hits —
	 *  used while knockout scoring is held back (v2.183.3). */
	export let pointsVisible = true;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: score = fixture.score;
	// Loser-of-record at a KO fixture is decided by pens → ET → regulation
	// (matches Score.outcome on the backend). Using regulation alone would
	// mark BOTH teams un-greyed for a draw-then-pens result like Germany
	// 1-1 Paraguay (Paraguay won 4-3 on pens), hiding the elimination.
	$: koLoser = koLoserSide(score);
	$: homeLoses = koLoser === 'home';
	$: awayLoses = koLoser === 'away';
	$: isThirdPlace = fixture.stage === 'third_place';
	// PER-SIDE seeded check (v2.184.x — Q9 fix). The downstream lineup
	// resolver can now partially resolve a fixture: e.g., the R16 home is
	// known (a finished R32's winner) while the away is still TBD (its
	// feeding R32 hasn't kicked off). A binary seeded flag would render
	// BOTH sides as TBD in that case, hiding the resolved side from the
	// user. Slot strings always start with "slot:" — that's a stronger
	// test than the prior /\d/ heuristic, which could misclassify any
	// future team name with a digit.
	$: homeSeeded = !!fixture.home_team && !fixture.home_team.startsWith('slot:');
	$: awaySeeded = !!fixture.away_team && !fixture.away_team.startsWith('slot:');
	$: homePicked = homeSeeded && !isThirdPlace && roundPicks.has(fixture.home_team);
	$: awayPicked = awaySeeded && !isThirdPlace && roundPicks.has(fixture.away_team);
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
		{striped && !isLive ? 'bg-base-300/15 lg:bg-transparent' : ''}
		{isLive ? 'border-l-4 border-l-success bg-success/5' : ''}"
	aria-label={`Open match detail for ${displayTeamName(fixture.home_team)} vs ${displayTeamName(fixture.away_team)}`}
>
	<!-- Desktop grid -->
	<div
		class="hidden items-center gap-2 px-3 py-1.5 sm:grid sm:grid-cols-[minmax(90px,1fr)_70px_minmax(90px,1fr)_56px_92px]"
	>
		<div class="flex items-center justify-end gap-2 {homeLoses ? 'opacity-60' : ''}">
			<span class="truncate text-[13px] font-semibold">
				{homeSeeded ? displayTeamName(fixture.home_team) : 'TBD'}
			</span>
			{#if homeSeeded && hasFlag(fixture.home_team)}
				<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{:else if !homeSeeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[9px] font-extrabold text-base-content/55"
					>?</span
				>
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
					{#if score.home_penalties != null && score.away_penalties != null}
						<span
							class="px-1 text-[11px] font-semibold {isLive
								? 'text-white/70'
								: 'text-base-content/55'}"
							title="Penalty shootout">({score.home_penalties}–{score.away_penalties})</span
						>
					{:else}
						<span class="px-0.5 {isLive ? 'text-white/70' : 'text-base-content/40'}">–</span>
					{/if}
					<b class={awayLoses ? 'opacity-60' : ''}>{score.away_score}</b>
				</span>
			{:else}
				<span class="text-base-content/30">———</span>
			{/if}
			<div class="text-[10px] text-base-content/55">
				{#if isLive}
					<span class="inline-block rounded bg-success px-1.5 py-0.5 font-bold text-white">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}
				{/if}
			</div>
		</div>
		<div class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
			{#if awaySeeded && hasFlag(fixture.away_team)}
				<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" style="aspect-ratio: 4 / 3" />
			{:else if !awaySeeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[9px] font-extrabold text-base-content/55"
					>?</span
				>
			{/if}
			<span class="truncate text-[13px] font-semibold">
				{awaySeeded ? displayTeamName(fixture.away_team) : 'TBD'}
			</span>
		</div>
		<div class="flex items-center justify-center gap-1">
			{#if isThirdPlace || (!homeSeeded && !awaySeeded)}
				<span class="text-xs text-base-content/30">—</span>
			{:else}
				{#if homeSeeded}
					<BracketChip team={fixture.home_team} picked={homePicked} />
				{:else}
					<span class="text-xs text-base-content/30">·</span>
				{/if}
				{#if awaySeeded}
					<BracketChip team={fixture.away_team} picked={awayPicked} />
				{:else}
					<span class="text-xs text-base-content/30">·</span>
				{/if}
			{/if}
		</div>
		<div class="text-right">
			<PointsCellKo
				{stagePoints}
				{hits}
				applicable={pointsVisible && !isThirdPlace && (homeSeeded || awaySeeded)}
			/>
		</div>
	</div>

	<!-- Mobile stacked card -->
	<div class="flex flex-col gap-1 px-3 py-1.5 sm:hidden">
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {homeLoses ? 'opacity-60' : ''}">
				{#if homeSeeded && hasFlag(fixture.home_team)}
					<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.home_team)}
					>{homeSeeded ? teamCode(fixture.home_team) : 'TBD'}</span
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
		{#if score?.home_penalties != null && score?.away_penalties != null}
			<div class="flex justify-end">
				<span
					class="font-display text-[10px] font-semibold text-base-content/55"
					title="Penalty shootout">({score.home_penalties}–{score.away_penalties})</span
				>
			</div>
		{/if}
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
				{#if awaySeeded && hasFlag(fixture.away_team)}
					<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" style="aspect-ratio: 4 / 3" />
				{/if}
				<span class="text-[13px] font-semibold" title={displayTeamName(fixture.away_team)}
					>{awaySeeded ? teamCode(fixture.away_team) : 'TBD'}</span
				>
			</span>
			<span
				class="font-display text-[15px] {isLive
					? 'inline-block min-w-[1.5rem] rounded-md bg-success px-1.5 py-0.5 text-center text-white'
					: ''}"
			>
				{#if score}{score.away_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div
			class="mt-0.5 flex items-center justify-between gap-2 border-t border-dashed border-base-300/40 pt-1.5"
		>
			<span class="flex items-center gap-1 text-[12px] text-base-content/55">
				{#if isLive}
					<span class="inline-block rounded bg-success px-1.5 py-0.5 font-bold text-white">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
					<span>·</span>
				{/if}
				{#if isThirdPlace || (!homeSeeded && !awaySeeded)}
					<span class="text-base-content/30">—</span>
				{:else}
					{#if homeSeeded}
						<BracketChip team={fixture.home_team} picked={homePicked} />
					{:else}
						<span class="text-base-content/30">·</span>
					{/if}
					{#if awaySeeded}
						<BracketChip team={fixture.away_team} picked={awayPicked} />
					{:else}
						<span class="text-base-content/30">·</span>
					{/if}
				{/if}
			</span>
			<PointsCellKo
				{stagePoints}
				{hits}
				applicable={pointsVisible && !isThirdPlace && (homeSeeded || awaySeeded)}
			/>
		</div>
	</div>
</a>

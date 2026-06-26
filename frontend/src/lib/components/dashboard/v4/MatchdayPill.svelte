<script lang="ts">
	/** ESPN-style compact fixture pill (v2.181.0). Vertical-stacked team
	 *  rows with state label at top. Powers the MatchdayStrip on the
	 *  dashboard — 6 pills across on desktop, horizontal scroll on mobile.
	 *
	 *  Three visual states:
	 *    - upcoming → kickoff label ("Sat · 02:00"), no scores yet
	 *    - live     → green LIVE/minute chip + red pulsing dot, scores live
	 *    - finished → "FT" label, scores frozen, loser dimmed
	 *
	 *  Click target navigates to /results/{fixture_id}.
	 */
	import type { Fixture } from '$types';
	import { teamCode } from '$lib/utils/teamCodes';
	import { isRealTeam } from '$lib/utils/leaderboardV4';
	import TeamFlag from './TeamFlag.svelte';

	export let fixture: Fixture;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: isFinished = fixture.status === 'finished';
	$: hasScore = fixture.score != null;
	$: homeCode = isRealTeam(fixture.home_team) ? teamCode(fixture.home_team) : 'TBD';
	$: awayCode = isRealTeam(fixture.away_team) ? teamCode(fixture.away_team) : 'TBD';
	$: homeScore = fixture.score?.home_score ?? null;
	$: awayScore = fixture.score?.away_score ?? null;

	// Winner / loser highlight only when match is FINISHED — live scores
	// can flip during the minute so we don't dim either side mid-match.
	$: homeWon = isFinished && homeScore != null && awayScore != null && homeScore > awayScore;
	$: awayWon = isFinished && homeScore != null && awayScore != null && awayScore > homeScore;

	function formatKickoff(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		const day = d.toLocaleDateString(undefined, { weekday: 'short' });
		const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
		return `${day} · ${time}`;
	}

	$: kickoffLabel = formatKickoff(fixture.kickoff);
</script>

<a
	href={`/results/${fixture.id}`}
	class="group block rounded-box border bg-base-200 p-2.5 transition-colors hover:border-primary/50
		   flex-none w-[148px] snap-start
		   md:flex-auto md:w-auto md:snap-align-none
		   {isLive ? 'border-l-4 border-l-success border-success/40 bg-success/5' : 'border-base-300/70'}"
>
	<!-- State label row -->
	<div class="mb-2 flex items-center text-[9.5px] font-extrabold uppercase tracking-[0.12em]">
		{#if isLive}
			<span
				class="inline-flex items-center gap-1 rounded-badge bg-success px-1.5 py-0.5 text-white"
			>
				<span class="h-1.5 w-1.5 rounded-full bg-error animate-pulse" aria-hidden="true"></span>
				{fixture.minute != null ? `${fixture.minute}'` : 'LIVE'}
			</span>
		{:else if isFinished}
			<span class="text-base-content/40">FT</span>
		{:else}
			<span class="text-base-content/55">{kickoffLabel}</span>
		{/if}
	</div>

	<!-- Home team row -->
	<div
		class="flex items-center gap-1.5 {homeWon
			? 'text-base-content'
			: isFinished
				? 'text-base-content/45'
				: 'text-base-content'}"
	>
		<TeamFlag team={fixture.home_team} />
		<span class="min-w-0 flex-1 truncate text-[12.5px] font-bold tabular-nums" title={fixture.home_team}>
			{homeCode}
		</span>
		{#if hasScore}
			<span class="font-display text-[14px] font-extrabold tabular-nums">{homeScore}</span>
		{/if}
	</div>

	<!-- Away team row -->
	<div
		class="mt-1 flex items-center gap-1.5 {awayWon
			? 'text-base-content'
			: isFinished
				? 'text-base-content/45'
				: 'text-base-content'}"
	>
		<TeamFlag team={fixture.away_team} />
		<span class="min-w-0 flex-1 truncate text-[12.5px] font-bold tabular-nums" title={fixture.away_team}>
			{awayCode}
		</span>
		{#if hasScore}
			<span class="font-display text-[14px] font-extrabold tabular-nums">{awayScore}</span>
		{/if}
	</div>
</a>

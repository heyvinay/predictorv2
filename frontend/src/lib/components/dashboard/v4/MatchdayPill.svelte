<script lang="ts">
	/** ESPN-style compact fixture pill (v2.181.0). Vertical-stacked team
	 *  rows with state label at top. Powers the MatchdayStrip on the
	 *  dashboard — flex-wrapped row on desktop, horizontal scroll on mobile.
	 *
	 *  Three visual states:
	 *    - upcoming → kickoff label ("Sat · 02:00"), no scores yet
	 *    - live     → green LIVE/minute chip + red pulsing dot, scores live
	 *    - finished → "FT" label, scores frozen, loser dimmed
	 *
	 *  `variant` (v2.191.4): 'today' is full-emphasis (the default); 'context'
	 *  dims the whole pill — used for the flanking most-recent-finished /
	 *  next-day pills so today's fixtures read as primary.
	 *
	 *  Click target navigates to /results/{fixture_id}.
	 */
	import type { Fixture } from '$types';
	import { teamCode } from '$lib/utils/teamCodes';
	import { isRealTeam } from '$lib/utils/leaderboardV4';
	import { koFinalScore, koLoserSide } from '$lib/utils/matchDetailV4';
	import TeamFlag from './TeamFlag.svelte';

	export let fixture: Fixture;
	export let variant: 'today' | 'context' = 'today';

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: isFinished = fixture.status === 'finished';
	$: homeCode = isRealTeam(fixture.home_team) ? teamCode(fixture.home_team) : 'TBD';
	$: awayCode = isRealTeam(fixture.away_team) ? teamCode(fixture.away_team) : 'TBD';
	// AET-inclusive score (e.g. 3–2 for a match won in extra time), matching
	// the dashboard "Latest results" table and match detail pages.
	$: finalScore = koFinalScore(fixture.score);
	$: hasScore = finalScore != null;

	// Winner / loser highlight only when match is FINISHED — live scores
	// can flip during the minute so we don't dim either side mid-match.
	// Pens → ET → regulation priority via koLoserSide (mirrors Score.outcome).
	$: koLoser = isFinished ? koLoserSide(fixture.score) : null;
	$: homeWon = isFinished && koLoser === 'away';
	$: awayWon = isFinished && koLoser === 'home';

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
	class="group block rounded-box border bg-base-200 px-2 py-1.5 transition-colors hover:border-primary/50
		   flex-none w-[128px] snap-start
		   md:flex-none md:w-[128px] md:snap-align-none
		   {variant === 'context' ? 'opacity-60' : ''}
		   {isLive ? 'border-l-4 border-l-success border-success/40 bg-success/5' : 'border-base-300/70'}"
>
	<!-- State label row -->
	<div class="mb-1 flex items-center text-[9.5px] font-extrabold uppercase tracking-[0.12em]">
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
			<span class="font-display text-[14px] font-extrabold tabular-nums">{finalScore?.home}</span>
		{/if}
	</div>

	<!-- Away team row -->
	<div
		class="mt-0.5 flex items-center gap-1.5 {awayWon
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
			<span class="font-display text-[14px] font-extrabold tabular-nums">{finalScore?.away}</span>
		{/if}
	</div>
</a>

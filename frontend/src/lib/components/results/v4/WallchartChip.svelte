<!--
	WallchartChip — clickable fixture chip for the Results page bracket wallchart.

	Clicking opens the match detail page. Shows scores when finished; penalty
	shootout result as small "(h–a pen)" text between the two rows.

	★ Per-side seeded check (v2.184.x): home/away resolved independently.
	★ koLoserSide priority: pens → ET → regulation (v2.185.1).
-->
<script lang="ts">
	import type { Fixture } from '$types';
	import { koLoserSide } from '$lib/utils/matchDetailV4';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let fixture: Fixture;
	export let picks: Set<string>;
	export let isFinal: boolean = false;

	$: f = fixture;
	$: loser = koLoserSide(f.score);
	$: homeSeeded = !!f.home_team && !f.home_team.startsWith('slot:');
	$: awaySeeded = !!f.away_team && !f.away_team.startsWith('slot:');
	$: homeHit = homeSeeded && picks.has(f.home_team ?? '');
	$: awayHit = awaySeeded && picks.has(f.away_team ?? '');
	$: hasPens = f.score?.home_penalties != null && f.score?.away_penalties != null;
</script>

<a
	href="/results/{f.id}"
	class="wc-chip block bg-base-200 border cursor-pointer
		{isFinal ? 'border-primary/80 wc-chip--final' : 'border-base-content/15'}
		hover:border-primary/50 transition-colors"
>
	{#if isFinal}
		<div class="final-strip">Final</div>
	{/if}

	<!-- Home row -->
	<div
		class="team-row"
		class:is-winner={loser === 'away'}
		class:is-loser={loser === 'home'}
		class:tbd={!homeSeeded}
	>
		<span class="bullet" class:hit={homeHit}>{homeHit ? '✓' : ''}</span>
		{#if homeSeeded && hasFlag(f.home_team ?? '')}
			<img src={getFlagUrl(f.home_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
		{:else}<span class="flag flag-ph"></span>{/if}
		<span class="tname">{homeSeeded ? displayTeamName(f.home_team).toUpperCase() : 'TBD'}</span>
		{#if f.score != null}<span class="chip-score">{f.score.home_score}</span>{/if}
	</div>

	<!-- Divider — pen result shown here if applicable -->
	{#if hasPens}
		<div class="chip-pen-row border-t border-base-content/15">
			({f.score?.home_penalties}–{f.score?.away_penalties} pen)
		</div>
	{:else}
		<div class="border-t border-base-content/15" aria-hidden="true"></div>
	{/if}

	<!-- Away row -->
	<div
		class="team-row"
		class:is-winner={loser === 'home'}
		class:is-loser={loser === 'away'}
		class:tbd={!awaySeeded}
	>
		<span class="bullet" class:hit={awayHit}>{awayHit ? '✓' : ''}</span>
		{#if awaySeeded && hasFlag(f.away_team ?? '')}
			<img src={getFlagUrl(f.away_team ?? '', 'sm')} alt="" class="flag" loading="lazy" style="aspect-ratio:4/3" />
		{:else}<span class="flag flag-ph"></span>{/if}
		<span class="tname">{awaySeeded ? displayTeamName(f.away_team).toUpperCase() : 'TBD'}</span>
		{#if f.score != null}<span class="chip-score">{f.score.away_score}</span>{/if}
	</div>
</a>

<style>
	.wc-chip {
		position: relative;
		overflow: hidden;
		border-radius: 6px;
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
		text-decoration: none;
		color: inherit;
	}

	.wc-chip--final {
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.25);
	}

	.final-strip {
		text-align: center;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 10px;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		@apply bg-primary text-primary-content;
		padding: 2px 0;
	}

	/* ── Team row ──────────────────────────────────────────────────────────── */
	.team-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 0.7rem;
		line-height: 1;
		transition: background 120ms ease, opacity 120ms ease;
	}

	.team-row.is-winner {
		font-weight: 700;
		background: rgb(34 197 94 / 0.28);
	}

	.team-row.is-loser {
		opacity: 0.45;
	}

	.team-row.tbd {
		opacity: 0.55;
	}

	/* ── Bullet ─────────────────────────────────────────────────────────────── */
	.bullet {
		width: 0.6rem;
		flex-shrink: 0;
		text-align: center;
		font-size: 0.7rem;
		font-weight: 900;
		line-height: 1;
		@apply text-success;
	}

	/* ── Flag ──────────────────────────────────────────────────────────────── */
	.flag {
		width: 14px;
		height: 9px;
		flex-shrink: 0;
		border-radius: 1px;
		box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 15%, transparent);
		object-fit: cover;
	}

	.flag-ph {
		display: inline-block;
		width: 14px;
		height: 9px;
		background: color-mix(in srgb, currentColor 12%, transparent);
		border-radius: 1px;
	}

	/* ── Team name ─────────────────────────────────────────────────────────── */
	.tname {
		font-weight: 600;
		letter-spacing: 0.04em;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* ── Score (right-aligned) ──────────────────────────────────────────────── */
	.chip-score {
		flex-shrink: 0;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
		opacity: 0.9;
		padding-left: 0.3rem;
	}

	/* ── Penalty row (between the two team rows) ────────────────────────────── */
	.chip-pen-row {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
		font-size: 0.58rem;
		font-style: italic;
		letter-spacing: 0.03em;
		opacity: 0.55;
		padding: 1px 0.5rem;
	}

	/* ── Final chip: bigger rows ────────────────────────────────────────────── */
	.wc-chip--final .team-row {
		font-size: 0.95rem;
		padding: 0.5rem 0.75rem;
	}

	.wc-chip--final .flag {
		width: 20px;
		height: 13px;
	}
</style>

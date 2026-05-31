<script lang="ts">
	/**
	 * Per-match breakdown card for /results.
	 *
	 * Ports the visual structure of main's PnResultsCard (commit c2af978)
	 * onto DaisyUI tokens — three pills (Outcome / Exact / Rarity) plus a
	 * Banked / If-FT-now / Up-to total. Single component handles both
	 * desktop and mobile via responsive Tailwind classes; mobile uses
	 * smaller flag/score sizes and a 2-column pill row.
	 *
	 * Data shape comes from matchBreakdown.ts (`computeBreakdown` + `MatchBreakdown`).
	 */
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { stageLabel, stageShort, type MatchBreakdown } from '$lib/utils/matchBreakdown';
	import type { Fixture, MatchPrediction } from '$types';
	import type { ScoringConfig } from '$api/competition';

	export let fixture: Fixture;
	export let prediction: MatchPrediction | undefined;
	export let breakdown: MatchBreakdown;
	export let config: ScoringConfig;
	/** Right-aligned metadata in the header strip (e.g. "18:00" or "12 Jun"). */
	export let metaRight: string = '';

	$: stateLabel = (() => {
		const s = breakdown.state;
		if (s === 'finished') return 'FT';
		if (s === 'live') return fixture.minute != null ? `${fixture.minute}'` : 'LIVE';
		if (s === 'locked') return formatLockIn(fixture.time_until_lock);
		return 'OPEN';
	})();

	function formatLockIn(secs: number | null): string {
		if (secs == null || secs <= 0) return 'LOCK';
		const m = Math.floor(secs / 60);
		if (m >= 60) {
			const h = Math.floor(m / 60);
			return `LOCK · ${h}h`;
		}
		const s = Math.floor(secs % 60);
		return `LOCK · ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	function fmtTime(iso: string): string {
		return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	}

	function pillIcon(state: string): string {
		if (state.startsWith('hit-rarity')) return '★';
		if (state === 'miss') return '✗';
		if (state.startsWith('potential')) return '?';
		if (state === 'none') return '–';
		return '✓';
	}
	function pillPts(pts: number): string {
		if (pts === 0) return '0';
		return pts > 0 ? `+${pts}` : `${pts}`;
	}

	/**
	 * Map a pill state to DaisyUI classes. State-driven palette:
	 *   hit-outcome → warning (amber); hit-exact → success (green);
	 *   hit-rarity → primary gold-ish accent (uses badge-warning here so
	 *   it pops against the green/amber; solo rarity gets an extra ring);
	 *   miss → error; none → ghost; potential → bordered/dashed.
	 */
	function pillClasses(state: string): string {
		if (state === 'hit-exact') return 'bg-success/20 text-success border border-success/40';
		if (state === 'hit-outcome') return 'bg-warning/20 text-warning-text border border-warning/40';
		if (state.startsWith('hit-rarity solo'))
			return 'bg-accent/25 text-accent border-2 border-accent/70 ring-1 ring-accent/30';
		if (state.startsWith('hit-rarity'))
			return 'bg-accent/15 text-accent border border-accent/40';
		if (state === 'miss') return 'bg-error/15 text-error border border-error/40';
		if (state.startsWith('potential'))
			return 'bg-base-300/40 text-base-content/60 border border-dashed border-base-content/30';
		return 'bg-base-300/40 text-base-content/40 border border-base-300/60';
	}

	/** Top-edge "tier" stripe colour. */
	function tierClass(tier: string): string {
		if (tier === 'tier-exact') return 'border-t-4 border-t-success';
		if (tier === 'tier-outcome') return 'border-t-4 border-t-warning';
		if (tier === 'tier-miss') return 'border-t-4 border-t-error/70';
		if (tier === 'tier-live') return 'border-t-4 border-t-info animate-pulse';
		if (tier === 'tier-locked') return 'border-t-4 border-t-base-content/40';
		return 'border-t-4 border-t-base-300';
	}

	/** State-pill in the card header (FT / LIVE / LOCK / OPEN). */
	function statePillClass(state: string): string {
		if (state === 'finished') return 'badge badge-sm badge-neutral font-mono';
		if (state === 'live') return 'badge badge-sm badge-info font-mono animate-pulse';
		if (state === 'locked') return 'badge badge-sm badge-warning font-mono';
		return 'badge badge-sm badge-ghost font-mono';
	}

	/** Your-pick chip background by result. */
	function ypickBg(cls: string): string {
		if (cls === 'exact') return 'bg-success/15 text-success border-success/40';
		if (cls === 'outcome') return 'bg-warning/15 text-warning-text border-warning/40';
		if (cls === 'miss') return 'bg-error/10 text-error border-error/30';
		if (cls === 'empty') return 'bg-base-300/30 text-base-content/40 border-base-300';
		return 'bg-base-300/30 text-base-content/60 border-base-300';
	}

	$: homeWon = fixture.score && fixture.score.home_score > fixture.score.away_score;
	$: awayWon = fixture.score && fixture.score.away_score > fixture.score.home_score;
</script>

<div
	class="stadium-card no-glow overflow-hidden {tierClass(breakdown.tier)}"
	data-state={breakdown.state}
>
	<!-- Header strip: group/stage · meta · state pill -->
	<div class="flex items-center justify-between gap-2 px-3 py-2 bg-base-300/30 text-xs">
		<span class="font-mono uppercase tracking-wider text-base-content/60 truncate">
			{#if fixture.group}
				Group <em class="not-italic font-bold text-base-content/80">{fixture.group}</em>
			{:else}
				<em class="not-italic font-bold text-base-content/80">{stageShort(fixture.stage)}</em>
				<span class="hidden sm:inline opacity-60">{stageLabel(fixture.stage)}</span>
			{/if}
		</span>
		{#if metaRight}
			<span class="font-mono text-[10px] text-base-content/40 hidden xs:inline">{metaRight}</span>
		{/if}
		<span class={statePillClass(breakdown.state)}>{stateLabel}</span>
	</div>

	<!-- Scoreline: home | centre | away -->
	<div class="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-3 px-3 py-3">
		<!-- Home team -->
		<div
			class="flex items-center gap-1.5 sm:gap-2 min-w-0 {awayWon ? 'opacity-60' : ''}"
		>
			{#if hasFlag(fixture.home_team)}
				<img
					src={getFlagUrl(fixture.home_team, 'sm')}
					alt=""
					class="w-7 sm:w-9 h-auto rounded-sm shadow-sm shrink-0"
				/>
			{/if}
			<span class="font-semibold text-xs sm:text-sm truncate {homeWon ? 'text-base-content' : ''}">
				<span class="hidden sm:inline">{displayTeamName(fixture.home_team)}</span>
				<span class="sm:hidden">{teamCode(fixture.home_team)}</span>
			</span>
		</div>

		<!-- Centre: scorebox + your pick -->
		<div class="flex flex-col items-center gap-1 min-w-[5rem]">
			{#if breakdown.state === 'finished' && fixture.score}
				<div class="flex flex-col items-center">
					<span class="font-display text-xl sm:text-2xl tracking-wider text-base-content"
						>{fixture.score.home_score}–{fixture.score.away_score}</span
					>
					<span class="text-[9px] uppercase tracking-widest text-base-content/40 font-mono">Full Time</span>
				</div>
			{:else if breakdown.state === 'live' && fixture.score}
				<div class="flex flex-col items-center">
					<span class="font-display text-xl sm:text-2xl tracking-wider text-info"
						>{fixture.score.home_score}–{fixture.score.away_score}</span
					>
					<span class="text-[9px] uppercase tracking-widest text-info font-mono">
						● {fixture.minute != null ? fixture.minute + "'" : 'LIVE'}
					</span>
				</div>
			{:else}
				<div class="flex flex-col items-center">
					<span class="font-display text-lg sm:text-xl tracking-wider text-base-content/50">VS</span>
					<span class="text-[9px] uppercase tracking-widest text-base-content/40 font-mono"
						>{fmtTime(fixture.kickoff)}</span
					>
				</div>
			{/if}

			{#if prediction}
				<div
					class="text-[10px] font-mono px-2 py-0.5 rounded border {ypickBg(breakdown.ypickClass)}"
				>
					<span class="opacity-70">{breakdown.ypickLabel}</span>
					<b class="font-bold">{prediction.home_score}–{prediction.away_score}</b>
				</div>
			{/if}
		</div>

		<!-- Away team -->
		<div
			class="flex items-center gap-1.5 sm:gap-2 min-w-0 justify-end text-right {homeWon ? 'opacity-60' : ''}"
		>
			<span class="font-semibold text-xs sm:text-sm truncate {awayWon ? 'text-base-content' : ''}">
				<span class="hidden sm:inline">{displayTeamName(fixture.away_team)}</span>
				<span class="sm:hidden">{teamCode(fixture.away_team)}</span>
			</span>
			{#if hasFlag(fixture.away_team)}
				<img
					src={getFlagUrl(fixture.away_team, 'sm')}
					alt=""
					class="w-7 sm:w-9 h-auto rounded-sm shadow-sm shrink-0"
				/>
			{/if}
		</div>
	</div>

	<!-- Breakdown strip: pills + total -->
	<div
		class="grid grid-cols-[1fr_1fr_1fr_auto] sm:grid-cols-[1fr_1fr_1fr_auto] gap-1.5 sm:gap-2 px-3 py-2.5 border-t border-base-300/40 bg-base-200/30"
		class:!grid-cols-[1fr_1fr_auto]={config.mode === 'fixed'}
	>
		<!-- Outcome pill -->
		<div
			class="flex flex-col items-center justify-center rounded-md px-1.5 py-1 {pillClasses(
				breakdown.outcomePill.state
			)}"
		>
			<span class="font-display text-sm sm:text-base leading-none tracking-wide">
				<span class="opacity-80">{pillIcon(breakdown.outcomePill.state)}</span>
				{pillPts(breakdown.outcomePill.pts)}
			</span>
			<span class="text-[9px] uppercase tracking-wider opacity-70 mt-0.5"
				>{breakdown.outcomePill.lab}</span
			>
		</div>

		<!-- Exact-score pill -->
		<div
			class="flex flex-col items-center justify-center rounded-md px-1.5 py-1 {pillClasses(
				breakdown.scorePill.state
			)}"
		>
			<span class="font-display text-sm sm:text-base leading-none tracking-wide">
				<span class="opacity-80">{pillIcon(breakdown.scorePill.state)}</span>
				{pillPts(breakdown.scorePill.pts)}
			</span>
			<span class="text-[9px] uppercase tracking-wider opacity-70 mt-0.5"
				>{breakdown.scorePill.lab}</span
			>
		</div>

		<!-- Rarity pill (hidden in fixed mode) -->
		{#if config.mode !== 'fixed'}
			<div
				class="flex flex-col items-center justify-center rounded-md px-1.5 py-1 {pillClasses(
					breakdown.rarityPill.state
				)}"
			>
				<span class="font-display text-sm sm:text-base leading-none tracking-wide">
					<span class="opacity-80">{pillIcon(breakdown.rarityPill.state)}</span>
					{pillPts(breakdown.rarityPill.pts)}
				</span>
				<span class="text-[9px] uppercase tracking-wider opacity-70 mt-0.5"
					>{breakdown.rarityPill.lab}</span
				>
			</div>
		{/if}

		<!-- Total -->
		<div class="flex flex-col items-center justify-center px-2 sm:px-3 min-w-[3.5rem]">
			<span class="font-display text-lg sm:text-xl tracking-wide leading-none"
				>{breakdown.totalDisplay}</span
			>
			<span class="text-[9px] uppercase tracking-wider text-base-content/50 mt-0.5"
				>{breakdown.totalLabel}</span
			>
		</div>
	</div>
</div>

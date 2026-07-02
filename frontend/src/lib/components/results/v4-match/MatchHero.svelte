<script lang="ts">
	/** Hero card. mode='played': badge + big score + winner emphasis.
	 *  mode='upcoming': LOCKED badge + big VS + kickoff countdown. */
	import type { Fixture } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { koFinalScore, koWinnerSide } from '$lib/utils/matchDetailV4';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let mode: 'played' | 'upcoming';
	export let upset = false;

	$: score = fixture.score;
	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	// KO-aware winner resolution: pens → ET → regulation. Without this,
	// a 1-1 draw resolved on penalties leaves homeWin === awayWin === false
	// and BOTH team-name + score halves render at opacity-50 (looks like
	// both teams lost). Mirrors `Score.outcome` on the backend exactly.
	$: koWinner = koWinnerSide(score);
	$: homeWin = koWinner === 'home';
	$: awayWin = koWinner === 'away';
	// Headline score is AET-inclusive — a match won in extra time shows the
	// AET score (e.g. 3–2) as the primary number, not the 90-min regulation
	// score. The line below duplicates it labelled "AET" for wentToEt cases.
	$: finalScore = koFinalScore(score);
	// Pens-decided / ET-decided flags drive the secondary scoreline below
	// the regulation score and the badge upgrade ("AFTER PENALTIES" etc).
	$: wentToPens =
		!!score && score.home_penalties != null && score.away_penalties != null;
	$: wentToEt =
		!!score && score.home_score_et != null && score.away_score_et != null;
	$: badgeLabel = isLive
		? null
		: wentToPens
			? 'AFTER PENALTIES'
			: wentToEt
				? 'AFTER EXTRA TIME'
				: 'FULL TIME';
	$: dateLabel = new Date(fixture.kickoff).toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short'
	});
	$: koClock = new Date(fixture.kickoff).toLocaleTimeString('en-GB', {
		hour: '2-digit',
		minute: '2-digit'
	});
	$: kicksIn = (() => {
		const ms = new Date(fixture.kickoff).getTime() - Date.now();
		if (ms <= 0) return 'soon';
		const h = Math.floor(ms / 3_600_000);
		const m = Math.floor((ms % 3_600_000) / 60_000);
		if (h >= 48) return `in ${Math.floor(h / 24)}d ${h % 24}h`;
		return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
	})();
</script>

<div
	class="relative overflow-hidden rounded-box border border-base-300/60 bg-gradient-to-b from-primary/5 to-base-200 p-3"
>
	{#if mode === 'played' && upset}
		<div
			class="mb-2 inline-block rounded-full bg-warning/20 px-2 py-0.5 text-[9px] font-extrabold tracking-[0.1em] text-warning-text"
		>
			★ UPSET OF THE ROUND
		</div>
	{:else if mode === 'upcoming'}
		<div
			class="mb-2 inline-flex items-center gap-1 rounded-full bg-base-300/40 px-2 py-0.5 text-[9px] font-extrabold tracking-[0.1em] text-base-content/70"
		>
			<span class="text-[10px]">🔒</span> LOCKED · KO {koClock}
		</div>
	{/if}

	<div class="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
		<div class="flex flex-col items-center gap-1 {!isLive && awayWin ? 'opacity-55' : ''}">
			{#if hasFlag(fixture.home_team)}
				<img
					src={getFlagUrl(fixture.home_team, 'sm')}
					alt=""
					class="h-[26px] w-[40px] rounded-md object-cover shadow-card max-sm:h-[22px] max-sm:w-[32px]" style="aspect-ratio: 4 / 3" />
			{/if}
			<div class="text-center font-display text-[12px] font-extrabold leading-tight max-sm:text-[13px]">
				<TeamName name={fixture.home_team} />
			</div>
		</div>

		<div class="flex flex-col items-center gap-0.5 px-2">
			{#if mode === 'played'}
				{#if isLive}
					<span
						class="inline-block rounded bg-success px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-white"
					>
						LIVE {fixture.minute ? `${fixture.minute}'` : ''}
					</span>
				{:else}
					<div class="text-[8.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
						{badgeLabel}
					</div>
				{/if}
				<div
					class="font-display text-[22px] leading-none max-sm:text-[18px] {isLive
						? 'inline-block rounded-md bg-success px-2 py-0.5 text-white'
						: ''}"
				>
					<b class={isLive ? '' : homeWin ? '' : 'opacity-50'}>{finalScore?.home ?? '–'}</b>
					<span class="px-1 {isLive ? 'text-white/70' : 'text-base-content/40'}">–</span>
					<b class={isLive ? '' : awayWin ? '' : 'opacity-50'}>{finalScore?.away ?? '–'}</b>
				</div>
				{#if !isLive && wentToEt}
					<!-- Redundant confirmation line labelling the headline as AET —
					     the headline above already shows the AET-inclusive score
					     (via koFinalScore), so this repeats the same numbers with
					     an explicit "AET" tag for clarity. Only renders when FD (or
					     admin) gave us an ET split. -->
					<div class="font-mono text-[11px] tabular-nums text-base-content/55 max-sm:text-[10px]">
						<span class="text-[8.5px] font-bold uppercase tracking-[0.08em] text-base-content/45">AET</span>
						<b class={homeWin ? '' : 'opacity-50'}>{score?.home_score_et}</b>
						<span class="px-0.5 text-base-content/35">–</span>
						<b class={awayWin ? '' : 'opacity-50'}>{score?.away_score_et}</b>
					</div>
				{/if}
				{#if !isLive && wentToPens}
					<!-- Penalty-shootout result. Highlighted slightly more (warning
					     amber) than the AET line because pens are the decisive leg. -->
					<div class="font-mono text-[11px] tabular-nums text-warning-text max-sm:text-[10px]">
						<span class="text-[8.5px] font-bold uppercase tracking-[0.08em] text-base-content/55">Pens</span>
						<b class={homeWin ? '' : 'opacity-50'}>{score?.home_penalties}</b>
						<span class="px-0.5 text-base-content/35">–</span>
						<b class={awayWin ? '' : 'opacity-50'}>{score?.away_penalties}</b>
					</div>
				{/if}
			{:else}
				<div class="font-display text-[18px] leading-none text-base-content/70 max-sm:text-[16px]">VS</div>
				<div class="text-[10px] font-bold text-primary">Kicks off {kicksIn}</div>
			{/if}
			<div class="text-[9.5px] text-base-content/55">
				{fixture.group ? `Group ${fixture.group} · ` : ''}{dateLabel}
			</div>
		</div>

		<div class="flex flex-col items-center gap-1 {!isLive && homeWin ? 'opacity-55' : ''}">
			{#if hasFlag(fixture.away_team)}
				<img
					src={getFlagUrl(fixture.away_team, 'sm')}
					alt=""
					class="h-[26px] w-[40px] rounded-md object-cover shadow-card max-sm:h-[22px] max-sm:w-[32px]" style="aspect-ratio: 4 / 3" />
			{/if}
			<div class="text-center font-display text-[12px] font-extrabold leading-tight max-sm:text-[13px]">
				<TeamName name={fixture.away_team} />
			</div>
		</div>
	</div>
</div>

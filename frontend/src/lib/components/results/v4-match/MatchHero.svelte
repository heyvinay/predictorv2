<script lang="ts">
	/** Hero card. mode='played': badge + big score + winner emphasis.
	 *  mode='upcoming': LOCKED badge + big VS + kickoff countdown. */
	import type { Fixture } from '$types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let mode: 'played' | 'upcoming';
	export let upset = false;

	$: score = fixture.score;
	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: homeWin = !!score && score.home_score > score.away_score;
	$: awayWin = !!score && score.away_score > score.home_score;
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
		<div class="flex flex-col items-center gap-1">
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
				<div
					class="text-[8.5px] font-extrabold uppercase tracking-[0.12em] {isLive
						? 'text-error'
						: 'text-base-content/55'}"
				>
					{isLive ? `LIVE ${fixture.minute ? `${fixture.minute}'` : ''}` : 'FULL TIME'}
				</div>
				<div class="font-display text-[22px] leading-none max-sm:text-[18px]">
					<b class={homeWin ? '' : 'opacity-50'}>{score?.home_score ?? '–'}</b>
					<span class="px-1 text-base-content/40">–</span>
					<b class={awayWin ? '' : 'opacity-50'}>{score?.away_score ?? '–'}</b>
				</div>
			{:else}
				<div class="font-display text-[18px] leading-none text-base-content/70 max-sm:text-[16px]">VS</div>
				<div class="text-[10px] font-bold text-primary">Kicks off {kicksIn}</div>
			{/if}
			<div class="text-[9.5px] text-base-content/55">
				{fixture.group ? `Group ${fixture.group} · ` : ''}{dateLabel}
			</div>
		</div>

		<div class="flex flex-col items-center gap-1">
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

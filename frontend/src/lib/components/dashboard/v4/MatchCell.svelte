<script lang="ts">
	/** Centre table cell: home name + flag · score / "vs" · flag + away
	 *  name. Score shows whenever one exists (live or finished); a "p"
	 *  marker flags penalty shootouts. */
	import type { Fixture } from '$types';
	import { scorelineOf } from '$lib/utils/dashboardV4';
	import { isRealTeam } from '$lib/utils/leaderboardV4';
	import TeamFlag from './TeamFlag.svelte';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;

	$: score = scorelineOf(fixture);
</script>

<span class="grid min-w-0 grid-cols-[1fr_auto_1fr] items-center gap-1.5">
	<span class="flex min-w-0 items-center justify-end gap-1.5">
		<span class="truncate text-right text-[12px] font-semibold text-base-content"
			>{#if isRealTeam(fixture.home_team)}<TeamName
					name={fixture.home_team}
				/>{:else}{fixture.home_team}{/if}</span
		>
		<TeamFlag team={fixture.home_team} />
	</span>

	{#if score}
		<span class="font-display text-[14px] font-extrabold tabular-nums text-base-content">
			{score.home}<span class="px-px text-base-content/40">–</span>{score.away}{#if score.pens}<span
					class="pl-0.5 align-super text-[9px] font-bold text-base-content/55"
					title="Decided on penalties">p</span
				>{/if}
		</span>
	{:else}
		<span class="px-0.5 text-[10.5px] font-bold uppercase text-base-content/30">vs</span>
	{/if}

	<span class="flex min-w-0 items-center gap-1.5">
		<TeamFlag team={fixture.away_team} />
		<span class="truncate text-[12px] font-semibold text-base-content"
			>{#if isRealTeam(fixture.away_team)}<TeamName
					name={fixture.away_team}
				/>{:else}{fixture.away_team}{/if}</span
		>
	</span>
</span>

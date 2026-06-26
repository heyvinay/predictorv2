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
	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
</script>

<span class="grid min-w-0 grid-cols-[1fr_auto_1fr] items-center gap-1.5">
	<span class="flex min-w-0 items-center justify-end gap-1.5">
		<span class="truncate text-right text-[12px] font-semibold text-base-content"
			>{#if isRealTeam(fixture.home_team)}<TeamName
					name={fixture.home_team}
					forceCode={isLive}
				/>{:else}{fixture.home_team}{/if}</span
		>
		<TeamFlag team={fixture.home_team} />
	</span>

	{#if score}
		<!-- v2.181.0: live score chip is smaller on mobile (px-1 text-[12px])
		     so the 1fr team-name columns get column width back. The bigger
		     chip from v2.180.0 (px-1.5 text-[14px]) ate enough horizontal
		     space to truncate TLAs to "C…" on narrow screens. -->
		<span
			class="font-display font-extrabold tabular-nums {isLive
				? 'inline-block rounded-md bg-success px-1 py-0.5 text-[12px] text-white sm:px-1.5 sm:text-[14px]'
				: 'text-[14px] text-base-content'}"
		>
			{score.home}<span class="px-px {isLive ? 'text-white/70' : 'text-base-content/40'}">–</span>{score.away}{#if score.pens}<span
					class="pl-0.5 align-super text-[9px] font-bold {isLive
						? 'text-white/70'
						: 'text-base-content/55'}"
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
					forceCode={isLive}
				/>{:else}{fixture.away_team}{/if}</span
		>
	</span>
</span>

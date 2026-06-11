<script lang="ts">
	/** 22×16 flag with the dashed "?" placeholder for unseeded slots
	 *  (e.g. "Winner of Match 49"). */
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { isRealTeam } from '$lib/utils/leaderboardV4';

	export let team: string;

	$: real = isRealTeam(team) && hasFlag(team);
</script>

{#if real}
	<img
		src={getFlagUrl(team, 'sm')}
		alt=""
		loading="lazy"
		class="h-4 w-[22px] flex-none rounded-sm object-cover ring-1 ring-black/30"
	/>
{:else}
	<span
		class="grid h-4 w-[22px] flex-none place-items-center rounded-sm border-[1.5px] border-dashed border-base-300 text-[10px] leading-none text-base-content/30"
		aria-hidden="true">?</span
	>
{/if}

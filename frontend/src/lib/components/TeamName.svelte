<script lang="ts">
	/** Responsive team name: full short name on wider screens, FIFA
	 *  three-letter code on phones. Placeholder slot strings render "TBD"
	 *  at both widths. `bp` selects where the swap happens — 'sm' (640px,
	 *  default) or '480' for surfaces that already break at min-[480px].
	 *
	 *  `forceCode` pins TLA at every viewport — used for visually-loaded
	 *  rows (live matches) where the cell is dense with score + LIVE
	 *  badge + flags regardless of screen width, so the most compact name
	 *  form beats picking a breakpoint. */
	import { displayTeamName, isPlaceholderTeam } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';

	export let name: string | null | undefined;
	export let bp: 'sm' | '480' = 'sm';
	export let forceCode = false;

	$: full = displayTeamName(name);
	$: code = !name || isPlaceholderTeam(name) ? 'TBD' : teamCode(name);
</script>

{#if forceCode}
	<span title={full}>{code}</span>
{:else if bp === 'sm'}
	<span class="max-sm:hidden">{full}</span><span class="sm:hidden" title={full}>{code}</span>
{:else}
	<span class="max-[479px]:hidden">{full}</span><span class="min-[480px]:hidden" title={full}
		>{code}</span
	>
{/if}

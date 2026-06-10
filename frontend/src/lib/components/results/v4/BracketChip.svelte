<script lang="ts">
	/** ✓ MEX (green) when the team is in the entry's bracket for this
	 *  round; muted otherwise. Label = first 3 letters of the short name. */
	import { displayTeamName } from '$lib/utils/teamName';

	export let team: string;
	export let picked: boolean;

	$: label = displayTeamName(team).toUpperCase().slice(0, 3);
</script>

<span
	class="inline-flex items-center gap-0.5 rounded-badge px-1.5 py-0.5 text-[10px] font-extrabold tracking-[0.02em] {picked
		? 'bg-success/20 text-success'
		: 'bg-base-300/30 text-base-content/40'}"
>
	{picked ? '✓ ' : ''}{label}
</span>

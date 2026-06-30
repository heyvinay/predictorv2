<script lang="ts">
	/** ✓ MEX (green) when the team is in the entry's bracket for this
	 *  round; muted otherwise. Label = FIFA three-letter code.
	 *
	 *  Important: this chip means "did your pick make THIS round's lineup"
	 *  — a permanent fact once the round starts. It does NOT reflect the
	 *  match result. A team can be ✓ here (made R32) and still lose the
	 *  R32 match — that loss is paid (or denied) in the NEXT row of the
	 *  bracket (R16). Don't surface match outcome on this chip. */
	import { teamCode } from '$lib/utils/teamCodes';

	export let team: string;
	export let picked: boolean;

	$: label = teamCode(team);
</script>

<span
	class="inline-flex items-center gap-0.5 rounded-badge px-1.5 py-0.5 text-[10px] font-extrabold tracking-[0.02em] {picked
		? 'bg-success/20 text-success'
		: 'bg-base-300/30 text-base-content/40'}"
>
	{picked ? '✓ ' : ''}{label}
</span>

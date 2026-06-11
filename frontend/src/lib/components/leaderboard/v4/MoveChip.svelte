<script lang="ts">
	/** Movement chip vs yesterday's snapshot: ▲n / ▼n / — (null or 0). */
	export let move: number | null | undefined = null;

	$: label =
		move == null || move === 0
			? 'no change'
			: move > 0
			? `up ${move} place${move === 1 ? '' : 's'}`
			: `down ${Math.abs(move)} place${move === -1 ? '' : 's'}`;
</script>

{#if move != null && move > 0}
	<span class="text-[10px] font-extrabold tracking-wide text-success" aria-label={label}>▲{move}</span>
{:else if move != null && move < 0}
	<span class="text-[10px] font-extrabold tracking-wide text-error" aria-label={label}>▼{Math.abs(move)}</span>
{:else}
	<span class="text-[10px] font-extrabold text-base-content/30" aria-label={label}>—</span>
{/if}

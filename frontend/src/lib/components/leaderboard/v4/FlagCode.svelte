<script lang="ts">
	/** Flag + 3-letter code chip for a team, with alive/eliminated styling.
	 *  `dot` adds the ✓/✗ status circle (standings champ column). */
	import { getFlagUrl } from '$lib/utils/flags';
	import { teamCode } from '$lib/utils/teamCodes';

	export let team: string;
	export let alive = true;
	export let dot = false;
	/** Flag box size. 'md' = 24×17 (champ column), 'sm' = 16×12 (chips). */
	export let size: 'md' | 'sm' = 'md';

	$: flagUrl = getFlagUrl(team, 'sm');
	$: tla = teamCode(team);
	$: dims = size === 'md' ? 'h-[17px] w-6' : 'h-3 w-4';
</script>

<span
	class="inline-flex items-center gap-1.5"
	title="{team}{dot ? (alive ? ' — still alive' : ' — eliminated') : ''}"
>
	{#if flagUrl}
		<img
			src={flagUrl}
			alt=""
			class="{dims} flex-none rounded-sm object-cover ring-1 ring-black/30 {alive
				? ''
				: 'opacity-45 grayscale'}"
			loading="lazy"
		/>
	{:else}
		<span class="{dims} flex-none rounded-sm bg-base-300"></span>
	{/if}
	<span
		class="font-display text-[11.5px] font-extrabold tracking-[0.06em] {alive
			? 'text-base-content'
			: 'text-base-content/30'}">{tla}</span
	>
	{#if dot}
		<span
			class="grid h-[13px] w-[13px] flex-none place-items-center rounded-full text-[8px] font-extrabold {alive
				? 'bg-success text-success-content'
				: 'bg-error/30 text-error'}"
			aria-label={alive ? 'still alive' : 'eliminated'}>{alive ? '✓' : '✗'}</span
		>
	{/if}
</span>

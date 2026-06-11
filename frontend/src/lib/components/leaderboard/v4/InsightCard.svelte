<script lang="ts">
	/** Shared insight card shell: Bebas title, muted sub, optional footer
	 *  slot, `wide` spans both grid columns. */
	export let title: string;
	export let sub = '';
	export let wide = false;
</script>

<div
	class="rounded-xl border border-base-300/60 bg-base-200 p-4 sm:p-5 {wide
		? 'min-[860px]:col-span-2'
		: ''}"
>
	<h3 class="font-hero text-[21px] tracking-[0.04em]">{title}</h3>
	{#if sub}<p class="mb-3.5 mt-0.5 text-xs text-base-content/55">{sub}</p>{/if}
	<slot />
	{#if $$slots.foot}
		<div class="mt-3 border-t border-base-300/45 pt-2.5 text-[11.5px] leading-relaxed text-base-content/55">
			<slot name="foot" />
		</div>
	{/if}
</div>

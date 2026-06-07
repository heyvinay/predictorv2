<!--
  Banner alert at the top of phase dashboards.

    variant="gold" — informational, non-urgent
    variant="red"  — urgent (next lock soon, KO matches missing picks)

  Ported from upstream's DwAlert.svelte. Token swaps:
    - .pn-alert-v4 .red → bg-error/20 border-error/40 text-error
    - .pn-alert-v4 gold → bg-warning/20 border-warning/40 text-warning-text
      (use text-warning-text per feedback_text_warning_token_trap memory)
-->
<script lang="ts">
	export let variant: 'gold' | 'red' = 'gold';
	export let title: string = '';
	/** Meta line below the title (HTML allowed for inline <b>/<em>). */
	export let meta: string = '';
	export let icon: string = '!';
	export let ctaLabel: string = '';
	export let ctaHref: string | null = null;
	/** When true and ctaHref is set, opens the link in a new tab. */
	export let ctaExternal: boolean = false;
	export let onCta: (() => void) | null = null;

	$: surfaceClass =
		variant === 'red'
			? 'bg-error/20 border-error/40'
			: 'bg-warning/20 border-warning/40';
	$: textClass = variant === 'red' ? 'text-error' : 'text-warning-text';
	$: iconBgClass =
		variant === 'red'
			? 'bg-error text-base-100'
			: 'bg-warning text-base-100';
	$: btnClass =
		variant === 'red'
			? 'btn btn-sm btn-error'
			: 'btn btn-sm btn-warning';
</script>

<div
	class="flex items-center gap-4 mb-4 rounded-box border p-3 sm:p-4 {surfaceClass}"
>
	<div
		class="w-9 h-9 sm:w-10 sm:h-10 rounded-md grid place-items-center font-display font-extrabold text-lg flex-none rotate-[-4deg] {iconBgClass}"
	>
		{icon}
	</div>
	<div class="flex-1 min-w-0">
		<div class="font-display font-extrabold text-sm sm:text-base {textClass}">{title}</div>
		<div class="text-xs sm:text-[13px] text-base-content/70 mt-0.5">{@html meta}</div>
	</div>

	{#if ctaLabel}
		{#if ctaHref}
			<a
				class={btnClass}
				href={ctaHref}
				target={ctaExternal ? '_blank' : undefined}
				rel={ctaExternal ? 'noopener noreferrer' : undefined}
			>
				{ctaLabel}
			</a>
		{:else}
			<button class={btnClass} type="button" on:click={() => onCta?.()}>
				{ctaLabel}
			</button>
		{/if}
	{/if}
</div>

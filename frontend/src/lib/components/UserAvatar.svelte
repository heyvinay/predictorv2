<script lang="ts">
	/** Used for the initial + aria-label. */
	export let name: string | null = null;
	/** Tailwind size classes for the circle (w/h). */
	export let sizeClass = 'w-9 h-9';
	/** Text size for the initial. */
	export let textClass = 'text-base';

	$: initial = (name?.charAt(0) ?? '?').toUpperCase();
</script>

<!-- Solid champagne-gold avatar (#D4AF37) with the user's initial in navy
     (#0B1329) for contrast on both light and dark themes. Replaced the
     flag-picker feature in round 2; see the plan for context. -->
<div
	class="{sizeClass} rounded-full bg-[#D4AF37] grid place-items-center ring-2 ring-[#D4AF37]/30"
	role="img"
	aria-label={name ? `${name}'s avatar` : 'avatar'}
>
	<span class="{textClass} font-bold text-[#0B1329] leading-none">{initial}</span>
</div>

<!--
	TrackedSection — generic IntersectionObserver wrapper that fires a
	`section_viewed` analytics event the first time the section becomes
	at-least-50%-visible to the user. Fires once per page load per section.

	Used on the landing page to build the scroll-depth funnel: wrap each
	major section in `<TrackedSection name="how_it_works">…</TrackedSection>`
	and Umami records which sections each visitor actually saw. Pair with
	`landing_view` (page mount) and `cta_clicked` (interactions) for a
	complete conversion picture.

	Props:
	  - `name` — semantic section identifier (e.g. "hero", "countdown",
	    "how_it_works"). Sent as the `section_name` event property.

	The wrapper renders a plain `<section>` so it doesn't change layout
	or semantics. Children render via the default slot.
-->
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { track } from '$lib/analytics';

	export let name: string;

	let el: HTMLElement;
	let fired = false;
	let obs: IntersectionObserver | undefined;

	onMount(() => {
		// SSR / older browsers / vitest jsdom — bail gracefully.
		if (typeof IntersectionObserver === 'undefined' || !el) return;

		obs = new IntersectionObserver(
			([entry]) => {
				if (!fired && entry.isIntersecting && entry.intersectionRatio >= 0.5) {
					fired = true;
					track('section_viewed', { section_name: name });
					// Once fired, stop observing — saves a tiny amount of work
					// on long pages with many tracked sections.
					obs?.disconnect();
				}
			},
			{ threshold: 0.5 }
		);
		obs.observe(el);
	});

	onDestroy(() => {
		obs?.disconnect();
	});
</script>

<section bind:this={el} class={$$props.class ?? ''}>
	<slot />
</section>

<script lang="ts">
	import { onMount } from 'svelte';

	export let formId: string;
	export let title: string = 'Embedded form';
	export let hiddenFields: Record<string, string | null | undefined> = {};
	let className: string = '';
	export { className as class };

	const TALLY_SCRIPT_SRC = 'https://tally.so/widgets/embed.js';
	const TALLY_SCRIPT_ID = 'tally-widget-script';

	interface TallyWidget {
		loadEmbeds?: () => void;
	}
	type WindowWithTally = Window & typeof globalThis & { Tally?: TallyWidget };

	$: hiddenQuery = Object.entries(hiddenFields)
		.filter(([, v]) => v != null && v !== '')
		.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v as string)}`)
		.join('&');
	$: src = `https://tally.so/embed/${formId}?alignLeft=1&hideTitle=1&transparentBackground=1&dynamicHeight=1${hiddenQuery ? `&${hiddenQuery}` : ''}`;

	function loadEmbeds() {
		(window as WindowWithTally).Tally?.loadEmbeds?.();
	}

	onMount(() => {
		if (document.getElementById(TALLY_SCRIPT_ID)) {
			loadEmbeds();
			return;
		}
		const script = document.createElement('script');
		script.id = TALLY_SCRIPT_ID;
		script.src = TALLY_SCRIPT_SRC;
		script.async = true;
		script.onload = loadEmbeds;
		script.onerror = () => {
			// Direct src= on the iframe keeps the form usable; dynamic-height is the only loss.
		};
		document.body.appendChild(script);
	});
</script>

<div class="h-full w-full {className}">
	<iframe
		{src}
		data-tally-src={src}
		{title}
		loading="lazy"
		width="100%"
		class="h-full w-full border-0"
	></iframe>
</div>

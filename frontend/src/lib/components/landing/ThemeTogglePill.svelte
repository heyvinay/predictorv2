<!--
	ThemeTogglePill — fixed bottom-right pill for switching themes on the
	landing page. The authenticated app uses the sidebar's existing
	toggle (in +layout.svelte); unauthenticated landing visitors don't
	see the sidebar at all, so this pill is their only way to flip
	themes. Mounted only on `/` in +page.svelte.

	Visual: rounded-full bg-base-200 with a thin slate border. Sun icon
	in premium-night (click = go light); moon icon in premium-day (click
	= go dark). Small caps label visible on md+ for clarity; mobile
	collapses to icon-only to save room.
-->
<script lang="ts">
	import { theme, type Theme } from '$stores/theme';
	import Sun from 'lucide-svelte/icons/sun';
	import Moon from 'lucide-svelte/icons/moon';

	// Pure dark themes — body canvas is dark. Hybrids have a LIGHT body
	// (dark chrome only) so they don't belong here.
	const DARK_THEMES = new Set<Theme>(['premium-night', 'vin-dark']);

	// Authenticated users get the full six-theme picker in the rail/navbar;
	// this pill is the unauthenticated visitor's fast night↔day affordance.
	// Light-bodied themes (hybrid, vin-light, vin-hybrid) flip to premium-night
	// so the binary toggle stays predictable regardless of the stored preference.
	function toggle() {
		theme.update((t) => (DARK_THEMES.has(t) ? 'premium-day' : 'premium-night'));
	}

	$: isDark = DARK_THEMES.has($theme);
</script>

<button
	type="button"
	class="fixed bottom-5 right-5 z-50 inline-flex items-center gap-2 px-3.5 py-2 rounded-full
		bg-base-200/90 backdrop-blur border border-base-300/60 shadow-card
		text-xs font-mono uppercase tracking-widest text-base-content/70
		hover:text-base-content hover:border-primary/40 transition-colors"
	on:click={toggle}
	aria-label="Toggle colour theme"
	title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
>
	{#if isDark}
		<Sun size={14} />
		<span class="hidden sm:inline">Light</span>
	{:else}
		<Moon size={14} />
		<span class="hidden sm:inline">Dark</span>
	{/if}
</button>

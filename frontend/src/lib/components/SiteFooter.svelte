<!--
	SiteFooter — thin closing row, brand mark + tagline + minimal links.
	Rendered globally by +layout.svelte for every route EXCEPT the entry
	wizard (`/entries/[entryId]`), where vertical room is at a premium and
	the BottomActionBar already anchors the page.

	The "Home" link points at the absolute production URL
	(https://wc26.heyvinay.com/) rather than a relative `/` per design call
	— "Home" here means "the canonical landing page on production". In
	dev/staging this jumps out of the local environment to production;
	swap to `href="/"` if that becomes undesirable.
-->
<script lang="ts">
	import { supportOpen } from '$stores/supportPanel';
	import { openRatingPrompt } from '$stores/ratingPrompt';
	import { isAuthenticated } from '$stores/auth';
	import { track } from '$lib/analytics';
	import { currentVersion } from '$lib/utils/releases';

	const version = currentVersion();

	function trackFooterNav(target: string, label: string) {
		track('nav_clicked', { source: 'footer', target, label });
	}

	function onFeedbackClick() {
		trackFooterNav('rating_card', 'Feedback');
		openRatingPrompt();
	}

	function onRulesClick() {
		// Keep the pre-existing rules_link_clicked event for backwards-compat
		// with funnels that reference it. nav_clicked fires alongside.
		track('rules_link_clicked', { placement: 'footer' });
		trackFooterNav('/rules', 'Rules');
	}

	function onContactClick() {
		trackFooterNav('support_panel', 'Contact');
		supportOpen.set(true);
	}
</script>

<footer class="border-t border-base-300/60 bg-base-100">
	<div class="max-w-[1200px] mx-auto mobile-padding py-10 flex flex-col items-center gap-4">
		<div class="flex items-center gap-2.5">
			<img
				src="/logo.png"
				alt=""
				class="w-7 h-7 rounded-full object-cover"
				aria-hidden="true"
			/>
			<span class="font-display text-sm tracking-[0.06em] text-base-content/70 lowercase">
				atlas world cup pools
			</span>
		</div>

		<p class="text-sm text-base-content/55 text-center">
			Built for fun and one trophy.
		</p>

		<nav
			class="flex items-center gap-5 text-xs font-mono uppercase tracking-widest text-base-content/55"
			aria-label="Footer"
		>
			<a
				href="https://wc26.heyvinay.com/"
				class="hover:text-primary transition-colors"
				on:click={() => trackFooterNav('https://wc26.heyvinay.com/', 'Home')}
			>
				Home
			</a>
			<span class="text-base-content/20" aria-hidden="true">·</span>
			<a href="/rules" class="hover:text-primary transition-colors" on:click={onRulesClick}>
				Rules
			</a>
			<span class="text-base-content/20" aria-hidden="true">·</span>
			<a
				href="/privacy"
				class="hover:text-primary transition-colors"
				on:click={() => trackFooterNav('/privacy', 'Privacy')}
			>Privacy</a>
			<span class="text-base-content/20" aria-hidden="true">·</span>
			<button
				type="button"
				class="hover:text-primary transition-colors font-mono uppercase tracking-widest"
				on:click={onContactClick}
			>
				Contact
			</button>
			{#if $isAuthenticated}
				<span class="text-base-content/20" aria-hidden="true">·</span>
				<button
					type="button"
					class="hover:text-primary transition-colors font-mono uppercase tracking-widest"
					on:click={onFeedbackClick}
				>
					Feedback
				</button>
			{/if}
		</nav>

		<p class="text-[11px] font-mono text-base-content/30" aria-label="App version">
			v{version}
		</p>
	</div>
</footer>

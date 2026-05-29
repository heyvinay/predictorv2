<!--
	StickyTopBar — minimal top bar shown on the landing page. Sticky,
	z-40, backdrop-blur, ~64px tall. Brand lockup on the left; right
	side swaps between a "Sign in" anchor (unauth → scrolls to #signin)
	and an avatar initial badge (auth).

	The existing authenticated app has its own sidebar in +layout.svelte;
	this top bar exists primarily so unauthenticated visitors have
	chrome to anchor on while scrolling the landing. Authenticated users
	on the landing see both this bar AND the sidebar — by design, since
	the landing is positioned as "visible to everyone".
-->
<script lang="ts">
	import { isAuthenticated, user } from '$stores/auth';
	import UserAvatar from '$components/UserAvatar.svelte';
	import { track } from '$lib/analytics';

	function logoFallback(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="font-display text-lg leading-none text-primary">P</span>';
	}

	function onSignInClick() {
		track('cta_clicked', {
			placement: 'top_bar',
			cta_label: 'sign_in_anchor',
			auth_state: 'guest'
		});
	}
</script>

<header
	class="sticky top-0 z-40 backdrop-blur-md bg-base-100/85 border-b border-base-300/50"
>
	<div class="max-w-[1200px] mx-auto h-16 mobile-padding flex items-center justify-between gap-4">
		<!-- Brand lockup -->
		<a href="/" class="flex items-center gap-3" aria-label="The Predictor — home">
			<img
				src="/logo.png"
				alt=""
				class="w-10 h-10 rounded-full object-cover shrink-0"
				on:error={logoFallback}
				aria-hidden="true"
			/>
			<span class="flex flex-col leading-tight">
				<span class="font-display text-xl text-primary tracking-[0.06em] lowercase">
					atlas world cup pools
				</span>
				<span class="text-[9px] font-mono uppercase tracking-[0.18em] text-base-content/45">
					WC 2026
				</span>
			</span>
		</a>

		<!-- Right side: sign-in link OR avatar -->
		{#if $isAuthenticated}
			<a
				href="/profile"
				class="shrink-0 hover:opacity-80 transition-opacity"
				aria-label="Open profile"
			>
				<UserAvatar name={$user?.name ?? null} />
			</a>
		{:else}
			<a
				href="#signin"
				class="text-xs font-mono uppercase tracking-widest text-base-content/70 hover:text-primary transition-colors"
				on:click={onSignInClick}
			>
				Sign in
			</a>
		{/if}
	</div>
</header>

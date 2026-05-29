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
	import { supportOpen } from '$stores/supportPanel';
	import UserAvatar from '$components/UserAvatar.svelte';
	import HelpCircle from 'lucide-svelte/icons/help-circle';
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
		<!-- Brand lockup — Bebas Neue (font-hero) is the editorial broadcast
		     letterform; matches the mockup. Uppercase for the tall, even
		     cap-height read that pairs with the gold accent. -->
		<a href="/" class="flex items-center gap-3" aria-label="The Predictor — home">
			<img
				src="/logo.png"
				alt=""
				class="w-9 h-9 sm:w-10 sm:h-10 rounded-full object-cover shrink-0"
				on:error={logoFallback}
				aria-hidden="true"
			/>
			<span class="flex flex-col leading-tight">
				<span class="font-hero text-lg sm:text-xl text-primary tracking-[0.06em] uppercase">
					atlas world cup pools
				</span>
				<span
					class="text-[9px] font-mono uppercase tracking-[0.18em] text-base-content/45 mt-0.5"
				>
					WC 2026
				</span>
			</span>
		</a>

		<!-- Right side: sign-in link (or avatar) THEN help icon at the far
		     right. The help icon replicates the layout's top-bar help
		     button so guests on the landing can reach the same
		     SupportPanel that authenticated users get; SupportPanel is
		     mounted globally in +layout.svelte outside the auth
		     conditional. -->
		<div class="flex items-center gap-2 sm:gap-3 shrink-0">
			{#if $isAuthenticated}
				<a
					href="/profile"
					class="hover:opacity-80 transition-opacity"
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

			<button
				type="button"
				class="btn btn-ghost btn-sm btn-circle text-base-content/70 hover:text-primary"
				aria-label="Help and support"
				title="Help & support"
				on:click={() => supportOpen.set(true)}
			>
				<HelpCircle size={18} strokeWidth={2} />
			</button>
		</div>
	</div>
</header>

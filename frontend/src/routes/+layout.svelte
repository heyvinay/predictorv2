<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { goto, afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user, logout, initAuth } from '$stores/auth';
	import { initAnalytics, identify, track } from '$lib/analytics';
	import { fetchPhaseStatus, phase1Deadline, currentTime } from '$stores/phase';
	import { theme, chromeThemeFor } from '$stores/theme';
	import { activeEntry, editableEntries } from '$stores/entries';
	import { pageTitle } from '$stores/pageTitle';
	import { supportOpen } from '$stores/supportPanel';
	import { wizardSectionLabel } from '$stores/wizardCrumb';
	import {
		adminAttentionCount,
		startAdminAttentionPolling,
		stopAdminAttentionPolling
	} from '$stores/adminAttention';
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';
	import CountdownTimer from '$components/predictions/CountdownTimer.svelte';
	import SiteFooter from '$lib/components/SiteFooter.svelte';
	import SupportPanel from '$lib/components/SupportPanel.svelte';
	import UserAvatar from '$lib/components/UserAvatar.svelte';
	import { needsOnboarding } from '$lib/utils/onboarding';

	let hasLoadedPhase = false;

	onMount(() => {
		initAuth();
		// Bootstrap PostHog browser SDK (autocapture, heatmaps, pageviews).
		// Idempotent + DNT-aware + SSR-safe. See lib/analytics/index.ts.
		initAnalytics();
	});

	// Tag the session with the user's UUID once auth hydrates so events
	// across pageloads attribute to the same distinct_id. No PII sent —
	// PostHog only sees the UUID.
	$: if ($user) identify($user.id);

	// Universal page-view capture for every successful route transition.
	// Catches rail clicks, footer clicks, programmatic goto(), browser
	// back/forward — everything. nav.type is SvelteKit's discriminator
	// ('link' | 'goto' | 'enter' | 'popstate' | 'leave' | 'form').
	afterNavigate((nav) => {
		void track('page_viewed', {
			path: nav.to?.url.pathname ?? '',
			referrer_path: nav.from?.url.pathname ?? null,
			nav_type: nav.type,
		});
	});

	/** Source-tagged nav-click helper. Fires `nav_clicked` with which UI
	 *  the user came from, where they're going, and the visible label.
	 *  Complements `page_viewed` — same destination reached from
	 *  different surfaces tells us which UI users actually use. */
	function trackNav(source: string, target: string, label: string) {
		void track('nav_clicked', { source, target, label });
	}

	// Fetch phase status when user becomes authenticated
	$: if ($isAuthenticated && !hasLoadedPhase) {
		hasLoadedPhase = true;
		fetchPhaseStatus();
	}

	// Admin attention polling — only runs for admins, stops on logout.
	$: if ($isAuthenticated && $user?.is_admin) {
		startAdminAttentionPolling();
	} else if (!$isAuthenticated) {
		stopAdminAttentionPolling();
	}

	// Users missing any mandatory profile field (name, employer, or the
	// neither-contact) are routed to onboarding — this also back-fills
	// existing/Google accounts that predate the new fields.
	$: if ($isAuthenticated && needsOnboarding($user) && $page.url.pathname !== '/onboarding') {
		goto('/onboarding');
	}

	// Document-text icon for Rules.
	const navItems = [
		{ href: '/', label: 'Home', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
		{ href: '/entries', label: 'Entries', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
		{ href: '/results', label: 'Results', icon: 'M3 7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7zM12 5v14M6 11v2M18 11v2' },
		{ href: '/leaderboard', label: 'Standings', icon: 'M9 21h6m-3 -4v4M7 4h10v4a5 5 0 01-10 0V4zM7 6H4a3 3 0 003 3m10 -3h3a3 3 0 01-3 3' },
		{ href: '/rules', label: 'Rules', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' }
	];

	$: currentPath = $page.url.pathname;

	// On the wizard route (/entries/[entryId]), the topbar swaps its
	// centred content for a breadcrumb (desktop) or a context-aware
	// back-link + record name (mobile).
	$: isWizardRoute = $page.route?.id === '/entries/[entryId]';
	$: entryCrumbLabel = $activeEntry
		? $activeEntry.display_name || `Entry #${$activeEntry.entry_number}`
		: '';
	// Desktop breadcrumb: Entries › <entry> › <section>. The section crumb
	// is appended only when the wizard page has published a section label.
	$: wizardCrumbs =
		isWizardRoute && $activeEntry
			? [
					{ label: 'Entries', href: '/entries' },
					{ label: entryCrumbLabel, href: undefined },
					...($wizardSectionLabel ? [{ label: $wizardSectionLabel }] : [])
				]
			: [];
	// Mobile breadcrumb: <entry> › <section> only — "Entries" is already
	// covered by the back button, so we drop it to save horizontal room.
	$: mobileCrumbs =
		isWizardRoute && $activeEntry
			? [
					{ label: entryCrumbLabel },
					...($wizardSectionLabel ? [{ label: $wizardSectionLabel }] : [])
				]
			: [];

	// Live deadline visibility — keeps lock pressure visible site-wide.
	$: hasLiveDeadline =
		!!$phase1Deadline && new Date($phase1Deadline).getTime() > $currentTime.getTime();

	// Chrome wrappers (rail / topbars / bottom-nav) carry data-theme={chromeTheme}.
	// Under `hybrid` (the light body) this is 'premium-night' so the chrome
	// flips to the dark broadcast palette; under `premium-night` itself the
	// value is null and Svelte 4 removes the attribute, so chrome inherits
	// the body theme.
	$: chromeTheme = chromeThemeFor($theme);

	function toggleTheme() {
		theme.update((t) => (t === 'premium-night' ? 'hybrid' : 'premium-night'));
	}

	// Logo fallback — if /logo.png is missing, swap the <img> for the
	// letter-P brand mark. Sized to roughly match the image dimensions
	// (rail w-10 ≈ 40px → text-3xl; mobile w-10 ≈ 40px → text-3xl).
	function logoFallbackRail(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="nav-brand text-3xl leading-none">P</span>';
	}
	function logoFallbackMobile(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="nav-brand text-3xl leading-none">P</span>';
	}
</script>

<div class="min-h-screen bg-base-100 flex flex-col noise overflow-x-clip">
	<!-- Support side panel (renders only when open) -->
	<SupportPanel />

	<!-- Navigation -->
	{#if $isAuthenticated}
		<!-- Desktop left rail (≥700px). w-48 with icon + label on each item.
		     Brand at top, nav in the middle, avatar pinned to the bottom. -->
		<aside
			data-theme={chromeTheme}
			class="fixed left-0 top-0 h-screen w-48 z-50 hidden min-[700px]:flex flex-col bg-base-200 border-r border-base-300/50"
			aria-label="Primary navigation"
		>
			<!-- Brand mark — circular logo image with letter-P fallback.
			     Wordmark "PREDICTOR" removed 2026-06-01 per design call —
			     the icon alone carries the brand. Left-aligned with px-3 so
			     the logo's left edge sits in the same column as the nav-item
			     icons below it (those use px-3 + gap-3, so their icons
			     start at 12px from the rail's left edge). Sized w-10 h-10 to
			     match the rail avatar at the bottom of the rail. -->
			<a
				href="/"
				class="h-16 flex items-center justify-start hover:opacity-80 transition-opacity flex-shrink-0 px-3"
				aria-label="Predictor home"
			>
				<img
					src="/logo.png"
					alt="Predictor"
					class="h-10 w-10 rounded-full object-cover"
					on:error={logoFallbackRail}
				/>
			</a>

			<!-- Primary nav items — icon + label rows. -->
			<nav class="flex-1 flex flex-col gap-1 py-2 px-2 min-h-0">
				{#each navItems as item}
					{@const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
					{@const badge = item.href === '/entries' ? $editableEntries.length : 0}
					<div class="relative w-full">
						{#if isActive}
							<span
								class="absolute left-0 top-1 bottom-1 w-[3px] bg-primary rounded-r"
								aria-hidden="true"
							></span>
						{/if}
						<a
							href={item.href}
							on:click={() => trackNav('left-rail', item.href, item.label)}
							class="relative w-full flex items-center gap-3 h-10 px-3 rounded-lg transition-colors
								{isActive
									? 'text-primary bg-base-300/40'
									: 'text-base-content/70 hover:text-base-content hover:bg-base-300/40'}"
							aria-current={isActive ? 'page' : undefined}
						>
							<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
							</svg>
							<span class="text-sm font-medium">{item.label}</span>
							{#if badge > 0}
								<span
									class="ml-auto badge badge-warning badge-xs font-mono"
									aria-label="{badge} draft entries pending"
								>{badge}</span>
							{/if}
						</a>
					</div>
				{/each}
			</nav>

			<!-- Avatar dropdown pinned at the bottom. -->
			<div class="flex-shrink-0 p-2 border-t border-base-300/40">
				<div class="dropdown dropdown-top dropdown-end w-full">
					<div
						tabindex="0"
						role="button"
						class="btn btn-ghost h-12 w-full justify-start px-2 gap-2"
					>
						<div class="relative">
							<!-- Sized to match the rail brand logo at the top of the rail
							     (w-10 h-10) so both ends of the rail have matched anchor weights. -->
							<UserAvatar name={$user?.name ?? null} sizeClass="w-10 h-10" />
							{#if $user?.is_admin && $adminAttentionCount > 0}
								<span
									class="absolute -top-1 -right-1 badge badge-warning badge-xs font-mono"
									aria-label="{$adminAttentionCount} unpaid entries need attention"
								>{$adminAttentionCount}</span>
							{/if}
						</div>
						<span class="text-sm font-medium truncate flex-1 text-left">{$user?.name ?? ''}</span>
					</div>
					<ul
						tabindex="0"
						class="menu menu-sm dropdown-content mb-2 z-[1] p-2 shadow-lg bg-base-200 border border-base-300/50 rounded-xl w-52"
					>
						<li>
							<a href="/profile" class="rounded-lg">
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
								</svg>
								Profile
							</a>
						</li>
						{#if $user?.is_admin}
							<li>
								<a href="/admin" class="rounded-lg">
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
										<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
									</svg>
									<span class="flex-1">Admin</span>
									{#if $adminAttentionCount > 0}
										<span class="badge badge-warning badge-xs">{$adminAttentionCount}</span>
									{/if}
								</a>
							</li>
						{/if}
						<li>
							<button on:click={logout} class="rounded-lg text-error hover:bg-error/10">
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
								</svg>
								Logout
							</button>
						</li>
					</ul>
				</div>
			</div>
		</aside>

		<!-- Desktop topbar: holds page title (left), live deadline pill (centre)
		     and help-icon button (right). Renders on desktop ≥700px. -->
		<div
			data-theme={chromeTheme}
			class="hidden min-[700px]:flex sticky top-0 z-40 h-14 items-center justify-between gap-4 bg-base-100/95 bg-stadium-glow backdrop-blur-md border-b border-base-300/50 px-6 min-[700px]:pl-[13.5rem]"
		>
			<div class="flex items-center min-w-0 flex-1">
				{#if isWizardRoute && wizardCrumbs.length > 0}
					<Breadcrumb crumbs={wizardCrumbs} />
				{:else if $pageTitle}
					<h1 class="text-xl font-display tracking-wide truncate">{$pageTitle}</h1>
				{/if}
			</div>
			<div class="flex items-center gap-3">
				{#if hasLiveDeadline}
					<CountdownTimer deadline={$phase1Deadline} />
				{/if}
				<div
					class="tooltip tooltip-bottom"
					data-tip={$theme === 'premium-night' ? 'Switch to light mode' : 'Switch to dark mode'}
				>
					<button
						class="btn btn-ghost btn-sm btn-circle"
						aria-label={$theme === 'premium-night' ? 'Switch to light mode' : 'Switch to dark mode'}
						on:click={toggleTheme}
					>
						{#if $theme === 'premium-night'}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
							</svg>
						{:else}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
							</svg>
						{/if}
					</button>
				</div>
				<div class="tooltip tooltip-bottom" data-tip="Help & support">
					<button
						class="btn btn-ghost btn-sm btn-circle"
						aria-label="Help and support"
						on:click={() => supportOpen.set(true)}
					>
						<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093M12 17h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
					</button>
				</div>
			</div>
		</div>

		<!-- Mobile top navbar (≤699px only). Logo + page title + deadline + avatar. -->
		<nav data-theme={chromeTheme} class="navbar bg-base-200 bg-stadium-glow border-b border-base-300/50 sticky top-0 z-50 min-[700px]:hidden">
			<div class="navbar-start gap-1 min-w-0 flex-1">
				{#if isWizardRoute}
					<!-- Back button (icon-only to save room) + left-aligned
					     breadcrumb. Together they read "‹ Entries › <name> ›
					     <section>" with the chevron acting as the Entries
					     back-affordance. -->
					<a
						href="/entries"
						class="btn btn-ghost btn-sm btn-square shrink-0"
						aria-label="Back to Entries"
					>
						<svg
							class="w-4 h-4"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
							aria-hidden="true"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
						</svg>
					</a>
					{#if mobileCrumbs.length > 0}
						<div class="flex min-w-0">
							<Breadcrumb crumbs={mobileCrumbs} />
						</div>
					{/if}
				{:else}
					<a href="/" class="flex items-center px-3 hover:opacity-80 transition-opacity">
						<!-- Mobile logo sized to match the mobile avatar (w-10 h-10) at
						     the right end of this navbar — balanced weights at both ends.
						     The DaisyUI navbar already accommodates w-10 children
						     (the avatar at line ~377 uses the same size). -->
						<img
							src="/logo.png"
							alt="Predictor"
							class="h-10 w-10 rounded-full object-cover"
							on:error={logoFallbackMobile}
						/>
					</a>
					<!-- Page title sits next to the logo (left-aligned) rather than
					     in navbar-center, which would compete for room with the
					     deadline pill + theme/help/avatar in navbar-end. `truncate`
					     + parent `min-w-0 flex-1` handle long titles gracefully. -->
					{#if $pageTitle}
						<span class="font-display text-lg tracking-wide truncate">
							{$pageTitle}
						</span>
					{/if}
				{/if}
			</div>

			<div class="navbar-end gap-1">
				{#if hasLiveDeadline}
					<CountdownTimer deadline={$phase1Deadline} compact />
				{/if}
				<div
					class="tooltip tooltip-bottom"
					data-tip={$theme === 'premium-night' ? 'Switch to light mode' : 'Switch to dark mode'}
				>
					<button
						class="btn btn-ghost btn-sm btn-circle"
						aria-label={$theme === 'premium-night' ? 'Switch to light mode' : 'Switch to dark mode'}
						on:click={toggleTheme}
					>
						{#if $theme === 'premium-night'}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
							</svg>
						{:else}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
							</svg>
						{/if}
					</button>
				</div>
				<div class="tooltip tooltip-bottom" data-tip="Help & support">
					<button
						class="btn btn-ghost btn-sm btn-circle"
						aria-label="Help and support"
						on:click={() => supportOpen.set(true)}
					>
						<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093M12 17h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
					</button>
				</div>
				<div class="dropdown dropdown-end">
					<div tabindex="0" role="button" class="btn btn-ghost btn-circle">
						<div class="relative">
							<UserAvatar name={$user?.name ?? null} sizeClass="w-10 h-10" textClass="text-lg" />
							{#if $user?.is_admin && $adminAttentionCount > 0}
								<span
									class="absolute -top-1 -right-1 badge badge-warning badge-xs font-mono"
									aria-label="{$adminAttentionCount} unpaid entries need attention"
								>{$adminAttentionCount}</span>
							{/if}
						</div>
					</div>
					<ul
						tabindex="0"
						class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow-lg bg-base-200 border border-base-300/50 rounded-xl w-52"
					>
						<li class="menu-title px-3 py-2 text-xs text-base-content/50 uppercase tracking-wider">
							{$user?.name}
						</li>
						<li>
							<a href="/profile" class="rounded-lg">
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
								</svg>
								Profile
							</a>
						</li>
						{#if $user?.is_admin}
							<li>
								<a href="/admin" class="rounded-lg">
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
										<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
									</svg>
									<span class="flex-1">Admin</span>
									{#if $adminAttentionCount > 0}
										<span class="badge badge-warning badge-xs">{$adminAttentionCount}</span>
									{/if}
								</a>
							</li>
						{/if}
						<li>
							<button on:click={logout} class="rounded-lg text-error hover:bg-error/10">
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
								</svg>
								Logout
							</button>
						</li>
					</ul>
				</div>
			</div>
		</nav>

		<!-- Mobile bottom navigation -->
		<nav data-theme={chromeTheme} class="fixed bottom-0 left-0 right-0 z-50 min-[700px]:hidden bg-base-200/95 backdrop-blur-md border-t border-base-300/50 h-14 flex items-center justify-around">
			{#each navItems as item}
				{@const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
				{@const badge = item.href === '/entries' ? $editableEntries.length : 0}
				<a
					href={item.href}
					on:click={() => trackNav('mobile-bottom-nav', item.href, item.label)}
					class="flex flex-col items-center justify-center gap-0.5 px-2 py-1 transition-colors duration-200
						{isActive ? 'text-primary' : 'text-base-content/50'}"
				>
					<div class="relative">
						<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
						</svg>
						{#if badge > 0}
							<span
								class="absolute -top-1.5 -right-2 badge badge-warning badge-xs font-mono"
								aria-label="{badge} draft entries pending"
							>{badge}</span>
						{/if}
					</div>
					<span class="text-[9px] font-medium">{item.label}</span>
				</a>
			{/each}
		</nav>
	{/if}

	<!-- Main content. Padding-left clears the desktop rail; bottom padding
	     clears the mobile tab bar. Both navs are auth-gated above, so we
	     only reserve space for them when actually rendering them —
	     otherwise guests get a phantom left column on `/` (the landing). -->
	<main class="flex-1 {$isAuthenticated ? 'pb-16 min-[700px]:pb-0 min-[700px]:pl-48' : ''}">
		<slot />
	</main>

	<!-- Site footer renders on every route except the entry wizard
	     (`/entries/[entryId]`), where vertical real-estate is at a premium
	     and the BottomActionBar already anchors the page. Promoted from
	     landing-only to global on 2026-06-01. -->
	{#if !isWizardRoute}
		<div class="{$isAuthenticated ? 'min-[700px]:pl-48' : ''}">
			<SiteFooter />
		</div>
	{/if}
</div>

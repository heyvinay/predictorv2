<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated, user, logout, initAuth } from '$stores/auth';
	import { fetchPhaseStatus } from '$stores/phase';
	import { theme, THEMES } from '$stores/theme';
	import { activeEntry, editableEntries } from '$stores/entries';
	import {
		adminAttentionCount,
		startAdminAttentionPolling,
		stopAdminAttentionPolling
	} from '$stores/adminAttention';
	import Breadcrumb from '$lib/components/Breadcrumb.svelte';

	let hasLoadedPhase = false;

	onMount(() => {
		initAuth();
	});

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

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
		{ href: '/entries', label: 'Entries', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
		{ href: '/results', label: 'Results', icon: 'M3 7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7zM12 5v14M6 11v2M18 11v2' },
		{ href: '/leaderboard', label: 'Leaderboard', icon: 'M9 21h6m-3 -4v4M7 4h10v4a5 5 0 01-10 0V4zM7 6H4a3 3 0 003 3m10 -3h3a3 3 0 01-3 3' },
		{ href: '/rules', label: 'Rules', icon: 'M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z' }
	];

	$: currentPath = $page.url.pathname;

	// On the wizard route (/entries/[entryId]), the topbar swaps its
	// centred content for a breadcrumb (desktop) or a context-aware
	// back-link + record name (mobile). Read $page.route?.id so URL
	// param changes don't accidentally toggle the slot.
	$: isWizardRoute = $page.route?.id === '/entries/[entryId]';
	$: wizardCrumbs =
		isWizardRoute && $activeEntry
			? [
					{ label: 'Entries', href: '/entries' },
					{ label: $activeEntry.display_name || `Entry #${$activeEntry.entry_number}` }
				]
			: [];
</script>

<div class="min-h-screen bg-base-100 flex flex-col noise">
	<!-- Navigation -->
	{#if $isAuthenticated}
		<!-- Desktop left rail (≥700px). Holds brand at top, nav items in
		     the middle, avatar dropdown pinned to the bottom. Replaces
		     the centred horizontal nav from Phase 1. -->
		<aside
			class="fixed left-0 top-0 h-screen w-16 z-50 hidden min-[700px]:flex flex-col bg-base-200 border-r border-base-300/50"
			aria-label="Primary navigation"
		>
			<!-- Brand mark — letterform stand-in for the full wordmark. -->
			<a
				href="/"
				class="h-16 flex items-center justify-center hover:opacity-80 transition-opacity flex-shrink-0"
				aria-label="Predictor home"
			>
				<span class="nav-brand text-2xl leading-none">P</span>
			</a>

			<!-- Primary nav items. -->
			<nav class="flex-1 flex flex-col items-center gap-1 py-2 min-h-0">
				{#each navItems as item}
					{@const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
					{@const badge = item.href === '/entries' ? $editableEntries.length : 0}
					<div class="relative w-full flex justify-center tooltip tooltip-right" data-tip={item.label}>
						{#if isActive}
							<span
								class="absolute left-0 top-1 bottom-1 w-[3px] bg-primary rounded-r"
								aria-hidden="true"
							></span>
						{/if}
						<a
							href={item.href}
							class="relative w-12 h-12 flex items-center justify-center rounded-lg transition-colors
								{isActive
									? 'text-primary'
									: 'text-base-content/60 hover:text-base-content hover:bg-base-300/40'}"
							aria-label={item.label}
							aria-current={isActive ? 'page' : undefined}
						>
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
							</svg>
							{#if badge > 0}
								<span
									class="absolute top-1 right-1 badge badge-warning badge-xs font-mono"
									aria-label="{badge} draft entries pending"
								>{badge}</span>
							{/if}
						</a>
					</div>
				{/each}

			</nav>

			<!-- Avatar dropdown pinned at the bottom. Opens to the right. -->
			<div class="flex-shrink-0 p-2">
				<div class="dropdown dropdown-right dropdown-end">
					<div tabindex="0" role="button" class="btn btn-ghost btn-circle btn-sm tooltip tooltip-right" data-tip={$user?.name ?? ''}>
						<div class="relative">
							<div class="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20">
								<span class="text-base font-bold text-white leading-none">{$user?.name?.charAt(0).toUpperCase() || '?'}</span>
							</div>
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
						class="menu menu-sm dropdown-content ml-2 z-[1] p-2 shadow-lg bg-base-200 border border-base-300/50 rounded-xl w-52"
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
							<details>
								<summary class="rounded-lg">
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
									</svg>
									Theme
									<span class="ml-auto text-xs opacity-60 capitalize">{$theme}</span>
								</summary>
								<ul class="max-h-64 overflow-y-auto flex-nowrap">
									{#each THEMES as t}
										<li>
											<label class="cursor-pointer flex items-center gap-2 rounded-lg">
												<input
													type="radio"
													name="theme-rail"
													class="theme-controller radio radio-xs radio-primary"
													value={t}
													checked={$theme === t}
													on:change={() => theme.set(t)}
												/>
												<span class="capitalize">{t}</span>
											</label>
										</li>
									{/each}
								</ul>
							</details>
						</li>
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

		<!-- Desktop topbar: thin strip that holds the breadcrumb when on a
		     wizard route. Only renders on desktop ≥700px AND only when a
		     breadcrumb exists — otherwise the rail is the entire chrome. -->
		{#if isWizardRoute && wizardCrumbs.length > 0}
			<div
				class="hidden min-[700px]:flex sticky top-0 z-40 h-12 items-center px-4 bg-base-100/95 backdrop-blur-md border-b border-base-300/50 min-[700px]:ml-16"
			>
				<Breadcrumb crumbs={wizardCrumbs} />
			</div>
		{/if}

		<!-- Mobile top navbar (≤699px only). Holds back-link / brand / record
		     name / avatar. The desktop centred nav was lifted into the rail
		     above, so this navbar is entirely hidden on desktop. -->
		<nav class="navbar bg-base-200 border-b border-base-300/50 sticky top-0 z-50 min-[700px]:hidden">
			<div class="navbar-start gap-2 min-w-0">
				{#if isWizardRoute}
					<a
						href="/entries"
						class="btn btn-ghost btn-sm gap-1"
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
						Entries
					</a>
				{:else}
					<a href="/" class="nav-brand px-4 hover:opacity-80 transition-opacity">
						PREDICTOR
					</a>
				{/if}
			</div>

			{#if isWizardRoute && $activeEntry}
				<!-- Mobile centred record name; mirrors iOS native pattern. -->
				<div class="navbar-center flex min-w-0 px-2">
					<span class="font-semibold truncate max-w-[60vw]">
						{$activeEntry.display_name || `Entry #${$activeEntry.entry_number}`}
					</span>
				</div>
			{/if}

			<div class="navbar-end">
				<div class="dropdown dropdown-end">
					<div tabindex="0" role="button" class="btn btn-ghost btn-circle">
						<div class="relative">
							<div class="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20">
								<span class="text-lg font-bold text-white leading-none translate-y-0.5">{$user?.name?.charAt(0).toUpperCase() || '?'}</span>
							</div>
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
							<details>
								<summary class="rounded-lg">
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
									</svg>
									Theme
									<span class="ml-auto text-xs opacity-60 capitalize">{$theme}</span>
								</summary>
								<ul class="max-h-64 overflow-y-auto flex-nowrap">
									{#each THEMES as t}
										<li>
											<label class="cursor-pointer flex items-center gap-2 rounded-lg">
												<input
													type="radio"
													name="theme-dropdown"
													class="theme-controller radio radio-xs radio-primary"
													value={t}
													checked={$theme === t}
													on:change={() => theme.set(t)}
												/>
												<span class="capitalize">{t}</span>
											</label>
										</li>
									{/each}
								</ul>
							</details>
						</li>
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
		<nav class="fixed bottom-0 left-0 right-0 z-50 min-[700px]:hidden bg-base-200/95 backdrop-blur-md border-t border-base-300/50 h-14 flex items-center justify-around">
			{#each navItems as item}
				{@const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
				{@const badge = item.href === '/entries' ? $editableEntries.length : 0}
				<a
					href={item.href}
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

	<!-- Main content. Padding-left shifts past the rail on desktop; bottom
	     padding accounts for the mobile tab bar (cleared on desktop). -->
	<main class="flex-1 pb-16 min-[700px]:pb-0 min-[700px]:pl-16">
		<slot />
	</main>
</div>

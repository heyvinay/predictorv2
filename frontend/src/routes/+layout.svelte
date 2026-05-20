<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated, user, logout, initAuth } from '$stores/auth';
	import { fetchPhaseStatus } from '$stores/phase';

	let hasLoadedPhase = false;

	onMount(() => {
		initAuth();
	});

	// Fetch phase status when user becomes authenticated
	$: if ($isAuthenticated && !hasLoadedPhase) {
		hasLoadedPhase = true;
		fetchPhaseStatus();
	}

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
		{ href: '/predictions', label: 'Predictions', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
		{ href: '/results', label: 'Results', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
		{ href: '/leaderboard', label: 'Leaderboard', icon: 'M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z' }
	];

	$: currentPath = $page.url.pathname;
</script>

<div class="min-h-screen bg-base-100 flex flex-col noise">
	<!-- Navigation -->
	{#if $isAuthenticated}
		<nav class="navbar bg-base-200 border-b border-base-300/50 sticky top-0 z-50">
			<div class="navbar-start">
				<a href="/" class="nav-brand px-4 hover:opacity-80 transition-opacity">
					PREDICTOR
				</a>
			</div>

			<div class="navbar-center hidden min-[700px]:flex">
				<ul class="flex items-center gap-1">
					{#each navItems as item}
						{@const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
						<li>
							<a
								href={item.href}
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
									{isActive
										? 'bg-primary/10 text-primary'
										: 'text-base-content/70 hover:text-base-content hover:bg-base-300/50'}"
							>
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
								</svg>
								{item.label}
							</a>
						</li>
					{/each}
					{#if $user?.is_admin}
						<li>
							<a
								href="/admin"
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
									{currentPath.startsWith('/admin')
										? 'bg-primary/10 text-primary'
										: 'text-base-content/70 hover:text-base-content hover:bg-base-300/50'}"
							>
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
									<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
								</svg>
								Admin
							</a>
						</li>
					{/if}
				</ul>
			</div>

			<div class="navbar-end">
				<div class="dropdown dropdown-end">
					<div tabindex="0" role="button" class="btn btn-ghost btn-circle">
						<div class="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20">
							<span class="text-lg font-bold text-white leading-none translate-y-0.5">{$user?.name?.charAt(0).toUpperCase() || '?'}</span>
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
				<a
					href={item.href}
					class="flex flex-col items-center justify-center gap-0.5 px-2 py-1 transition-colors duration-200
						{isActive ? 'text-primary' : 'text-base-content/50'}"
				>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
					</svg>
					<span class="text-[9px] font-medium">{item.label}</span>
				</a>
			{/each}
			{#if $user?.is_admin}
				<a
					href="/admin"
					class="flex flex-col items-center justify-center gap-0.5 px-2 py-1 transition-colors duration-200
						{currentPath.startsWith('/admin') ? 'text-primary' : 'text-base-content/50'}"
				>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
					</svg>
					<span class="text-[9px] font-medium">Admin</span>
				</a>
			{/if}
		</nav>
	{/if}

	<!-- Main content -->
	<main class="flex-1 pb-16 min-[700px]:pb-0">
		<slot />
	</main>
</div>

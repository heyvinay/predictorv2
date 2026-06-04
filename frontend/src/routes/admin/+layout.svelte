<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$lib/stores/auth';
	import { getAdminStats } from '$lib/api/admin';
	import type { AdminStats } from '$lib/api/admin';
	import { onMount } from 'svelte';

	// v2.156.0 — admin layout hoists the guard from +page.svelte so
	// every /admin/* route (Users, Entries, Audit, etc.) inherits the
	// admin-only access check + persistent sub-nav.
	let stats: AdminStats | null = null;

	$: if ($isAuthenticated && $user && !$user.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	onMount(async () => {
		try {
			stats = await getAdminStats();
		} catch {
			// Non-fatal — sub-nav still renders without counts.
		}
	});

	function isActive(prefix: string): boolean {
		const path = $page.url.pathname;
		if (prefix === '/admin') return path === '/admin';
		return path === prefix || path.startsWith(prefix + '/');
	}
</script>

<div class="min-h-screen bg-base-100">
	<nav
		class="sticky top-0 z-30 bg-base-100/95 backdrop-blur border-b border-base-300/40"
		aria-label="Admin sections"
	>
		<div class="max-w-[1280px] mx-auto px-4 sm:px-6 py-2">
			<div class="flex gap-1 p-1 rounded-2xl bg-primary/[0.04] border border-primary/[0.08] overflow-x-auto">
				<a
					href="/admin"
					class="px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isActive('/admin')}
					class:from-primary-soft={isActive('/admin')}
					class:to-primary={isActive('/admin')}
					class:text-primary-content={isActive('/admin')}
					class:text-base-content={!isActive('/admin')}
					class:opacity-60={!isActive('/admin')}
				>Overview</a>
				<a
					href="/admin/users"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isActive('/admin/users')}
					class:from-primary-soft={isActive('/admin/users')}
					class:to-primary={isActive('/admin/users')}
					class:text-primary-content={isActive('/admin/users')}
					class:text-base-content={!isActive('/admin/users')}
					class:opacity-60={!isActive('/admin/users')}
				>
					Users
					{#if stats}<span class="font-mono text-[10px] bg-base-content/10 rounded-full px-1.5 py-0.5">{stats.total_users}</span>{/if}
				</a>
				<a
					href="/admin/entries"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isActive('/admin/entries')}
					class:from-primary-soft={isActive('/admin/entries')}
					class:to-primary={isActive('/admin/entries')}
					class:text-primary-content={isActive('/admin/entries')}
					class:text-base-content={!isActive('/admin/entries')}
					class:opacity-60={!isActive('/admin/entries')}
				>Entries</a>
				<a
					href="/admin/audit"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isActive('/admin/audit')}
					class:from-primary-soft={isActive('/admin/audit')}
					class:to-primary={isActive('/admin/audit')}
					class:text-primary-content={isActive('/admin/audit')}
					class:text-base-content={!isActive('/admin/audit')}
					class:opacity-60={!isActive('/admin/audit')}
				>Audit</a>
			</div>
		</div>
	</nav>
	<slot />
</div>

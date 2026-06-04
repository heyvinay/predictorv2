<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$lib/stores/auth';
	import { getAdminStats } from '$lib/api/admin';
	import type { AdminStats } from '$lib/api/admin';
	import changelog from '$lib/data/changelog.json';
	import { onMount } from 'svelte';

	// v2.156.0 — admin layout hoists the guard from +page.svelte so
	// every /admin/* route (Users, Entries, Audit, etc.) inherits the
	// admin-only access check + persistent sub-nav.
	let stats: AdminStats | null = null;

	// Topbar: version + latest release date pulled from the bundled
	// changelog. The last entry in `entries[]` is the newest release.
	const entries = (changelog as { entries: Array<{ version: string; date: string }> }).entries;
	const latest = entries[entries.length - 1];
	const adminVersion = latest?.version ?? '';
	const adminReleaseDate = latest?.date ?? '';

	function formatLatestDate(iso: string): string {
		if (!iso) return '';
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
		}).format(d);
	}

	$: if ($isAuthenticated && $user && !$user.is_admin) goto('/');
	$: if (!$isAuthenticated) goto('/login');

	onMount(async () => {
		try {
			stats = await getAdminStats();
		} catch {
			// Non-fatal — sub-nav still renders without counts.
		}
	});

	// Reactive path + per-route active flags. Function calls inside
	// `class:` directives don't always re-evaluate when the $page store
	// updates on client-side navigation, so we explicitly derive the
	// booleans via `$:` and reference those in the template.
	$: currentPath = $page.url.pathname;
	$: isOverview = currentPath === '/admin';
	$: isUsers = currentPath === '/admin/users' || currentPath.startsWith('/admin/users/');
	$: isEntries = currentPath === '/admin/entries' || currentPath.startsWith('/admin/entries/');
	$: isAudit = currentPath === '/admin/audit' || currentPath.startsWith('/admin/audit/');
</script>

<div class="min-h-screen bg-base-100">
	<!-- Admin Console topbar (B4) — brand + version + latest release date -->
	<div class="sticky top-0 z-40 bg-base-100/95 backdrop-blur border-b border-base-300/40">
		<div class="max-w-[1280px] mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
			<div class="flex items-center gap-2.5">
				<div class="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-soft via-primary to-primary-deep text-primary-content font-extrabold text-sm flex items-center justify-center shadow-glow-gold">
					P
				</div>
				<span class="font-display font-extrabold tracking-wider text-sm">Admin Console</span>
				<span class="text-base-content/40 font-mono text-xs">
					v{adminVersion}
					{#if adminReleaseDate}<span class="text-base-content/20 mx-1">·</span>{formatLatestDate(adminReleaseDate)}{/if}
				</span>
			</div>
			{#if $user}
				<div class="flex items-center gap-2 text-base-content/60 text-xs">
					<div class="w-6 h-6 rounded-full bg-gradient-to-br from-primary-soft via-primary to-primary-deep text-primary-content font-bold text-[10px] flex items-center justify-center">
						{($user.name ?? $user.email).slice(0, 2).toUpperCase()}
					</div>
					<span>{$user.name ?? $user.email} · admin</span>
				</div>
			{/if}
		</div>
	</div>

	<nav
		class="sticky top-[52px] z-30 bg-base-100/95 backdrop-blur border-b border-base-300/40"
		aria-label="Admin sections"
	>
		<div class="max-w-[1280px] mx-auto px-4 sm:px-6 py-2">
			<div class="flex gap-1 p-1 rounded-2xl bg-primary/[0.04] border border-primary/[0.08] overflow-x-auto">
				<a
					href="/admin"
					class="px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isOverview}
					class:from-primary-soft={isOverview}
					class:to-primary={isOverview}
					class:text-primary-content={isOverview}
					class:text-base-content={!isOverview}
					class:opacity-60={!isOverview}
				>Overview</a>
				<a
					href="/admin/users"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isUsers}
					class:from-primary-soft={isUsers}
					class:to-primary={isUsers}
					class:text-primary-content={isUsers}
					class:text-base-content={!isUsers}
					class:opacity-60={!isUsers}
				>
					Users
					{#if stats}<span class="font-mono text-[10px] bg-base-content/10 rounded-full px-1.5 py-0.5">{stats.total_users}</span>{/if}
				</a>
				<a
					href="/admin/entries"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isEntries}
					class:from-primary-soft={isEntries}
					class:to-primary={isEntries}
					class:text-primary-content={isEntries}
					class:text-base-content={!isEntries}
					class:opacity-60={!isEntries}
				>Entries</a>
				<a
					href="/admin/audit"
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
					class:bg-gradient-to-b={isAudit}
					class:from-primary-soft={isAudit}
					class:to-primary={isAudit}
					class:text-primary-content={isAudit}
					class:text-base-content={!isAudit}
					class:opacity-60={!isAudit}
				>Audit</a>
			</div>
		</div>
	</nav>
	<slot />
</div>

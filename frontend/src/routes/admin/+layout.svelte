<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$lib/stores/auth';
	import { getAdminStats } from '$lib/api/admin';
	import type { AdminStats } from '$lib/api/admin';
	import changelog from '$lib/data/changelog.json';
	import { pageTitle } from '$lib/stores/pageTitle';
	import { onDestroy, onMount } from 'svelte';

	// v2.156.0 — admin layout hoists the guard from +page.svelte so
	// every /admin/* route (Users, Entries, Audit, etc.) inherits the
	// admin-only access check + persistent sub-nav.
	//
	// v2.160.0 — sub-nav grew from 4 to 7 tabs (added Sync, Bonus, Notes).
	// Mobile breakpoints get a scrollable-pills variant; desktop keeps the
	// original tab strip. See memory feedback_scrollable_pills_mobile_subnav.md.
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

	// Push the "Admin Console" title (with version) to the global top
	// nav via the pageTitle store. The root +layout.svelte renders
	// $pageTitle in its h1, so this replaces the default "The Predictor"
	// branding while inside /admin/*. Clear on unmount so other routes
	// get their own title back.
	onMount(() => {
		const titleSuffix = adminVersion ? ` v${adminVersion}` : '';
		const dateSuffix = adminReleaseDate ? ` · ${formatLatestDate(adminReleaseDate)}` : '';
		pageTitle.set(`Admin Console${titleSuffix}${dateSuffix}`);
	});

	onDestroy(() => {
		pageTitle.set('');
	});

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
	$: isSync = currentPath === '/admin/sync' || currentPath.startsWith('/admin/sync/');
	$: isBonus = currentPath === '/admin/bonus' || currentPath.startsWith('/admin/bonus/');
	$: isAudit = currentPath === '/admin/audit' || currentPath.startsWith('/admin/audit/');
	$: isUsage = currentPath === '/admin/usage' || currentPath.startsWith('/admin/usage/');
	$: isReleases = currentPath === '/admin/releases' || currentPath.startsWith('/admin/releases/');
	$: isAnnouncements =
		currentPath === '/admin/announcements' || currentPath.startsWith('/admin/announcements/');

	// Single source of truth for the 8 tabs — desktop strip + mobile
	// pills both render from this list.
	$: navItems = [
		{ href: '/admin', label: 'Overview', active: isOverview, badge: null as number | null },
		{
			href: '/admin/users',
			label: 'Users',
			active: isUsers,
			badge: stats?.total_users ?? null
		},
		{ href: '/admin/entries', label: 'Entries', active: isEntries, badge: null },
		{ href: '/admin/sync', label: 'Sync', active: isSync, badge: null },
		{ href: '/admin/bonus', label: 'Bonus', active: isBonus, badge: null },
		{ href: '/admin/audit', label: 'Audit', active: isAudit, badge: null },
		{ href: '/admin/usage', label: 'Usage', active: isUsage, badge: null },
		{ href: '/admin/announcements', label: 'News', active: isAnnouncements, badge: null },
		{ href: '/admin/releases', label: 'Notes', active: isReleases, badge: null }
	];
</script>

<div class="min-h-screen bg-base-100">
	<!--
		Topbar removed earlier (B4). Page title + version flows via the
		pageTitle store to the global top nav.
	-->
	<nav
		class="sticky top-0 z-30 bg-base-100/95 backdrop-blur border-b border-base-300/40"
		aria-label="Admin sections"
	>
		<!-- Desktop tab strip (md+): preserves the v2.156.0 styling. -->
		<div class="hidden md:block max-w-[1280px] mx-auto px-4 sm:px-6 py-2">
			<div class="flex gap-1 p-1 rounded-2xl bg-primary/[0.04] border border-primary/[0.08] overflow-x-auto">
				{#each navItems as item}
					<a
						href={item.href}
						class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all"
						class:bg-gradient-to-b={item.active}
						class:from-primary-soft={item.active}
						class:to-primary={item.active}
						class:text-primary-content={item.active}
						class:text-base-content={!item.active}
						class:opacity-60={!item.active}
					>
						{item.label}
						{#if item.badge !== null}
							<span class="font-mono text-[10px] bg-base-content/10 rounded-full px-1.5 py-0.5">
								{item.badge}
							</span>
						{/if}
					</a>
				{/each}
			</div>
		</div>

		<!--
			Mobile pills (sub-md): scrollable pills with snap. Active pill
			gets a subtle gold accent (bg-primary/15) — NOT btn-primary,
			which we reserve for actual primary actions. See memory
			feedback_scrollable_pills_mobile_subnav.md.

			Hide the scrollbar so the pill row looks intentional rather
			than overflowed. Snap-mandatory pairs with snap-start on each
			pill so a swipe lands cleanly on the next tab.
		-->
		<div class="md:hidden px-3 py-2">
			<div class="admin-pills flex gap-2 overflow-x-auto snap-x snap-mandatory">
				{#each navItems as item}
					<a
						href={item.href}
						class="snap-start inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-sm font-medium whitespace-nowrap border transition-colors {item.active
							? 'bg-primary/15 text-primary border-primary/40'
							: 'bg-base-200 text-base-content/70 border-base-300/40'}"
					>
						{item.label}
						{#if item.badge !== null}
							<span class="font-mono text-[10px] bg-base-content/10 rounded-full px-1.5 py-0.5">
								{item.badge}
							</span>
						{/if}
					</a>
				{/each}
			</div>
		</div>
	</nav>
	<slot />
</div>

<style>
	/* Hide the scrollbar on the mobile pill row but keep it scrollable.
	   Designed-for-the-pattern: the pills are meant to be swiped, not
	   "this is overflowing." */
	.admin-pills {
		scrollbar-width: none;
		-ms-overflow-style: none;
	}
	.admin-pills::-webkit-scrollbar {
		display: none;
	}
</style>

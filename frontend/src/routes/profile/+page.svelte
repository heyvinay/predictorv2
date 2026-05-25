<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user, logout } from '$stores/auth';
	import { getUserStats } from '$api/auth';
	import {
		loadEntries,
		activeEntryId,
		activeEntry,
		entries,
		setActiveEntry
	} from '$stores/entries';
	import { fetchLeaderboard, myLeaderboardRows } from '$stores/leaderboard';
	import { computeDisplayStatus, type Entry, type EntryStatus } from '$lib/types/entry';
	import type { UserStats } from '$types';
	import { get } from 'svelte/store';

	$: if (!$isAuthenticated) goto('/login');

	let stats: UserStats | null = null;
	let statsLoading = true;
	let statsError: string | null = null;


	onMount(async () => {
		if ($isAuthenticated) {
			// The leaderboard fetch doesn't need $user. Entry loading + stats
			// are handled by the reactive block below — needed because
			// initAuth()/fetchUser() can race with this onMount.
			await fetchLeaderboard();
		}
	});

	// Hydrate entries + stats as soon as $user.id resolves.
	let profileLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !profileLoadStarted) {
		profileLoadStarted = true;
		void (async () => {
			await loadEntries($user!.id);
			await loadStats();
		})();
	}

	function entryDisplayStatus(e: Entry): EntryStatus {
		// Phase 1 is the default lens for profile cards — admin still gets
		// the disabled/withdrawn precedence baked into computeDisplayStatus.
		return computeDisplayStatus(e, 'phase_1');
	}

	function statusBadgeClass(s: EntryStatus): string {
		switch (s) {
			case 'submitted':
				return 'badge-success';
			case 'withdrawn':
				return 'badge-error';
			case 'draft':
			default:
				return 'badge-ghost';
		}
	}

	function pointsForEntry(entryId: string): number | null {
		const row = $myLeaderboardRows.find((r) => r.entry_id === entryId);
		return row ? row.total_points : null;
	}

	function positionForEntry(entryId: string): number | null {
		const row = $myLeaderboardRows.find((r) => r.entry_id === entryId);
		return row ? row.position : null;
	}

	function handleSelectEntry(entry: Entry) {
		if (entry.id === $activeEntryId) return;
		setActiveEntry(entry.id);
	}

	// Re-load stats whenever the active entry changes (e.g. user switched
	// from another route). Skip the very-first run when activeEntryId is
	// still null — onMount handles that case.
	let lastEntryForStats: string | null = null;
	$: if ($activeEntryId && $activeEntryId !== lastEntryForStats) {
		lastEntryForStats = $activeEntryId;
		void loadStats();
	}

	async function loadStats() {
		statsLoading = true;
		statsError = null;
		try {
			stats = await getUserStats(get(activeEntryId));
		} catch (e) {
			statsError = e instanceof Error ? e.message : 'Failed to load stats';
		} finally {
			statsLoading = false;
		}
	}

	function fmtDate(s: string): string {
		return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
	}
</script>

<svelte:head>
	<title>Profile - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && $user}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="mb-8 flex items-center gap-4">
			<div class="w-14 h-14 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20">
				<span class="text-2xl font-bold text-white leading-none translate-y-0.5">
					{($user.name?.[0] ?? '?').toUpperCase()}
				</span>
			</div>
			<div>
				<h1 class="text-3xl sm:text-4xl font-display tracking-wide">{$user.name}</h1>
				<p class="text-sm text-base-content/50">
					{$user.email} · member since {fmtDate($user.created_at)}
				</p>
			</div>
		</div>

		<div class="space-y-8">
			<!-- Prediction stats (active entry) -->
			<div class="stadium-card no-glow p-6">
				<div class="flex items-center justify-between mb-6 flex-wrap gap-2">
					<div>
						<h2 class="text-lg font-display tracking-wide">Prediction Stats</h2>
						<p class="text-xs text-base-content/50">
							{#if $activeEntry}{$activeEntry.display_name} · {$activeEntry.reference}{:else}Your performance overview{/if}
						</p>
					</div>
					{#if stats?.leaderboard_position}
						<span class="badge badge-primary badge-lg gap-1">
							#{stats.leaderboard_position} of {stats.total_participants}
						</span>
					{/if}
				</div>

				{#if statsLoading}
					<div class="flex justify-center py-8">
						<span class="loading loading-spinner loading-lg text-primary"></span>
					</div>
				{:else if statsError}
					<div class="alert alert-error">
						<span>{statsError}</span>
						<button class="btn btn-sm btn-ghost" on:click={loadStats}>Retry</button>
					</div>
				{:else if stats}
					<div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
						<div class="stat-card">
							<p class="stat-title">{$activeEntry ? 'Entry Points' : 'Total Points'}</p>
							<p class="stat-value">{stats.total_points}</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Predictions</p>
							<p class="stat-value">{stats.total_predictions}</p>
							<p class="text-xs text-base-content/40 mt-1">
								{stats.total_match_predictions} match, {stats.total_team_predictions} team
							</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Accuracy</p>
							<p class="stat-value">{stats.accuracy_pct}%</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Exact Scores</p>
							<p class="stat-value text-primary">{stats.exact_scores}</p>
							<p class="text-xs text-base-content/40 mt-1">+{stats.exact_scores * 10} pts</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Correct Outcomes</p>
							<p class="stat-value text-success">{stats.correct_outcomes}</p>
						</div>
						<div class="stat-card">
							<p class="stat-title">Bonus Haul</p>
							<p class="stat-value text-accent">{stats.breakdown.hybrid_bonus_points}</p>
						</div>
					</div>
				{/if}
			</div><!-- /stats stadium-card -->

			<!-- Your entries -->
			{#if $entries.length > 0}
				<div class="stadium-card no-glow p-6">
					<div class="flex items-center justify-between mb-4">
						<h2 class="text-lg font-display tracking-wide">Your Entries</h2>
						<span class="text-xs text-base-content/50">{$entries.length} total</span>
					</div>
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
						{#each $entries as e (e.id)}
							{@const status = entryDisplayStatus(e)}
							{@const pts = pointsForEntry(e.id)}
							{@const pos = positionForEntry(e.id)}
							{@const isActive = e.id === $activeEntryId}
							<button
								type="button"
								class="text-left rounded-xl border p-4 transition-all
									{isActive
										? 'bg-primary/10 border-primary/40 shadow-glow-green'
										: 'bg-base-300/30 border-base-300/50 hover:border-base-content/20'}
									{e.is_disabled || e.withdrawn_at ? 'opacity-60' : ''}"
								on:click={() => handleSelectEntry(e)}
								title={isActive ? 'Active entry' : 'Set as active entry'}
							>
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0">
										<div class="font-semibold flex items-center gap-2">
											<span class="truncate">{e.display_name}</span>
											{#if isActive}<span class="badge badge-primary badge-xs">Active</span>{/if}
										</div>
										<div class="text-xs text-base-content/50 font-mono mt-0.5">{e.reference}</div>
									</div>
									<div class="text-right shrink-0">
										{#if pts !== null}
											<div class="font-display text-2xl tracking-wide leading-none">{pts}</div>
											<div class="text-[10px] text-base-content/40 uppercase tracking-wider">pts{#if pos !== null} · #{pos}{/if}</div>
										{:else}
											<div class="font-display text-2xl tracking-wide leading-none text-base-content/30">—</div>
											<div class="text-[10px] text-base-content/40 uppercase tracking-wider">not ranked</div>
										{/if}
									</div>
								</div>
								<div class="flex items-center gap-1.5 mt-3">
									<span class="badge badge-sm {statusBadgeClass(status)}">{status.toUpperCase()}</span>
									<span class="badge badge-sm {e.paid ? 'badge-success' : 'badge-ghost'}">{e.paid ? 'Paid' : 'Unpaid'}</span>
								</div>
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Account information -->
			<div class="stadium-card no-glow p-6">
				<h2 class="text-lg font-display tracking-wide mb-6">Account Information</h2>
				<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
					<div>
						<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Name</p>
						<p class="font-medium">{$user.name}</p>
					</div>
					<div>
						<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Email</p>
						<p class="font-medium lowercase">{$user.email}</p>
					</div>
					<div>
						<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Auth</p>
						<span class="badge badge-sm {$user.auth_provider === 'google' ? 'badge-info' : 'badge-ghost'}">
							{$user.auth_provider === 'google' ? 'Google' : 'Email'}
						</span>
					</div>
					<div>
						<p class="text-xs text-base-content/50 uppercase tracking-wider mb-1">Member Since</p>
						<p class="text-sm">{fmtDate($user.created_at)}</p>
					</div>
				</div>
			</div>

			<!-- Sign-in method (replaces the legacy password card now that
			     the project uses magic-link auth). -->
			<div class="stadium-card no-glow p-6">
				<h2 class="text-lg font-display tracking-wide mb-6">Sign-in method</h2>
				{#if $user.auth_provider === 'google'}
					<div class="p-4 rounded-xl bg-info/10 border border-info/20">
						<p class="text-sm font-medium text-info">Google Account</p>
						<p class="text-xs text-base-content/60 mt-1">
							You sign in with Google. Manage your account via your Google settings.
						</p>
					</div>
				{:else}
					<div class="p-4 rounded-xl bg-primary/10 border border-primary/20">
						<p class="text-sm font-medium text-primary">★ Passwordless</p>
						<p class="text-xs text-base-content/60 mt-1">
							You sign in via a magic link sent to your email — no password needed.
						</p>
					</div>
				{/if}
			</div>

			<!-- Logout -->
			<div class="flex justify-center pt-4">
				<button class="btn btn-outline btn-error" on:click={logout}>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
					</svg>
					Sign Out
				</button>
			</div>
		</div><!-- /space-y-8 -->
	</div><!-- /container -->
{/if}

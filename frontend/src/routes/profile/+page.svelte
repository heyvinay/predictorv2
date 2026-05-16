<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user, logout } from '$stores/auth';
	import { getUserStats, changePassword } from '$api/auth';
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
	import PnPageShell from '$components/panini/PnPageShell.svelte';

	$: if (!$isAuthenticated) goto('/login');

	let stats: UserStats | null = null;
	let statsLoading = true;
	let statsError: string | null = null;

	let currentPassword = '';
	let newPassword = '';
	let confirmPassword = '';
	let passwordChanging = false;
	let passwordError: string | null = null;
	let passwordSuccess: string | null = null;

	onMount(async () => {
		if ($isAuthenticated && $user) {
			// Resolve the active entry before pulling stats — they're scoped
			// to one entry now. The backend falls back to the user's primary
			// eligible entry if we pass null, so this is best-effort.
			const tasks: Promise<unknown>[] = [];
			if ($user.competition_id) {
				tasks.push(loadEntries($user.id, $user.competition_id));
			}
			// Fetch the leaderboard so the entries-list can show per-entry
			// total_points without N+1 breakdown calls. Pre-lock returns
			// only the user's own rows, which is exactly what we want here.
			tasks.push(fetchLeaderboard());
			await Promise.all(tasks);
			await loadStats();
		}
	});

	function entryDisplayStatus(e: Entry): EntryStatus {
		// Phase 1 is the default lens for profile cards — admin still gets
		// the disabled/withdrawn precedence baked into computeDisplayStatus.
		return computeDisplayStatus(e, 'phase_1');
	}

	function statusChipClass(s: EntryStatus): string {
		switch (s) {
			case 'submitted':
			case 'locked':
				return 'pn-tag got';
			case 'ready':
				return 'pn-tag gold';
			case 'disabled':
				return 'pn-tag red';
			case 'withdrawn':
				return 'pn-tag';
			default:
				return 'pn-tag';
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

	async function handleChangePassword() {
		passwordError = null;
		passwordSuccess = null;
		if (!currentPassword || !newPassword || !confirmPassword) {
			passwordError = 'All fields are required';
			return;
		}
		if (newPassword.length < 8) {
			passwordError = 'New password must be at least 8 characters';
			return;
		}
		if (newPassword !== confirmPassword) {
			passwordError = 'New passwords do not match';
			return;
		}
		passwordChanging = true;
		try {
			const r = await changePassword({ current_password: currentPassword, new_password: newPassword });
			passwordSuccess = r.message;
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (e) {
			passwordError = e instanceof Error ? e.message : 'Failed to change password';
		} finally {
			passwordChanging = false;
		}
	}

	function fmtDate(s: string): string {
		return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
	}

	function ordinal(n: number): string {
		if (n % 100 >= 11 && n % 100 <= 13) return 'th';
		switch (n % 10) {
			case 1: return 'st';
			case 2: return 'nd';
			case 3: return 'rd';
			default: return 'th';
		}
	}
</script>

<svelte:head>
	<title>Profile — Predictor</title>
</svelte:head>

{#if $isAuthenticated && $user}
	<PnPageShell>
		<!-- Hero -->
		<section class="pn-pf-hero">
			<div class="av">{($user.name?.[0] ?? '?').toUpperCase()}</div>
			<div class="nm-block">
				<div class="nm">{$user.name}</div>
				<div class="sub">
					<b>@{$user.email}</b> · member since {fmtDate($user.created_at)}
				</div>
				<div class="badges">
					<span class="pn-tag {$user.auth_provider === 'google' ? 'gold' : ''}">{$user.auth_provider === 'google' ? 'Google' : 'Email'}</span>
					{#if $user.is_admin}<span class="pn-tag red">Admin</span>{/if}
					<span class="pn-tag {$user.is_active ? 'got' : ''}">{$user.is_active ? 'Active' : 'Inactive'}</span>
				</div>
			</div>
			<div class="rank-block">
				<div class="l">Leaderboard</div>
				<div class="v">
					{#if stats?.leaderboard_position}
						{stats.leaderboard_position}<span class="sx">{ordinal(stats.leaderboard_position)}</span>
					{:else}
						—
					{/if}
				</div>
				<div class="of">{#if stats}of {stats.total_participants}{/if}</div>
			</div>
		</section>

		{#if statsError}
			<div class="pn-pf-alert error" style="margin-bottom: 22px;">{statsError} · <button class="pn-btn ghost" style="padding: 4px 10px; font-size: 11px;" on:click={loadStats}>Retry</button></div>
		{:else if statsLoading}
			<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 22px;">Loading stats…</p>
		{:else if stats}
			<section class="pn-pf-stats">
				<div class="pn-pf-stat">
					<div class="l">{$activeEntry ? `${$activeEntry.display_name} · points` : 'Total points'}</div>
					<div class="v">{stats.total_points}</div>
					{#if $activeEntry}
						<div class="sub">Entry {$activeEntry.reference}</div>
					{/if}
				</div>
				<div class="pn-pf-stat">
					<div class="l">Predictions</div>
					<div class="v">{stats.total_predictions}</div>
					<div class="sub">{stats.total_match_predictions} match · {stats.total_team_predictions} team</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Accuracy</div>
					<div class="v">{stats.accuracy_pct}%</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Exact scores</div>
					<div class="v exact">{stats.exact_scores}</div>
					<div class="sub">+{stats.exact_scores * 10} pts</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Correct outcomes</div>
					<div class="v">{stats.correct_outcomes}</div>
				</div>
				<div class="pn-pf-stat">
					<div class="l">Bonus haul</div>
					<div class="v bonus">{stats.breakdown.hybrid_bonus_points}</div>
				</div>
			</section>
		{/if}

		<!-- F.3: All entries for this user -->
		{#if $entries.length > 0}
			<section class="pn-pf-section">
				<div class="h">
					<span>Your entries</span>
					<span class="right">{$entries.length} of {$entries.length > 0 ? $entries.length : 0}</span>
				</div>
				<div class="body">
					<div class="pn-pf-entries">
						{#each $entries as e (e.id)}
							{@const status = entryDisplayStatus(e)}
							{@const pts = pointsForEntry(e.id)}
							{@const pos = positionForEntry(e.id)}
							{@const isActive = e.id === $activeEntryId}
							<button
								type="button"
								class="pn-pf-entry"
								class:active={isActive}
								class:disabled={e.is_disabled}
								class:withdrawn={!!e.withdrawn_at}
								on:click={() => handleSelectEntry(e)}
								title={isActive ? 'Active entry' : 'Set as active entry'}
							>
								<div class="who">
									<div class="nm">
										{e.display_name}
										{#if isActive}<span class="pn-tag gold">Active</span>{/if}
									</div>
									<div class="em">{e.reference}</div>
								</div>
								<div class="badges">
									<span class={statusChipClass(status)}>{status.toUpperCase()}</span>
									{#if e.paid}<span class="pn-tag got">Paid</span>{:else}<span class="pn-tag">Unpaid</span>{/if}
								</div>
								<div class="stat">
									{#if pts !== null}
										<div class="pts">{pts}</div>
										<div class="lbl">pts{#if pos !== null} · #{pos}{/if}</div>
									{:else}
										<div class="pts">—</div>
										<div class="lbl">not ranked</div>
									{/if}
								</div>
							</button>
						{/each}
					</div>
				</div>
			</section>
		{/if}

		<!-- Account info section -->
		<section class="pn-pf-section">
			<div class="h"><span>Account Information</span><span class="right">Read-only</span></div>
			<div class="body">
				<div class="pn-pf-info">
					<div class="item"><div class="l">Name</div><div class="v">{$user.name}</div></div>
					<div class="item"><div class="l">Email</div><div class="v lower">{$user.email}</div></div>
					<div class="item"><div class="l">Auth</div><div class="v">{$user.auth_provider === 'google' ? 'Google' : 'Email'}</div></div>
					<div class="item"><div class="l">Member since</div><div class="v">{fmtDate($user.created_at)}</div></div>
				</div>
			</div>
		</section>

		<!-- Password change section -->
		<section class="pn-pf-section">
			<div class="h"><span>Password</span><span class="right">Security</span></div>
			<div class="body">
				{#if $user.auth_provider === 'google'}
					<div class="pn-pf-alert">★ Your password is managed by Google. To change it, visit your Google Account settings.</div>
				{:else}
					{#if passwordError}<div class="pn-pf-alert error" style="margin-bottom: 12px;">{passwordError}</div>{/if}
					{#if passwordSuccess}<div class="pn-pf-alert success" style="margin-bottom: 12px;">{passwordSuccess}</div>{/if}
					<div class="pn-pf-form row2">
						<div class="full">
							<label for="current-password">Current password</label>
							<input id="current-password" type="password" bind:value={currentPassword} autocomplete="current-password" />
						</div>
						<div>
							<label for="new-password">New password</label>
							<input id="new-password" type="password" bind:value={newPassword} autocomplete="new-password" minlength={8} />
						</div>
						<div>
							<label for="confirm-password">Confirm new password</label>
							<input id="confirm-password" type="password" bind:value={confirmPassword} autocomplete="new-password" />
						</div>
						<div class="full" style="margin-top: 6px;">
							<button class="pn-btn" type="button" on:click={handleChangePassword} disabled={passwordChanging}>
								{passwordChanging ? 'Updating…' : 'Update password'}
							</button>
						</div>
					</div>
				{/if}
			</div>
		</section>

		<!-- Logout -->
		<div style="display: flex; justify-content: center; padding-top: 6px; margin-bottom: 22px;">
			<button class="pn-btn navy" type="button" on:click={logout}>Sign out</button>
		</div>
	</PnPageShell>
{/if}

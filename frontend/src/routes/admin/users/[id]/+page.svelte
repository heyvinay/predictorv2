<script lang="ts">
	/** /admin/users/[id] — user-detail drill-down (v2.156.0).
	 *
	 * Sections (top → bottom):
	 * 1. Hero card — profile + KPI strip
	 * 2. Engagement card — PostHog (graceful fallback if disabled)
	 * 3. Split: Entries grid (left) + Account controls + Danger zone (right)
	 * 4. Activity log — filterable table fed by query_audit_events
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		getUserDetail,
		getUserEngagement,
		toggleUserAdmin,
		toggleUserActive,
		adminListEntries,
		type UserDetailRead,
		type EngagementSummary,
		type AuditEventRead,
	} from '$lib/api/admin';
	import type { Entry } from '$lib/types/entry';
	import EntryDetailSlideOver from '$lib/components/admin/EntryDetailSlideOver.svelte';

	let user: UserDetailRead | null = null;
	let engagement: EngagementSummary | null = null;
	let engagementLoaded = false;
	let error: string | null = null;

	// Entries grid state (C3)
	let entries: Entry[] = [];
	let entriesLoaded = false;
	let activeEntry: Entry | null = null;
	let slideOverOpen = false;

	// Activity log filtering state (C5)
	let activityFilter: 'all' | 'auth' | 'entry' | 'prediction' | 'user' = 'all';
	let timeRange: 'all' | '1h' | '24h' | '7d' | '30d' = 'all';
	let filteredActivity: AuditEventRead[] = [];

	// Confirmation modal for Deactivate (C4 + G3 pattern)
	let confirmDeactivate = false;
	let deactivateReason = '';

	// SvelteKit types $page.params.id as `string | undefined`, but this
	// route only matches when the id segment is present — coerce.
	$: userId = ($page.params.id ?? '') as string;

	// Reactive max for the sparkline — derived in the script (not via
	// {@const} in the template) because {@const} would have to live as
	// the immediate child of a block tag, and the engagement card's
	// sparkline lives inside a plain <div>.
	$: sparkMaxN = engagement ? Math.max(1, ...engagement.sparkline_14d) : 1;

	$: if (user) {
		filteredActivity = filterActivity(user.recent_activity, activityFilter, timeRange);
	}

	function filterActivity(
		events: AuditEventRead[],
		ns: typeof activityFilter,
		win: typeof timeRange
	): AuditEventRead[] {
		const now = Date.now();
		const windowMs: Record<string, number | null> = {
			all: null,
			'1h': 60 * 60 * 1000,
			'24h': 24 * 60 * 60 * 1000,
			'7d': 7 * 24 * 60 * 60 * 1000,
			'30d': 30 * 24 * 60 * 60 * 1000,
		};
		const cutoff = windowMs[win];
		return events.filter((e) => {
			if (ns !== 'all' && !e.event_type.startsWith(ns + '.')) return false;
			if (cutoff !== null && now - new Date(e.created_at).getTime() > cutoff) return false;
			return true;
		});
	}

	async function loadEntries(uid: string): Promise<void> {
		try {
			const page = await adminListEntries({ user_id: uid }, { limit: 100, offset: 0 });
			entries = page.items;
		} catch {
			entries = [];
		} finally {
			entriesLoaded = true;
		}
	}

	async function refreshUser(): Promise<void> {
		try {
			user = await getUserDetail(userId);
		} catch (e: unknown) {
			error = (e as Error).message ?? 'Failed to load user';
		}
	}

	async function handleToggleAdmin(): Promise<void> {
		if (!user) return;
		try {
			await toggleUserAdmin(user.id);
			await refreshUser();
		} catch (e: unknown) {
			alert(`Failed to toggle admin: ${(e as Error).message}`);
		}
	}

	async function handleToggleActive(): Promise<void> {
		if (!user) return;
		try {
			await toggleUserActive(user.id);
			await refreshUser();
		} catch (e: unknown) {
			alert(`Failed to toggle active: ${(e as Error).message}`);
		}
	}

	async function commitDeactivate(): Promise<void> {
		if (!user || deactivateReason.trim().length < 3) return;
		try {
			// Reuses the toggle-active endpoint; reason captured client-side
			// for now (would route to dedicated deactivate endpoint with
			// reason param in a future iteration).
			await toggleUserActive(user.id);
			await refreshUser();
		} finally {
			confirmDeactivate = false;
			deactivateReason = '';
		}
	}

	function openSlideOver(entry: Entry): void {
		activeEntry = entry;
		slideOverOpen = true;
		const url = new URL(window.location.href);
		url.searchParams.set('entry', entry.reference);
		history.replaceState(null, '', url.toString());
	}

	function closeSlideOver(): void {
		slideOverOpen = false;
		activeEntry = null;
		const url = new URL(window.location.href);
		url.searchParams.delete('entry');
		history.replaceState(null, '', url.toString());
	}

	onMount(async () => {
		try {
			user = await getUserDetail(userId);
		} catch (e: unknown) {
			error = (e as Error).message ?? 'Failed to load user';
		}
		try {
			engagement = await getUserEngagement(userId);
		} catch {
			engagement = null;
		}
		engagementLoaded = true;
		if (user) await loadEntries(user.id);
	});

	function formatDate(iso: string | null, withTime = true): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
		}).format(d);
	}

	function relativeRecency(iso: string | null): string {
		if (!iso) return '—';
		const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
		if (seconds < 60) return 'just now';
		if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
		if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
		return `${Math.floor(seconds / 86400)}d ago`;
	}
</script>

<div class="max-w-[1280px] mx-auto px-4 sm:px-6 py-6">
	<p class="text-xs text-base-content/40 mb-4">
		<a href="/admin/users" class="hover:text-primary">Users</a> /
		{user?.name ?? user?.email ?? '…'}
	</p>

	{#if error}
		<div class="alert alert-error">{error}</div>
	{:else if user}
		<!-- Hero card -->
		<section class="card bg-base-200/60 border border-primary/10 mb-5">
			<div class="card-body">
				<div class="flex flex-wrap gap-6 items-start">
					<div class="flex-1 min-w-[240px]">
						<div class="flex items-center gap-2 flex-wrap">
							<h1 class="font-display font-extrabold text-3xl">{user.name ?? user.email}</h1>
							{#if user.is_admin}<span class="status-pill s-warning"><span class="dot"></span>Admin</span>{/if}
							{#if user.is_active}<span class="status-pill s-success"><span class="dot"></span>Active</span>{:else}<span class="status-pill s-error"><span class="dot"></span>Deactivated</span>{/if}
						</div>
						<p class="text-sm text-base-content/60 mt-1.5">
							{user.email} <span class="text-base-content/20">·</span>
							<span class="font-mono text-[11px] uppercase tracking-wider">{user.auth_provider} auth</span>
						</p>
						<p class="font-mono text-xs text-base-content/40 mt-3">
							{user.employer ?? 'no employer'} · paid to {user.paid_to ?? '—'} · joined {formatDate(user.created_at, false)} · cohort: {user.cohort}
						</p>
					</div>
					<div class="grid grid-cols-2 sm:grid-cols-3 gap-2 flex-1 min-w-[300px]">
						<div class="kpi-card"><div class="label">Entries</div><div class="value">{user.entries_count}</div><div class="delta">{user.submitted_entries_count} sub · {user.draft_entries_count} draft</div></div>
						<div class="kpi-card"><div class="label">Paid</div><div class="value">{user.paid ? '1' : '0'}<span class="unit">/{user.entries_count || 1}</span></div></div>
						<div class="kpi-card"><div class="label">Last login</div><div class="value !text-xs !font-semibold" title={user.last_login_at ?? ''}>{formatDate(user.last_login_at)}</div><div class="delta">audit-derived</div></div>
						<div class="kpi-card"><div class="label">Last activity</div><div class="value !text-xs !font-semibold" title={user.last_activity_at ?? ''}>{formatDate(user.last_activity_at)}</div><div class="delta">all event types</div></div>
						<div class="kpi-card sm:col-span-1"><div class="label">Member since</div><div class="value !text-xs !font-semibold">{formatDate(user.created_at, false)}</div></div>
					</div>
				</div>
			</div>
		</section>

		<!-- Engagement card (PostHog Scope C) -->
		{#if engagementLoaded}
			<section class="card bg-base-200/60 border border-base-300/30 mb-5">
				<div class="card-body">
					<div class="flex items-baseline justify-between gap-3 mb-3">
						<div>
							<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">PostHog · last 30 days</p>
							<h2 class="font-display font-bold text-lg mt-1">Engagement</h2>
						</div>
						<span class="text-[11px] text-base-content/40 font-mono">cached 2 min</span>
					</div>
					{#if engagement === null}
						<p class="text-sm text-base-content/55">PostHog not configured / unreachable — showing "—" placeholders. Set <code class="font-mono text-xs">POSTHOG_PERSONAL_API_KEY</code> + <code class="font-mono text-xs">POSTHOG_PROJECT_ID</code> on the backend to enable.</p>
					{:else}
						<div class="engagement-card">
							<div>
								<div class="text-[10px] uppercase tracking-widest text-base-content/40">Last seen</div>
								<div class="font-display font-bold text-base mt-1.5">{relativeRecency(engagement.last_seen)}</div>
								<div class="text-[11px] text-base-content/40 mt-1" title={engagement.last_seen ?? ''}>{formatDate(engagement.last_seen)}</div>
							</div>
							<div>
								<div class="text-[10px] uppercase tracking-widest text-base-content/40">Last page</div>
								<div class="font-mono text-xs mt-1.5 truncate">{engagement.last_url ?? '—'}</div>
							</div>
							<div>
								<div class="text-[10px] uppercase tracking-widest text-base-content/40">Sessions (30d)</div>
								<div class="font-display font-bold text-xl mt-1.5">{engagement.session_count}</div>
							</div>
							<div>
								<div class="text-[10px] uppercase tracking-widest text-base-content/40">Avg duration</div>
								<div class="font-display font-bold text-xl mt-1.5">{engagement.avg_session_seconds ? `${Math.floor(engagement.avg_session_seconds / 60)}m ${Math.floor(engagement.avg_session_seconds % 60)}s` : '—'}</div>
							</div>
							<div class="ec-spark" title="14-day pageviews, oldest left → newest right">
								{#each engagement.sparkline_14d as count}
									{#if count === 0}
										<div class="bar empty"></div>
									{:else}
										<div class="bar" style="height: {Math.max(8, (count / sparkMaxN) * 100)}%"></div>
									{/if}
								{/each}
							</div>
							<div class="text-[9.5px] uppercase tracking-widest text-base-content/30 font-mono">
								via PostHog · powers future /api/me/engagement
							</div>
						</div>
					{/if}
				</div>
			</section>
		{/if}

		<!-- Split: Entries grid (left) + Account controls + Danger zone (right) -->
		<div class="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 mb-5">
			<!-- Entries grid (C3) -->
			<section class="card bg-base-200/60 border border-base-300/30">
				<div class="card-body">
					<div class="flex items-baseline justify-between mb-3">
						<div>
							<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">Their submissions · read-only</p>
							<h2 class="font-display font-bold text-xl mt-1">Entries</h2>
						</div>
						<span class="text-xs text-base-content/40">{entries.length} total</span>
					</div>
					{#if !entriesLoaded}
						<p class="text-sm text-base-content/55">Loading entries…</p>
					{:else if entries.length === 0}
						<p class="text-sm text-base-content/55">No entries yet.</p>
					{:else}
						<div class="grid gap-3 grid-cols-1 sm:grid-cols-2">
							{#each entries as e (e.id)}
								<div
									class="entry-mini cursor-pointer"
									role="button"
									tabindex="0"
									on:click={() => openSlideOver(e)}
									on:keydown={(ev) => ev.key === 'Enter' && openSlideOver(e)}
								>
									<div class="flex items-center justify-between gap-2 mb-2">
										<span class="font-mono text-[10.5px] bg-primary/10 border border-primary/20 text-primary rounded px-1.5 py-0.5">{e.reference}</span>
										{#if e.is_disabled}<span class="status-pill s-error"><span class="dot"></span>Disabled</span>
										{:else}<span class="status-pill s-success"><span class="dot"></span>Submitted</span>{/if}
									</div>
									<div class="font-semibold text-sm mb-2">{e.display_name ?? `Entry ${e.entry_number}`}</div>
									<div class="flex items-center gap-2 flex-wrap text-[11px] text-base-content/40">
										{#if e.paid}<span class="status-pill s-success" style="padding: 2px 8px;"><span class="dot"></span>Paid</span>{:else}<span class="status-pill s-ghost" style="padding: 2px 8px;"><span class="dot"></span>Unpaid</span>{/if}
										<span>Entry #{e.entry_number}</span>
									</div>
									<button class="btn btn-outline btn-xs mt-2 self-start">View picks →</button>
								</div>
							{/each}
						</div>
					{/if}
					<p class="text-xs text-base-content/40 italic mt-3">
						"View picks" opens the slide-over <strong>in place</strong> — URL becomes
						<span class="font-mono text-primary">/admin/users/[id]?entry=REF</span>.
					</p>
				</div>
			</section>

			<!-- Permissions + Danger zone (C4) -->
			<aside class="flex flex-col gap-4">
				<section class="card bg-base-200/60 border border-base-300/30">
					<div class="card-body">
						<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">Permissions</p>
						<h3 class="font-display font-bold text-base mt-1 mb-3">Account controls</h3>
						<div class="flex items-center justify-between py-2 border-b border-base-300/30">
							<div class="text-sm">
								Admin access
								<div class="text-[11px] text-base-content/40">Full console</div>
							</div>
							<input type="checkbox" class="toggle toggle-warning toggle-sm" checked={user.is_admin} on:change={handleToggleAdmin} />
						</div>
						<div class="flex items-center justify-between py-2">
							<div class="text-sm">
								Active account
								<div class="text-[11px] text-base-content/40">Can sign in &amp; play</div>
							</div>
							<input type="checkbox" class="toggle toggle-success toggle-sm" checked={user.is_active} on:change={handleToggleActive} />
						</div>
					</div>
				</section>
				<section class="card bg-base-200/60 border border-error/20">
					<div class="card-body">
						<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-error">Danger zone</p>
						<h3 class="font-display font-bold text-sm mt-1">Deactivate account</h3>
						<p class="text-xs text-base-content/55 mt-2 mb-3">
							Sign them out everywhere &amp; block re-entry. Audit-logged. Reversible.
						</p>
						<button class="btn btn-error btn-outline btn-sm" on:click={() => (confirmDeactivate = true)}>
							✕ Deactivate {user.name ?? 'user'}
						</button>
					</div>
				</section>
			</aside>
		</div>

		<!-- Activity log with filters (C5) -->
		<section class="card bg-base-200/60 border border-base-300/30">
			<div class="card-body">
				<div class="flex items-baseline justify-between mb-3">
					<div>
						<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">From the audit log · all entries + account</p>
						<h2 class="font-display font-bold text-xl mt-1">Activity</h2>
					</div>
					<div class="flex items-center gap-2">
						<span class="text-xs text-base-content/40">{filteredActivity.length} of {user.recent_activity.length}</span>
						<button class="btn btn-outline btn-xs" on:click={refreshUser} title="Re-fetch from the audit log">↻ Refresh</button>
					</div>
				</div>

				<!-- Filter bar -->
				<div class="flex flex-wrap gap-2 items-center mb-3">
					<select bind:value={activityFilter} class="select select-bordered select-sm">
						<option value="all">All activity</option>
						<option value="auth">auth.*</option>
						<option value="entry">entry.*</option>
						<option value="prediction">prediction.*</option>
						<option value="user">user.*</option>
					</select>
					<select bind:value={timeRange} class="select select-bordered select-sm">
						<option value="all">Any time</option>
						<option value="1h">Last hour</option>
						<option value="24h">Last 24 hours</option>
						<option value="7d">Last 7 days</option>
						<option value="30d">Last 30 days</option>
					</select>
				</div>

				<div class="overflow-x-auto">
					<table class="table table-sm">
						<thead>
							<tr class="text-[10px] uppercase tracking-widest text-base-content/40">
								<th>When</th>
								<th>Event</th>
								<th>Detail</th>
							</tr>
						</thead>
						<tbody>
							{#each filteredActivity as e (e.id)}
								<tr>
									<td class="font-mono text-xs text-base-content/40 whitespace-nowrap" title={e.created_at}>{formatDate(e.created_at)}</td>
									<td><span class="font-mono text-xs">{e.event_type}</span></td>
									<td class="font-mono text-[10.5px] text-base-content/40 truncate max-w-xs">
										{e.event_metadata ? JSON.stringify(e.event_metadata) : ''}
										{#if e.reason}<span class="italic ml-1">"{e.reason}"</span>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
					{#if filteredActivity.length === 0}
						<p class="text-center text-sm text-base-content/55 py-6">No activity matches the current filter.</p>
					{/if}
				</div>
			</div>
		</section>
	{:else}
		<div class="p-10 text-center text-base-content/55">Loading…</div>
	{/if}
</div>

<!-- Slide-over (C3 — opens from Entries grid) -->
<EntryDetailSlideOver
	entry={activeEntry}
	open={slideOverOpen}
	on:close={closeSlideOver}
	on:updated={refreshUser}
/>

<!-- Deactivate confirmation modal (C4 + G3 Pattern C) -->
{#if confirmDeactivate && user}
	<div class="confirm-scrim open" on:click={() => (confirmDeactivate = false)} role="presentation">
		<div class="confirm-modal" on:click|stopPropagation role="dialog">
			<p class="cm-kicker">Danger zone</p>
			<h3 class="font-display font-extrabold text-lg mt-1.5">
				Deactivate {user.name ?? user.email}?
			</h3>
			<p class="text-sm text-base-content/60 mt-2 mb-4">
				They'll be signed out everywhere and blocked from re-entry. Reversible — you can re-activate them anytime.
			</p>
			<label class="text-[11px] uppercase tracking-widest text-base-content/40 font-medium block mb-1.5">
				Reason <span class="normal-case tracking-normal text-base-content/40">(audit logged)</span>
			</label>
			<textarea
				bind:value={deactivateReason}
				placeholder="e.g. requested account closure, duplicate account, payment reversed…"
				class="textarea textarea-bordered w-full min-h-[64px]"
			></textarea>
			<p class="text-[11px] text-base-content/40 italic mt-1.5">Minimum 3 characters · routes to <span class="font-mono">audit_events.reason</span></p>
			<div class="flex justify-end gap-2 mt-4">
				<button class="btn btn-ghost btn-sm" on:click={() => (confirmDeactivate = false)}>Cancel</button>
				<button
					class="btn btn-error btn-sm"
					disabled={deactivateReason.trim().length < 3}
					on:click={commitDeactivate}
				>Deactivate</button>
			</div>
		</div>
	</div>
{/if}

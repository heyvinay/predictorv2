<script lang="ts">
	/** /admin/users/[id] — user-detail drill-down (v2.156.0). */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		getUserDetail,
		getUserEngagement,
		type UserDetailRead,
		type EngagementSummary,
	} from '$lib/api/admin';

	let user: UserDetailRead | null = null;
	let engagement: EngagementSummary | null = null;
	let engagementLoaded = false;
	let error: string | null = null;

	$: userId = $page.params.id;

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
					<div class="avatar avatar-placeholder">
						<div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-soft via-primary to-primary-deep text-primary-content font-extrabold text-3xl">
							{(user.name ?? user.email).slice(0, 2).toUpperCase()}
						</div>
					</div>
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
						<div class="kpi-card"><div class="label">Last login</div><div class="value text-base" title={user.last_login_at ?? ''}>{formatDate(user.last_login_at)}</div><div class="delta">audit-derived</div></div>
						<div class="kpi-card"><div class="label">Last activity</div><div class="value text-base" title={user.last_activity_at ?? ''}>{formatDate(user.last_activity_at)}</div><div class="delta">all event types</div></div>
						<div class="kpi-card sm:col-span-1"><div class="label">Member since</div><div class="value text-base">{formatDate(user.created_at, false)}</div></div>
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
									{@const maxN = Math.max(1, ...engagement.sparkline_14d)}
									{@const pct = Math.max(8, (count / maxN) * 100)}
									{#if count === 0}
										<div class="bar empty"></div>
									{:else}
										<div class="bar" style="height: {pct}%"></div>
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

		<!-- Activity log -->
		<section class="card bg-base-200/60 border border-base-300/30">
			<div class="card-body">
				<div class="flex items-baseline justify-between mb-3">
					<div>
						<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">From the audit log · all entries + account</p>
						<h2 class="font-display font-bold text-xl mt-1">Activity</h2>
					</div>
					<span class="text-xs text-base-content/40">{user.recent_activity.length} most recent events</span>
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
							{#each user.recent_activity as e (e.id)}
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
				</div>
			</div>
		</section>
	{:else}
		<div class="p-10 text-center text-base-content/55">Loading…</div>
	{/if}
</div>

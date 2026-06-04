<script lang="ts">
	/**
	 * /admin/users — v2.156.0 cohort-aware roster.
	 *
	 * Three cohort chips (Active / Signed-up-only / Verified-only) plus
	 * the routine filter set (All / Admins / Paid / Unpaid). Click any
	 * stat card to drill into that cohort + smooth-scroll to the table.
	 * "Email Inactive" downloads a CSV of cohorts 1 + 2 for re-engagement.
	 */
	import { onMount, tick } from 'svelte';
	import {
		listUsersV2,
		downloadInactiveEmailsUrl,
		type UserAdminPage,
		type UserAdminRowV2,
		type UserCohort,
	} from '$lib/api/admin';

	const COHORT_OPTIONS: UserCohort[] = [
		'active', 'all', 'admins', 'paid', 'unpaid', 'signed_up_only', 'verified_only',
	];

	let page: UserAdminPage = { rows: [], total: 0 };
	let cohort: UserCohort = 'active';
	let search = '';
	let loading = false;
	let tableEl: HTMLDivElement | null = null;
	let stats = {
		active: 0,
		paid: 0,
		admins: 0,
		signed_up_only: 0,
		verified_only: 0,
	};

	async function refresh(): Promise<void> {
		loading = true;
		try {
			page = await listUsersV2({ cohort, search: search || undefined, limit: 100 });
		} finally {
			loading = false;
		}
	}

	async function refreshStats(): Promise<void> {
		// Quick counts via separate calls. Could be a single endpoint
		// but for v2.156.0 we wire it as 5 cheap queries.
		const [a, p, ad, s1, s2] = await Promise.all([
			listUsersV2({ cohort: 'active', limit: 1 }),
			listUsersV2({ cohort: 'paid', limit: 1 }),
			listUsersV2({ cohort: 'admins', limit: 1 }),
			listUsersV2({ cohort: 'signed_up_only', limit: 1 }),
			listUsersV2({ cohort: 'verified_only', limit: 1 }),
		]);
		stats = {
			active: a.total,
			paid: p.total,
			admins: ad.total,
			signed_up_only: s1.total,
			verified_only: s2.total,
		};
	}

	async function setCohort(c: UserCohort): Promise<void> {
		cohort = c;
		await refresh();
		await tick();
		tableEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit',
		}).format(d);
	}

	function daysAgo(iso: string | null): string {
		if (!iso) return '';
		const diff = Date.now() - new Date(iso).getTime();
		const d = Math.floor(diff / (1000 * 60 * 60 * 24));
		return d === 0 ? '(0d)' : `(${d}d)`;
	}

	onMount(async () => {
		await Promise.all([refresh(), refreshStats()]);
	});
</script>

<div class="max-w-[1380px] mx-auto px-4 sm:px-6 py-6">
	<header class="flex flex-wrap items-end justify-between gap-4 mb-5">
		<div>
			<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary font-medium">
				Member roster · three-cohort filtering
			</p>
			<h1 class="font-display font-extrabold text-3xl sm:text-4xl mt-2">Users</h1>
			<p class="text-base-content/60 text-sm mt-2 max-w-2xl">
				People who signed up. Click a row to drill into entries + activity.
				The two <em>Inactive</em> cohorts are hidden from <em>Active</em> by default;
				export their emails to send a re-engagement mailshot.
			</p>
		</div>
		<div class="flex gap-2 flex-wrap">
			<a
				href={downloadInactiveEmailsUrl('both')}
				class="btn btn-outline btn-sm"
				title="CSV of just the two inactive cohorts, for a re-engagement mailshot"
			>
				Email Inactive ({stats.signed_up_only + stats.verified_only})
			</a>
		</div>
	</header>

	<!-- Stat strip (clickable) -->
	<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 border border-base-300/30 rounded-2xl overflow-hidden mb-4">
		<button on:click={() => setCohort('active')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Active members</div>
			<div class="value">{stats.active}</div>
			<div class="delta">joined the pool</div>
		</button>
		<button on:click={() => setCohort('paid')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Paid</div>
			<div class="value">{stats.paid}<span class="unit">/{stats.active}</span></div>
			<div class="delta">payment status</div>
		</button>
		<button on:click={() => setCohort('admins')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Admins</div>
			<div class="value">{stats.admins}</div>
			<div class="delta">incl. you</div>
		</button>
		<button on:click={() => setCohort('signed_up_only')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Inactive (cohort 1)</div>
			<div class="value">{stats.signed_up_only}</div>
			<div class="delta">signed up · no magic-link click</div>
		</button>
		<button on:click={() => setCohort('verified_only')} class="kpi-card is-clickable text-left border-b border-base-300/30 rounded-none">
			<div class="label">Inactive (cohort 2)</div>
			<div class="value">{stats.verified_only}</div>
			<div class="delta">verified · no onboarding</div>
		</button>
	</div>

	<!-- Filter bar -->
	<div class="flex flex-wrap gap-2 items-center mb-3">
		<div class="relative flex-1 min-w-[240px] max-w-[360px]">
			<input
				type="search"
				bind:value={search}
				on:input={() => { refresh(); }}
				placeholder="Search by name or email"
				class="input input-bordered input-sm w-full"
			/>
		</div>
		<div class="flex gap-1.5 flex-wrap">
			{#each COHORT_OPTIONS as c}
				<button
					class="badge badge-sm gap-1.5 px-3 py-3 cursor-pointer transition-colors"
					class:badge-primary={cohort === c}
					class:badge-outline={cohort !== c}
					on:click={() => setCohort(c)}
				>
					{c === 'signed_up_only' ? 'Signed up only' : c === 'verified_only' ? 'Verified only' : c[0].toUpperCase() + c.slice(1)}
				</button>
			{/each}
		</div>
	</div>

	<!-- Users table -->
	<div bind:this={tableEl} class="rounded-2xl border border-base-300/30 bg-base-200/40 overflow-hidden scroll-mt-24">
		{#if loading && page.rows.length === 0}
			<div class="p-10 text-center text-base-content/55">Loading…</div>
		{:else if page.rows.length === 0}
			<div class="p-10 text-center text-base-content/55">No users match the current filter.</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="table table-sm">
					<thead>
						<tr class="text-[10px] uppercase tracking-widest text-base-content/40">
							<th>Member</th>
							<th>Status</th>
							<th>Entries</th>
							<th>Works at</th>
							<th>Atlas/JMFA contact</th>
							<th>Paid to</th>
							<th title="MAX(audit_events.created_at) across ALL event types">Last activity</th>
							<th>Joined</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each page.rows as u (u.id)}
							<tr
								class="cursor-pointer hover:bg-primary/[0.04] transition-colors"
								on:click={() => location.assign(`/admin/users/${u.id}`)}
							>
								<td>
									<div class="min-w-0">
										<div class="font-medium truncate">{u.name ?? u.email}</div>
										<div class="text-[11px] text-base-content/40 truncate">{u.email} · {u.auth_provider}</div>
									</div>
								</td>
								<td>
									<div class="flex flex-wrap gap-1">
										{#if u.is_admin}<span class="status-pill s-warning"><span class="dot"></span>Admin</span>{/if}
										{#if u.paid}<span class="status-pill s-success"><span class="dot"></span>Paid</span>{:else if u.cohort === 'active'}<span class="status-pill s-ghost"><span class="dot"></span>Unpaid</span>{/if}
										{#if u.cohort === 'signed_up_only'}<span class="status-pill s-warning"><span class="dot"></span>Signed up only</span>{/if}
										{#if u.cohort === 'verified_only'}<span class="status-pill s-info"><span class="dot"></span>Verified only</span>{/if}
									</div>
								</td>
								<td>
									{#if u.entries_count > 0}
										<span class="font-semibold">{u.entries_count}</span>
										<span class="text-[11px] text-base-content/40">· {u.submitted_entries_count} sub · {u.draft_entries_count} draft</span>
									{:else}
										<span class="text-base-content/40">—</span>
									{/if}
								</td>
								<td class="text-base-content/60 text-xs">{u.employer ?? '—'}</td>
								<td class="text-base-content/60 text-xs">{u.company_contact ?? '—'}</td>
								<td class="text-base-content/60 text-xs">{u.paid_to ?? '—'}</td>
								<td class="text-base-content/60 text-xs" title={u.last_activity_at ?? ''}>
									{formatDate(u.last_activity_at)} <span class="text-base-content/40">{daysAgo(u.last_activity_at)}</span>
								</td>
								<td class="text-base-content/60 text-xs" title={u.created_at}>
									{formatDate(u.created_at)}
								</td>
								<td class="text-right text-base-content/40">›</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/30 text-xs text-base-content/40">
				<span>Showing 1–{page.rows.length} of {page.total} · cohort: <span class="text-base-content/60">{cohort}</span></span>
				<span>First 100 loaded</span>
			</div>
		{/if}
	</div>
</div>

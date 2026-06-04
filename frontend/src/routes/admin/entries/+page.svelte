<script lang="ts">
	/** /admin/entries — reconciliation table (v2.156.0). */
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page as pageStore } from '$app/stores';
	import {
		adminListEntries,
		getPaidLocal,
		type AdminEntriesPage,
	} from '$lib/api/admin';
	import EntryDetailSlideOver from '$lib/components/admin/EntryDetailSlideOver.svelte';
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';

	/** True iff the entry is effectively paid.
	 *
	 *  As of v2.157.0 the admin entries response carries `owner.paid`
	 *  (the per-user payment flag) from the backend, so we prefer it.
	 *  Falls back to the legacy localStorage cache when the field is
	 *  missing (e.g. cached responses pre-rollout) — getPaidLocal will
	 *  also be retired once we're confident nothing depends on it.
	 */
	function isEffectivelyPaid(e: Entry): boolean {
		if (e.paid) return true;
		if (e.owner?.paid) return true;
		return getPaidLocal(e.user_id);
	}

	/** Derive the Prize-eligibility chip state.
	 *
	 *  - `eligible` — entry is prize_eligible, submitted, and paid.
	 *  - `pending`  — entry is prize_eligible, submitted, but unpaid.
	 *  - `excluded` — anything else (not eligible, withdrawn, disabled,
	 *                 or still draft).
	 */
	function prizeChipState(e: Entry): 'eligible' | 'pending' | 'excluded' {
		if (e.is_disabled || e.withdrawn_at) return 'excluded';
		if (!e.prize_eligible) return 'excluded';
		const isSubmitted = computeDisplayStatus(e, 'phase_1') === 'submitted';
		if (!isSubmitted) return 'excluded';
		return isEffectivelyPaid(e) ? 'eligible' : 'pending';
	}

	let listing: AdminEntriesPage = { items: [], total: 0 };
	let search = '';
	let statusFilter = '';
	// Lifecycle filter is orthogonal to status — 'disabled' (entry.is_disabled)
	// and 'withdrawn' (entry.withdrawn_at) are entry-level overlays, not
	// phase statuses. Collapsing them into the same dropdown as draft/submitted
	// was the source of the v2.156.1 "Disabled stat card 422" bug.
	let lifecycleFilter: '' | 'disabled' | 'withdrawn' = '';
	let paidFilter = '';
	let modifiedWithin = '';
	let refreshError: string | null = null;
	let tableEl: HTMLDivElement | null = null;

	// Slide-over state — entry to show + deep-link sync via ?entry=REF
	let activeEntry: Entry | null = null;
	let slideOverOpen = false;

	async function refresh(): Promise<void> {
		try {
			refreshError = null;
			// Resolve the lifecycle filter to the right backend params.
			// Lifecycle overlays take precedence over the status dropdown
			// because they're a *different* axis: disabled / withdrawn
			// entries don't have a meaningful draft/submitted state to surface.
			let effectiveStatus: string | undefined = statusFilter || undefined;
			let effectiveDisabled: boolean | undefined;
			if (lifecycleFilter === 'disabled') {
				effectiveDisabled = true;
				effectiveStatus = undefined;
			} else if (lifecycleFilter === 'withdrawn') {
				effectiveStatus = 'withdrawn'; // backend special-cases this
			}
			listing = await adminListEntries(
				{
					search: search || undefined,
					status: effectiveStatus,
					disabled: effectiveDisabled,
					paid: paidFilter ? paidFilter === 'paid' : undefined,
					modified_within: modifiedWithin || undefined,
				},
				{ limit: 100, offset: 0 }
			);
		} catch (err) {
			refreshError = err instanceof Error ? err.message : 'Failed to load entries.';
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

	function handleUpdated(e: CustomEvent<Entry>): void {
		activeEntry = e.detail;
		refresh();
	}

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit',
		}).format(d);
	}

	onMount(async () => {
		await refresh();
		// Deep-link: if ?entry=REF is present, open the slide-over.
		const ref = $pageStore.url.searchParams.get('entry');
		if (ref) {
			const match = listing.items.find((e) => e.reference === ref);
			if (match) {
				activeEntry = match;
				slideOverOpen = true;
			}
		}
	});

	async function setStatusFilter(s: string): Promise<void> {
		statusFilter = s;
		lifecycleFilter = ''; // clear overlay when selecting a phase status
		await refresh();
		await tick();
		tableEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	async function setLifecycleFilter(l: '' | 'disabled' | 'withdrawn'): Promise<void> {
		lifecycleFilter = l;
		statusFilter = ''; // clear status when filtering by lifecycle overlay
		await refresh();
		await tick();
		tableEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	async function setPaidFilter(p: string): Promise<void> {
		paidFilter = p;
		await refresh();
		await tick();
		tableEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	// Submitted = entries with phase_1 status === 'submitted' and not
	// disabled / withdrawn. Was previously `!is_disabled` which
	// conflated drafts + submitted + withdrawn into one bucket.
	$: submitted = listing.items.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			computeDisplayStatus(e, 'phase_1') === 'submitted'
	).length;
	// Paid count uses the effectively-paid check so per-user payment
	// mode is honoured (entries don't have their own paid flag set
	// in that mode).
	$: paid = listing.items.filter(isEffectivelyPaid).length;
	// Disabled + withdrawn (excluded from prize calculation either way).
	$: disabled = listing.items.filter((e) => e.is_disabled || !!e.withdrawn_at).length;
	// Draft = not disabled, not withdrawn, phase_1 not submitted yet.
	$: drafts = listing.items.filter(
		(e) =>
			!e.is_disabled &&
			!e.withdrawn_at &&
			computeDisplayStatus(e, 'phase_1') !== 'submitted'
	).length;
</script>

<div class="max-w-[1380px] mx-auto px-4 sm:px-6 py-6">
	<header class="flex flex-wrap items-end justify-between gap-4 mb-5">
		<div>
			<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary font-medium">Reconciliation · prize fund · payment audit</p>
			<h1 class="font-display font-extrabold text-3xl sm:text-4xl mt-2">Entries</h1>
			<p class="text-base-content/60 text-sm mt-2 max-w-2xl">
				Search by email, name, or reference. Click any stat card to drill in.
				Row click opens the slide-over with picks + audit log + admin actions.
			</p>
		</div>
	</header>

	<!-- Stat strip -->
	<div class="grid grid-cols-2 sm:grid-cols-4 border border-base-300/30 rounded-2xl overflow-hidden mb-4">
		<button on:click={() => { setStatusFilter(''); setLifecycleFilter(''); }} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Total entries</div>
			<div class="value">{listing.total}</div>
		</button>
		<button on:click={() => setStatusFilter('submitted')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Submitted</div>
			<div class="value">{submitted}</div>
			<div class="delta">{drafts} draft{drafts === 1 ? '' : 's'} pending</div>
		</button>
		<button on:click={() => setPaidFilter('paid')} class="kpi-card is-clickable text-left border-r border-b border-base-300/30 rounded-none">
			<div class="label">Paid</div>
			<div class="value">{paid}<span class="unit">/{submitted}</span></div>
		</button>
		<button on:click={() => setLifecycleFilter('disabled')} class="kpi-card is-clickable text-left border-b border-base-300/30 rounded-none">
			<div class="label">Disabled / withdrawn</div>
			<div class="value">{disabled}</div>
		</button>
	</div>

	{#if refreshError}
		<div role="alert" class="alert alert-error alert-soft mb-3 text-sm">
			<span>Couldn't load entries: {refreshError}</span>
			<button class="btn btn-ghost btn-xs" on:click={() => refresh()}>Retry</button>
		</div>
	{/if}

	<!-- Filter bar -->
	<div class="flex flex-wrap gap-2 items-center mb-3">
		<input
			type="search"
			bind:value={search}
			on:input={() => refresh()}
			placeholder="Search by email, name, or reference"
			class="input input-bordered input-sm max-w-xs flex-1"
		/>
		<select bind:value={statusFilter} on:change={() => setStatusFilter(statusFilter)} class="select select-bordered select-sm">
			<option value="">All status</option>
			<option value="draft">Draft</option>
			<option value="submitted">Submitted</option>
		</select>
		<select bind:value={lifecycleFilter} on:change={() => setLifecycleFilter(lifecycleFilter)} class="select select-bordered select-sm" title="Lifecycle overlay: disabled or withdrawn entries">
			<option value="">Active entries</option>
			<option value="disabled">Disabled</option>
			<option value="withdrawn">Withdrawn</option>
		</select>
		<select bind:value={paidFilter} on:change={() => refresh()} class="select select-bordered select-sm">
			<option value="">All payment</option>
			<option value="paid">Paid</option>
			<option value="unpaid">Unpaid</option>
		</select>
		<select bind:value={modifiedWithin} on:change={() => refresh()} class="select select-bordered select-sm" title="Filter by Entry.updated_at within window">
			<option value="">Modified anytime</option>
			<option value="1h">Last hour</option>
			<option value="24h">Last 24 hours</option>
			<option value="7d">Last 7 days</option>
			<option value="30d">Last 30 days</option>
		</select>
	</div>

	<!-- Entries table -->
	<div bind:this={tableEl} class="rounded-2xl border border-base-300/30 bg-base-200/40 overflow-hidden scroll-mt-24">
		{#if listing.items.length === 0}
			<div class="p-10 text-center text-base-content/55">No entries match the current filter.</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="table table-sm">
					<thead>
						<tr class="text-[10px] uppercase tracking-widest text-base-content/40">
							<th>Reference</th>
							<th>Entry</th>
							<th>Owner</th>
							<th>Status</th>
							<th>Paid</th>
							<th>Paid to</th>
							<th>Prize</th>
							<th>Modified</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each listing.items as e (e.id)}
							<tr class="cursor-pointer hover:bg-primary/[0.04]" on:click={() => openSlideOver(e)}>
								<td><span class="font-mono text-[10.5px] bg-primary/10 border border-primary/20 text-primary rounded px-1.5 py-0.5">{e.reference}</span></td>
								<td><div class="font-medium">{e.display_name ?? `Entry ${e.entry_number}`}</div></td>
								<td>
									{#if e.owner}
										<div class="text-[12.5px] font-medium leading-tight">{e.owner.name ?? '—'}</div>
										<div class="text-[11px] text-base-content/55 leading-tight">{e.owner.email}</div>
									{:else}
										<span class="text-base-content/30">—</span>
									{/if}
								</td>
								<td>
									{#if e.is_disabled}
										<span class="status-pill s-error"><span class="dot"></span>Disabled</span>
									{:else if e.withdrawn_at}
										<span class="status-pill s-warning"><span class="dot"></span>Withdrawn</span>
									{:else if computeDisplayStatus(e, 'phase_1') === 'submitted'}
										<span class="status-pill s-success"><span class="dot"></span>Submitted</span>
									{:else}
										<span class="status-pill s-ghost"><span class="dot"></span>Draft</span>
									{/if}
								</td>
								<td>{#if isEffectivelyPaid(e)}<span class="status-pill s-success"><span class="dot"></span>Paid</span>{:else}<span class="status-pill s-ghost"><span class="dot"></span>Unpaid</span>{/if}</td>
								<td class="text-[12px] text-base-content/60">
									{#if e.owner?.paid_to}{e.owner.paid_to}{:else}<span class="text-base-content/30">—</span>{/if}
								</td>
								<td>
									{#if prizeChipState(e) === 'eligible'}
										<span class="status-pill s-ghost">Eligible</span>
									{:else if prizeChipState(e) === 'pending'}
										<span class="status-pill s-warning">Pending payment</span>
									{:else}
										<span class="text-base-content/30">—</span>
									{/if}
								</td>
								<td class="text-xs text-base-content/60" title={e.updated_at}>{formatDate(e.updated_at)}</td>
								<td class="text-right text-base-content/40">›</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/30 text-xs text-base-content/40">
				<span>Showing 1–{listing.items.length} of {listing.total}</span>
			</div>
		{/if}
	</div>
</div>

<EntryDetailSlideOver
	entry={activeEntry}
	open={slideOverOpen}
	on:close={closeSlideOver}
	on:updated={handleUpdated}
/>

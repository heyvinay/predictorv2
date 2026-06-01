<!--
	/entries — list of every prediction entry the user owns.

	Design:
	  - Clean card-style table: no background shading, hairline row dividers
	  - "＋ New Entry" opens a naming dialog (not an immediate create)
	  - Entry names editable inline — pencil affordance on hover
	  - Completion column: three compact color-coded chips (Groups / Knockout / Bonus)
	  - All per-row actions in a single ⋮ kebab dropdown
	  - Clicking a row navigates into the entry
	  - Mobile-first: works equally well at 375 px and 1280 px+
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		entries,
		entriesLoading,
		entriesError,
		editableEntries,
		submittedEntries,
		entrySettings,
		loadEntries,
		refreshEntries
	} from '$stores/entries';
	import { isPhase1Locked } from '$stores/phase';
	import {
		entryUiStatus,
		entryStatusBadge,
		entryStatusDot,
		shouldShowPrizeModifier,
		type EntryUiStatus
	} from '$lib/utils/entryStatusBadge';
	import {
		createEntry,
		renameEntry,
		duplicateEntry,
		withdrawEntry,
		reinstateEntry,
		getCompletionSummary
	} from '$lib/api/entries';
	import type { CompletionSummary, Entry } from '$lib/types/entry';
	import { pageTitle } from '$stores/pageTitle';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted && $entries.length === 0 && !$entriesLoading) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	$: deadlinePassed = $isPhase1Locked;

	// ── Completion data ──────────────────────────────────────────────────────
	let completionMap = new Map<string, CompletionSummary>();
	let completionLoading = true;

	async function loadCompletion(): Promise<void> {
		completionLoading = true;
		try {
			const summaries = await getCompletionSummary();
			completionMap = new Map(summaries.map((s) => [s.entry_id, s]));
		} catch {
			// Non-fatal — chips just stay hidden
		} finally {
			completionLoading = false;
		}
	}

	onMount(() => {
		pageTitle.set('Entries');
		viewMode = loadViewMode();
		void loadCompletion();
	});

	// ── Action state ─────────────────────────────────────────────────────────
	let actionBusy: string | null = null;
	let confirmWithdrawId: string | null = null;
	let confirmReinstateId: string | null = null;
	// Component-local error surface for create/duplicate/withdraw/reinstate
	// failures — rendered as an inline alert near the header (avoids the
	// jarring native window.alert dialog on the primary money path).
	let actionError: string | null = null;

	// ── View mode (cards | list) ─────────────────────────────────────────────
	// Default cards on both desktop and mobile; user can switch and choice
	// persists in localStorage so it survives reload across devices.
	let viewMode: 'cards' | 'list' = 'cards';

	function loadViewMode(): 'cards' | 'list' {
		try {
			const v = localStorage.getItem('entries.viewMode');
			return v === 'list' ? 'list' : 'cards';
		} catch {
			return 'cards';
		}
	}

	$: {
		// Persist on every viewMode change. Wrapped in try so SSR / disabled
		// storage never throws.
		try {
			localStorage.setItem('entries.viewMode', viewMode);
		} catch {
			/* no-op */
		}
	}

	// ── New-entry modal ──────────────────────────────────────────────────────
	let newEntryModalOpen = false;
	let newEntryName = '';
	let newEntryBusy = false;

	function openNewEntryModal(): void {
		newEntryName = '';
		newEntryModalOpen = true;
	}

	async function handleCreate(): Promise<void> {
		actionError = null;
		newEntryBusy = true;
		try {
			await createEntry({ display_name: newEntryName.trim() || undefined });
			await Promise.all([loadEntries($user!.id), loadCompletion()]);
			newEntryModalOpen = false;
			newEntryName = '';
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to create entry';
		} finally {
			newEntryBusy = false;
		}
	}

	// ── Inline rename ────────────────────────────────────────────────────────
	let editingEntryId: string | null = null;
	let editingName = '';
	let editingOriginalName = '';

	function startEdit(entryId: string, currentName: string): void {
		editingEntryId = entryId;
		editingName = currentName;
		editingOriginalName = currentName;
	}

	async function commitRename(entryId: string): Promise<void> {
		const trimmed = editingName.trim();
		editingEntryId = null;
		if (!trimmed) return;
		const existing = $entries.find((e) => e.id === entryId);
		if (trimmed === existing?.display_name) return;
		try {
			await renameEntry(entryId, { display_name: trimmed });
			await refreshEntries();
		} catch {
			// Silent — stale name shows until next load
		}
	}

	// ── Row actions ──────────────────────────────────────────────────────────
	async function handleDuplicate(entryId: string): Promise<void> {
		actionError = null;
		actionBusy = entryId + ':dup';
		try {
			await duplicateEntry(entryId);
			await Promise.all([loadEntries($user!.id), loadCompletion()]);
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to duplicate entry';
		} finally {
			actionBusy = null;
		}
	}

	async function handleWithdraw(entryId: string): Promise<void> {
		actionError = null;
		confirmWithdrawId = null;
		actionBusy = entryId + ':withdraw';
		try {
			await withdrawEntry(entryId);
			await loadEntries($user!.id);
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to withdraw entry';
		} finally {
			actionBusy = null;
		}
	}

	async function handleReinstate(entryId: string): Promise<void> {
		actionError = null;
		confirmReinstateId = null;
		actionBusy = entryId + ':reinstate';
		try {
			await reinstateEntry(entryId);
			await Promise.all([loadEntries($user!.id), loadCompletion()]);
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Failed to reinstate entry';
		} finally {
			actionBusy = null;
		}
	}

	function openEntry(entryId: string): void {
		goto(`/entries/${entryId}`);
	}

	function formatUpdated(iso: string): string {
		try {
			return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
		} catch {
			return iso;
		}
	}

	$: maxEntries = $entrySettings?.max_entries_per_user ?? 1;
	$: activeEntries = $entries.filter((e) => e.withdrawn_at === null);
	$: canCreate = activeEntries.length < maxEntries;

	// ── Per-row derived state ────────────────────────────────────────────────
	// Single source of truth for both Card and List views. Returns everything
	// the row markup needs: badge/dot/CTA derived from the lifecycle status
	// (which itself depends on completion totals — see Context #2a in the
	// plan: passing totalRequired/totalFilled is what makes the `ready`
	// state actually fire so 100%-complete pre-deadline drafts get the
	// "Review & submit" CTA instead of "Continue picks").
	interface Cta {
		label: string;
		kind: 'primary' | 'ghost';
		locked: boolean;
		action: () => void;
	}
	interface RowState {
		completion: CompletionSummary | undefined;
		total: number;
		done: number;
		pct: number;
		ui: EntryUiStatus;
		badge: { label: string; class: string };
		dot: string;
		showNoPrize: boolean;
		isWithdrawn: boolean;
		noPredictions: boolean;
		cta: Cta | null;
	}

	function rowState(entry: Entry): RowState {
		const completion = completionMap.get(entry.id);
		const total =
			(completion?.groups.total ?? 0) +
			(completion?.bracket.total ?? 0) +
			(completion?.bonus.total ?? 0);
		const done =
			(completion?.groups.done ?? 0) +
			(completion?.bracket.done ?? 0) +
			(completion?.bonus.done ?? 0);
		const pct = total > 0 ? Math.round((done / total) * 100) : 0;
		const ui = entryUiStatus(entry, {
			deadlinePassed,
			totalRequired: total,
			totalFilled: done
		});
		const isWithdrawn = entry.withdrawn_at !== null;
		return {
			completion,
			total,
			done,
			pct,
			ui,
			badge: entryStatusBadge(ui),
			dot: entryStatusDot(ui),
			showNoPrize: shouldShowPrizeModifier(entry, ui),
			isWithdrawn,
			noPredictions: done === 0,
			cta: deriveCta(ui, entry.id, pct)
		};
	}

	function deriveCta(ui: EntryUiStatus, entryId: string, pct: number): Cta | null {
		if (ui === 'draft') {
			// Three-band escalation as user closes in on submission.
			// Thresholds are strict-less-than on the upper bound so a row
			// at exactly 30% reads "Continue picks", at exactly 80% reads
			// "Finish picks". 100% is the ready state, handled below.
			let label: string;
			if (pct < 30) label = 'Start picks';
			else if (pct < 80) label = 'Continue picks';
			else label = 'Finish picks';
			return { label, kind: 'primary', locked: false, action: () => openEntry(entryId) };
		}
		if (ui === 'ready') {
			return { label: 'Review and Submit', kind: 'primary', locked: false, action: () => openEntry(entryId) };
		}
		if (ui === 'locked' || ui === 'scored') {
			return { label: 'View entry', kind: 'ghost', locked: true, action: () => openEntry(entryId) };
		}
		if (ui === 'missed') {
			return { label: 'View entry', kind: 'ghost', locked: false, action: () => openEntry(entryId) };
		}
		if (ui === 'withdrawn') {
			return { label: 'Reinstate', kind: 'ghost', locked: false, action: () => (confirmReinstateId = entryId) };
		}
		return null; // disabled — no CTA, kebab still surfaces actions
	}
</script>

<svelte:head>
	<title>Entries - Predictor v2</title>
</svelte:head>

<!-- ── New Entry modal ─────────────────────────────────────────────────────── -->
{#if newEntryModalOpen}
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Create new entry"
		on:click|self={() => { newEntryModalOpen = false; }}
		on:keydown={(e) => { if (e.key === 'Escape') newEntryModalOpen = false; }}
	>
		<div class="card bg-base-100 shadow-2xl w-full max-w-sm">
			<div class="card-body gap-4">
				<h2 class="card-title text-base font-semibold">New entry</h2>
				<div>
					<input
						type="text"
						class="input input-bordered w-full"
						placeholder="e.g. My Picks, Entry A…"
						bind:value={newEntryName}
						maxlength={40}
						autofocus
						on:keydown={(e) => {
							if (e.key === 'Enter' && !newEntryBusy) handleCreate();
							if (e.key === 'Escape') { newEntryModalOpen = false; }
						}}
					/>
					<p class="text-xs text-base-content/50 mt-1.5">Optional — you can rename it any time.</p>
				</div>
				<div class="card-actions justify-end gap-2">
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						on:click={() => { newEntryModalOpen = false; }}
					>Cancel</button>
					<button
						type="button"
						class="btn btn-primary btn-sm min-w-[80px]"
						on:click={handleCreate}
						disabled={newEntryBusy}
					>
						{#if newEntryBusy}
							<span class="loading loading-spinner loading-xs"></span>
						{:else}
							Create
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- ── Withdraw confirmation ───────────────────────────────────────────────── -->
{#if confirmWithdrawId !== null}
	{@const entry = $entries.find((e) => e.id === confirmWithdrawId)}
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Confirm withdrawal"
		on:click|self={() => (confirmWithdrawId = null)}
		on:keydown={(e) => { if (e.key === 'Escape') confirmWithdrawId = null; }}
	>
		<div class="card bg-base-100 shadow-2xl w-full max-w-sm">
			<div class="card-body gap-3">
				<h2 class="card-title text-base font-semibold">Withdraw this entry?</h2>
				<p class="text-sm text-base-content/70">
					<strong>{entry?.display_name ?? 'This entry'}</strong> will be marked as withdrawn.
					You can reinstate it any time before the deadline.
				</p>
				<div class="card-actions justify-end gap-2 mt-1">
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						on:click={() => (confirmWithdrawId = null)}
					>Cancel</button>
					<button
						type="button"
						class="btn btn-error btn-sm min-w-[90px]"
						disabled={actionBusy !== null}
						on:click={() => { if (confirmWithdrawId) handleWithdraw(confirmWithdrawId); }}
					>
						{#if actionBusy?.endsWith(':withdraw')}
							<span class="loading loading-spinner loading-xs"></span>
						{:else}
							Withdraw
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- ── Reinstate confirmation ──────────────────────────────────────────────── -->
{#if confirmReinstateId !== null}
	{@const entry = $entries.find((e) => e.id === confirmReinstateId)}
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Confirm reinstatement"
		on:click|self={() => (confirmReinstateId = null)}
		on:keydown={(e) => { if (e.key === 'Escape') confirmReinstateId = null; }}
	>
		<div class="card bg-base-100 shadow-2xl w-full max-w-sm">
			<div class="card-body gap-3">
				<h2 class="card-title text-base font-semibold">Reinstate this entry?</h2>
				<p class="text-sm text-base-content/70">
					<strong>{entry?.display_name ?? 'This entry'}</strong> will be returned to active
					status. You can keep editing it until the deadline.
				</p>
				<div class="card-actions justify-end gap-2 mt-1">
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						on:click={() => (confirmReinstateId = null)}
					>Cancel</button>
					<button
						type="button"
						class="btn btn-success btn-sm min-w-[90px]"
						disabled={actionBusy !== null}
						on:click={() => { if (confirmReinstateId) handleReinstate(confirmReinstateId); }}
					>
						{#if actionBusy?.endsWith(':reinstate')}
							<span class="loading loading-spinner loading-xs"></span>
						{:else}
							Reinstate
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- ── Page ───────────────────────────────────────────────────────────────── -->
<!-- No explicit max-w — matches the data-page convention used by /admin,
     /leaderboard, /results, /profile. Falls back to Tailwind's default
     `container` cap (1536px at the 2xl breakpoint), so all data pages
     share the same visual width on wide desktops. Long-form text pages
     (/rules, /privacy) keep their narrower max-w-4xl. Standardized
     2026-06-01. -->
<div class="container mx-auto mobile-padding py-6">

	<!-- Header -->
	<header class="flex items-center justify-between mb-6 gap-4">
		<div>
			<h1 class="text-2xl font-bold">Entries</h1>
			<p class="text-sm text-base-content/50 mt-0.5">
				{#if $entriesLoading}
					Loading…
				{:else}
					{$entries.length} {$entries.length === 1 ? 'entry' : 'entries'}
					{#if $submittedEntries.length > 0}
						· {$submittedEntries.length} submitted
					{/if}
					{#if $editableEntries.length > 0}
						· {$editableEntries.length} draft
					{/if}
				{/if}
			</p>
		</div>
		<div class="flex items-center gap-2 flex-shrink-0">
			<!-- View-mode segmented toggle. Persists to localStorage; default = cards.
			     Active state uses btn-active (neutral pressed look) rather than
			     btn-primary, so the gold accent stays reserved for the primary
			     CTA on each entry (no visual collision in the header row). -->
			<div class="join" role="group" aria-label="View mode">
				<button
					type="button"
					class="btn btn-sm join-item {viewMode === 'cards' ? 'btn-active' : 'btn-ghost'}"
					aria-pressed={viewMode === 'cards'}
					aria-label="Card view"
					on:click={() => (viewMode = 'cards')}
				>
					<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h6v6H4V6zm10 0h6v6h-6V6zM4 14h6v6H4v-6zm10 0h6v6h-6v-6z" />
					</svg>
					<span class="hidden sm:inline">Cards</span>
				</button>
				<button
					type="button"
					class="btn btn-sm join-item {viewMode === 'list' ? 'btn-active' : 'btn-ghost'}"
					aria-pressed={viewMode === 'list'}
					aria-label="List view"
					on:click={() => (viewMode = 'list')}
				>
					<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
					</svg>
					<span class="hidden sm:inline">List</span>
				</button>
			</div>
			<button
				type="button"
				class="btn btn-primary btn-sm gap-1.5"
				disabled={!canCreate || $entriesLoading}
				title={!canCreate
					? `Maximum of ${maxEntries} active ${maxEntries === 1 ? 'entry' : 'entries'} reached`
					: undefined}
				on:click={openNewEntryModal}
			>
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				<span class="hidden sm:inline">New Entry</span>
				<span class="sm:hidden">New</span>
			</button>
		</div>
	</header>

	{#if $entriesError}
		<div class="alert alert-error mb-4"><span>{$entriesError}</span></div>
	{/if}

	{#if actionError}
		<div class="alert alert-error mb-4" role="alert">
			<span class="flex-1">{actionError}</span>
			<button
				type="button"
				class="btn btn-ghost btn-xs"
				on:click={() => (actionError = null)}
				aria-label="Dismiss error"
			>
				✕
			</button>
		</div>
	{/if}

	{#if $entriesLoading && $entries.length === 0}
		<!-- Loading skeletons -->
		<div class="rounded-xl border border-base-300/50 overflow-hidden">
			{#each Array(3) as _}
				<div class="flex items-center gap-4 px-4 py-3.5 border-b border-base-300/40 last:border-0">
					<div class="skeleton w-2 h-2 rounded-full flex-shrink-0"></div>
					<div class="skeleton h-4 w-32 rounded"></div>
					<div class="skeleton h-5 w-16 rounded-full ml-auto"></div>
				</div>
			{/each}
		</div>

	{:else if $entries.length === 0}
		<div class="rounded-xl border border-base-300/50 bg-base-200/40">
			<div class="flex flex-col items-center text-center py-14 px-6 gap-4">
				<div class="text-3xl">📋</div>
				<h2 class="font-semibold text-base">No entries yet</h2>
				<p class="text-sm text-base-content/50 max-w-xs">
					Name your entry, then fill in your picks. You can edit until the deadline.
				</p>
				<button
					type="button"
					class="btn btn-primary btn-lg gap-2 mt-2 shadow-glow-gold"
					disabled={!canCreate || $entriesLoading}
					title={!canCreate
						? `Maximum of ${maxEntries} active ${maxEntries === 1 ? 'entry' : 'entries'} reached`
						: undefined}
					on:click={openNewEntryModal}
				>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
					</svg>
					Create your first entry
				</button>
			</div>
		</div>

	{:else if viewMode === 'cards'}
		<!-- ── Card view ───────────────────────────────────────────────────────── -->
		<div
			class="grid gap-[18px]"
			style="grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));"
		>
			{#each $entries as entry (entry.id)}
				{@const s = rowState(entry)}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<article
					class="bg-base-200 border rounded-2xl p-4 flex flex-col gap-3
						shadow-card transition-shadow hover:shadow-glow-gold cursor-pointer
						{s.isWithdrawn ? 'opacity-50' : ''}
						{s.ui === 'locked' || s.ui === 'scored' ? 'border-success/30' : 'border-base-300/50'}"
					on:click={() => { if (editingEntryId !== entry.id) openEntry(entry.id); }}
				>
					<!-- Top row: dot + name (+ pencil) + kebab -->
					<div class="flex items-start gap-2 min-w-0">
						<span class="w-2 h-2 rounded-full flex-shrink-0 mt-1.5 {s.dot}" aria-hidden="true"></span>
						<div class="flex-1 min-w-0">
							{#if editingEntryId === entry.id}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
								<div on:click|stopPropagation>
									<input
										type="text"
										class="input input-bordered input-sm w-full font-medium"
										bind:value={editingName}
										autofocus
										on:blur={() => commitRename(entry.id)}
										on:keydown={(e) => {
											if (e.key === 'Enter') e.currentTarget.blur();
											if (e.key === 'Escape') { editingName = editingOriginalName; editingEntryId = null; }
										}}
									/>
								</div>
							{:else}
								<div class="flex items-center gap-1.5 group/name min-w-0">
									<span class="font-medium truncate">
										{entry.display_name || `Entry #${entry.entry_number}`}
									</span>
									<button
										type="button"
										class="opacity-0 group-hover/name:opacity-50 hover:!opacity-100 transition-opacity flex-shrink-0 p-0.5 rounded hover:bg-base-300/60"
										title="Rename"
										aria-label="Rename {entry.display_name}"
										on:click|stopPropagation={() => startEdit(entry.id, entry.display_name)}
									>
										<svg class="w-3 h-3 text-base-content" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
											<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z"/>
										</svg>
									</button>
								</div>
								<div class="text-[10px] font-mono text-base-content/35 mt-0.5 truncate">
									{entry.reference} · Updated {formatUpdated(entry.updated_at)}
								</div>
							{/if}
						</div>
						<!-- Kebab (duplicated from list view; identical menu items) -->
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<div on:click|stopPropagation>
							<details class="relative">
								<summary
									class="btn btn-ghost btn-sm btn-square list-none"
									aria-label="Actions for {entry.display_name || `Entry #${entry.entry_number}`}"
								>
									<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
										<circle cx="12" cy="5"  r="1.5"/>
										<circle cx="12" cy="12" r="1.5"/>
										<circle cx="12" cy="19" r="1.5"/>
									</svg>
								</summary>
								<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
								<ul
									class="absolute right-0 top-full mt-1 min-w-44 bg-base-100 border border-base-300/60 rounded-xl shadow-xl z-30 overflow-hidden py-1"
									on:click={(e) => {
										const det = e.currentTarget.closest('details');
										if (det) det.removeAttribute('open');
									}}
								>
									{#if !s.isWithdrawn}
										<li>
											<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors" on:click={() => openEntry(entry.id)}>
												<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6"/>
												</svg>
												Open
											</button>
										</li>
										<li>
											<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors" on:click={() => startEdit(entry.id, entry.display_name)}>
												<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z"/>
												</svg>
												Rename
											</button>
										</li>
										<li>
											<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed" disabled={s.noPredictions || actionBusy !== null} title={s.noPredictions ? 'Add predictions before duplicating' : undefined} on:click={() => handleDuplicate(entry.id)}>
												{#if actionBusy === entry.id + ':dup'}
													<span class="loading loading-spinner loading-xs w-4 h-4 flex-shrink-0"></span>
												{:else}
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
													</svg>
												{/if}
												Duplicate
											</button>
										</li>
<li class="border-t border-base-300/40 mt-1 pt-1">
											<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-error/5 text-error/80 transition-colors" disabled={actionBusy !== null} on:click={() => (confirmWithdrawId = entry.id)}>
												<svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/>
												</svg>
												Withdraw
											</button>
										</li>
									{:else}
										<li>
											<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40" disabled={actionBusy !== null} on:click={() => (confirmReinstateId = entry.id)}>
												<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
												</svg>
												Reinstate
											</button>
										</li>
									{/if}
								</ul>
							</details>
						</div>
					</div>

					<!-- Status row: badges (left) + completion % (right) -->
					<div class="flex items-center justify-between gap-2 flex-wrap">
						<div class="flex items-center gap-1.5 flex-wrap">
							<span class="badge badge-sm {s.badge.class} whitespace-nowrap">{s.badge.label}</span>
							{#if s.showNoPrize}
								<span class="badge badge-ghost badge-sm whitespace-nowrap" title="Not eligible for the prize pool">NO PRIZE</span>
							{/if}
						</div>
						{#if s.total > 0 && !completionLoading}
							<span class="font-display font-bold text-base
								{s.pct >= 100 ? 'text-success' : 'text-base-content/80'}
								{s.isWithdrawn || s.ui === 'disabled' ? 'opacity-60' : ''}">
								{s.pct}%
							</span>
						{/if}
					</div>

					<!-- Per-section breakdown — single quiet line, right-aligned to mirror
					     the percentage on the status row above it. No bar (removed per user feedback). -->
					{#if completionLoading}
						<div class="skeleton h-3 w-3/4 rounded ml-auto"></div>
					{:else if s.total > 0 && s.completion}
						<p class="text-[10px] font-mono text-base-content/55 leading-tight text-right">
							<span class={s.completion.groups.done === s.completion.groups.total ? 'text-success' : 'text-primary'}>{s.completion.groups.done}/{s.completion.groups.total} grp</span><span class="text-base-content/30"> · </span><span class={s.completion.bracket.done === s.completion.bracket.total ? 'text-success' : 'text-primary'}>{s.completion.bracket.done}/{s.completion.bracket.total} brk</span><span class="text-base-content/30"> · </span><span class={s.completion.bonus.done === s.completion.bonus.total ? 'text-success' : 'text-warning-text'}>{s.completion.bonus.done}/{s.completion.bonus.total} bns</span>
						</p>
					{/if}

					<!-- Bottom row: predicted winner (left) + contextual CTA (right).
					     Winner chip sits opposite the CTA so the eye can read
					     "this is my champion pick → this is the action I'd take" in
					     one horizontal scan. Hidden while completion is loading to
					     avoid flickering 'TBD' for entries whose winner is picked. -->
					<div class="flex items-end justify-between gap-2 mt-auto">
						<div class="min-w-0">
							{#if s.completion}
								<span
									class="badge badge-ghost badge-sm whitespace-nowrap"
									title={s.completion.predicted_winner ? `Predicted winner: ${s.completion.predicted_winner}` : 'Winner not yet predicted'}
								>
									🏆 {s.completion.predicted_winner ?? 'TBD'}
								</span>
							{/if}
						</div>
						{#if s.cta}
							<button
								type="button"
								class="btn btn-xs gap-1.5 {s.cta.kind === 'primary' ? 'btn-primary' : 'btn-ghost'}"
								on:click|stopPropagation={s.cta.action}
							>
								{#if s.cta.locked}
									<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
									</svg>
								{/if}
								{s.cta.label}
							</button>
						{/if}
					</div>
				</article>
			{/each}

			{#if canCreate}
				<button
					type="button"
					class="border-2 border-dashed border-base-300 rounded-2xl p-4 flex flex-col items-center justify-center gap-2 min-h-[180px] text-base-content/55 hover:text-primary hover:border-primary hover:bg-primary/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
					disabled={$entriesLoading}
					on:click={openNewEntryModal}
				>
					<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/>
					</svg>
					<span class="text-sm font-medium">Add entry · {maxEntries - activeEntries.length} left</span>
				</button>
			{/if}
		</div>

	{:else}
		<!-- ── List view (table) ──────────────────────────────────────────────────
		     overflow-hidden removed 2026-06-01 — it was clipping the row-kebab
		     dropdown when it opened below the last row (very visible with a single
		     entry; less visible but still present at the last row of longer lists).
		     The rounded-xl outer border still draws crisply; the thead's
		     bg-base-300 paints under it with a sub-pixel artifact at 12px radius
		     that's effectively invisible in practice. -->
		<div class="rounded-xl border border-base-300/50 bg-base-100">
			<table class="w-full text-sm">
				<thead class="bg-base-300">
					<tr>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-4 py-3">Name</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-4 py-3">Status</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-4 py-3 hidden sm:table-cell min-w-[180px]">Completion</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-4 py-3 hidden lg:table-cell whitespace-nowrap">Updated</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/60 px-4 py-3 hidden sm:table-cell">Action</th>
						<th class="w-10 px-2 py-3"></th>
					</tr>
				</thead>
				<tbody>
					{#each $entries as entry (entry.id)}
						{@const s = rowState(entry)}

						<tr
							class="group/row bg-base-200 border-b border-base-300/40 last:border-b-0
								transition-colors duration-100 cursor-pointer
								hover:bg-base-200/70
								{s.isWithdrawn ? 'opacity-50' : ''}"
							on:click={() => { if (editingEntryId !== entry.id) openEntry(entry.id); }}
						>

							<!-- Name cell: inline edit or display+pencil -->
							<td class="px-4 py-3 min-w-0">
								{#if editingEntryId === entry.id}
									<!-- svelte-ignore a11y-click-events-have-key-events -->
									<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
									<div on:click|stopPropagation>
										<input
											type="text"
											class="input input-bordered input-sm w-full max-w-[200px] font-medium"
											bind:value={editingName}
											autofocus
											on:blur={() => commitRename(entry.id)}
											on:keydown={(e) => {
												if (e.key === 'Enter') e.currentTarget.blur();
												if (e.key === 'Escape') { editingName = editingOriginalName; editingEntryId = null; }
											}}
										/>
									</div>
								{:else}
									<div class="flex items-center gap-2 min-w-0">
										<span
											class="w-2 h-2 rounded-full flex-shrink-0 {s.dot}"
											aria-hidden="true"
										></span>
										<div class="min-w-0 flex-1">
											<div class="flex items-center gap-1.5 group/name min-w-0">
												<span class="font-medium truncate">
													{entry.display_name || `Entry #${entry.entry_number}`}
												</span>
												<button
													type="button"
													class="opacity-0 group-hover/row:opacity-50 hover:!opacity-100 transition-opacity flex-shrink-0 p-0.5 rounded hover:bg-base-300/60"
													title="Rename"
													aria-label="Rename {entry.display_name}"
													on:click|stopPropagation={() => startEdit(entry.id, entry.display_name)}
												>
													<svg class="w-3 h-3 text-base-content" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
														<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z"/>
													</svg>
												</button>
											</div>
											<div class="flex items-center gap-1.5 mt-0.5 sm:hidden">
												<span class="text-[10px] font-mono text-base-content/35">{entry.reference}</span>
											</div>
										</div>
									</div>
									<div class="hidden sm:block text-[10px] font-mono text-base-content/35 mt-0.5 ml-4">
										{entry.reference}
									</div>
								{/if}
							</td>

							<!-- Status -->
							<td class="px-4 py-3">
								<span class="inline-flex items-center gap-1.5 flex-wrap">
									<span class="badge badge-sm {s.badge.class} whitespace-nowrap">{s.badge.label}</span>
									{#if s.showNoPrize}
										<span class="badge badge-ghost badge-sm whitespace-nowrap" title="Not eligible for the prize pool">NO PRIZE</span>
									{/if}
									<!-- Predicted winner chip — mirrors the card view. -->
									{#if s.completion}
										<span
											class="badge badge-ghost badge-sm whitespace-nowrap"
											title={s.completion.predicted_winner ? `Predicted winner: ${s.completion.predicted_winner}` : 'Winner not yet predicted'}
										>
											🏆 {s.completion.predicted_winner ?? 'TBD'}
										</span>
									{/if}
								</span>
							</td>

							<!-- Completion: % + slim bar + caption (replaces doughnut) -->
							<td class="px-4 py-3 hidden sm:table-cell">
								{#if completionLoading}
									<div class="skeleton h-2 w-32 rounded-full"></div>
								{:else if s.total > 0 && s.completion}
									<div class="min-w-[160px]">
										<div class="flex items-baseline justify-between gap-2">
											<span class="font-display font-bold text-sm
												{s.pct >= 100 ? 'text-success' : 'text-base-content'}
												{s.isWithdrawn || s.ui === 'disabled' ? 'opacity-60' : ''}">
												{s.pct}%
											</span>
											<span class="text-[10px] font-mono text-base-content/55">
												<span class={s.completion.groups.done === s.completion.groups.total ? 'text-success' : 'text-primary'}>{s.completion.groups.done}/{s.completion.groups.total} grp</span><span class="text-base-content/30"> · </span><span class={s.completion.bracket.done === s.completion.bracket.total ? 'text-success' : 'text-primary'}>{s.completion.bracket.done}/{s.completion.bracket.total} brk</span><span class="text-base-content/30"> · </span><span class={s.completion.bonus.done === s.completion.bonus.total ? 'text-success' : 'text-warning-text'}>{s.completion.bonus.done}/{s.completion.bonus.total} bns</span>
											</span>
										</div>
										<div class="mt-1 h-[7px] w-full rounded-full bg-base-content/10 overflow-hidden">
											<div
												class="h-full rounded-full transition-[width] duration-300
													{s.isWithdrawn || s.ui === 'disabled'
														? 'bg-base-content/30'
														: s.pct >= 100 ? 'bg-success' : 'bg-primary'}"
												style="width: {s.pct}%"
											></div>
										</div>
									</div>
								{:else}
									<span class="text-xs text-base-content/25">—</span>
								{/if}
							</td>

							<!-- Updated (hidden < lg) -->
							<td class="px-4 py-3 hidden lg:table-cell whitespace-nowrap">
								<span class="text-xs text-base-content/50">{formatUpdated(entry.updated_at)}</span>
							</td>

							<!-- Action (contextual CTA, hidden < sm) -->
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
							<td class="px-4 py-3 hidden sm:table-cell" on:click|stopPropagation role="cell">
								{#if s.cta}
									<button
										type="button"
										class="btn btn-xs gap-1.5 whitespace-nowrap {s.cta.kind === 'primary' ? 'btn-primary' : 'btn-ghost'}"
										on:click={s.cta.action}
									>
										{#if s.cta.locked}
											<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
												<path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
											</svg>
										{/if}
										{s.cta.label}
									</button>
								{/if}
							</td>

							<!-- Kebab ⋮ — all row actions -->
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
							<td
								class="px-2 py-3 w-10"
								on:click|stopPropagation
								role="cell"
							>
								<details class="relative">
									<summary
										class="btn btn-ghost btn-sm btn-square list-none"
										aria-label="Actions for {entry.display_name || `Entry #${entry.entry_number}`}"
									>
										<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
											<circle cx="12" cy="5"  r="1.5"/>
											<circle cx="12" cy="12" r="1.5"/>
											<circle cx="12" cy="19" r="1.5"/>
										</svg>
									</summary>
									<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
									<ul
										class="absolute right-0 top-full mt-1 min-w-44 bg-base-100 border border-base-300/60 rounded-xl shadow-xl z-30 overflow-hidden py-1"
										on:click={(e) => {
											const det = e.currentTarget.closest('details');
											if (det) det.removeAttribute('open');
										}}
									>
										{#if !s.isWithdrawn}
											<li>
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors" on:click={() => openEntry(entry.id)}>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6"/>
													</svg>
													Open
												</button>
											</li>
											<li>
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors" on:click={() => startEdit(entry.id, entry.display_name)}>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z"/>
													</svg>
													Rename
												</button>
											</li>
											<li>
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed" disabled={s.noPredictions || actionBusy !== null} title={s.noPredictions ? 'Add predictions before duplicating' : undefined} on:click={() => handleDuplicate(entry.id)}>
													{#if actionBusy === entry.id + ':dup'}
														<span class="loading loading-spinner loading-xs w-4 h-4 flex-shrink-0"></span>
													{:else}
														<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
															<path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
														</svg>
													{/if}
													Duplicate
												</button>
											</li>
											<li>
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors" on:click={() => goto(`/entries/${entry.id}?print=1`)}>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
													</svg>
													Print
												</button>
											</li>
											<li class="border-t border-base-300/40 mt-1 pt-1">
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-error/5 text-error/80 transition-colors" disabled={actionBusy !== null} on:click={() => (confirmWithdrawId = entry.id)}>
													<svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/>
													</svg>
													Withdraw
												</button>
											</li>
										{:else}
											<li>
												<button type="button" class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40" disabled={actionBusy !== null} on:click={() => handleReinstate(entry.id)}>
													{#if actionBusy === entry.id + ':reinstate'}
														<span class="loading loading-spinner loading-xs w-4 h-4 flex-shrink-0"></span>
													{:else}
														<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
															<path stroke-linecap="round" stroke-linejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
														</svg>
													{/if}
													Reinstate
												</button>
											</li>
										{/if}
									</ul>
								</details>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

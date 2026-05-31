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
		shouldShowPrizeModifier
	} from '$lib/utils/entryStatusBadge';
	import {
		createEntry,
		renameEntry,
		duplicateEntry,
		withdrawEntry,
		reinstateEntry,
		getCompletionSummary
	} from '$lib/api/entries';
	import type { CompletionSummary } from '$lib/types/entry';
	import ProgressSection from '$lib/components/predictions/ProgressSection.svelte';
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
		void loadCompletion();
	});

	// ── Action state ─────────────────────────────────────────────────────────
	let actionBusy: string | null = null;
	let confirmWithdrawId: string | null = null;
	// Component-local error surface for create/duplicate/withdraw/reinstate
	// failures — rendered as an inline alert near the header (avoids the
	// jarring native window.alert dialog on the primary money path).
	let actionError: string | null = null;

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

	/** Map any UI status string to the 4-value union ProgressSection accepts. */
	function toProgressStatus(uiStatus: string, withdrawn: boolean): 'draft' | 'locked' | 'scored' | 'missed' {
		if (withdrawn) return 'missed';
		if (uiStatus === 'locked' || uiStatus === 'scored' || uiStatus === 'missed') return uiStatus;
		return 'draft';
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

<!-- ── Page ───────────────────────────────────────────────────────────────── -->
<div class="container mx-auto px-4 py-6 max-w-4xl">

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
		<button
			type="button"
			class="btn btn-primary btn-sm gap-1.5 flex-shrink-0"
			disabled={!canCreate || $entriesLoading}
			title={!canCreate
				? `Maximum of ${maxEntries} active ${maxEntries === 1 ? 'entry' : 'entries'} reached`
				: undefined}
			on:click={openNewEntryModal}
		>
			<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			New Entry
		</button>
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

	{:else}
		<!-- Table — no shading, hairline row separators -->
		<div class="rounded-xl border border-base-300/50 overflow-hidden bg-base-100">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-base-300/50">
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/40 px-4 py-2.5">Name</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/40 px-4 py-2.5">Status</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/40 px-4 py-2.5 hidden sm:table-cell">Completion</th>
						<th class="text-left text-[11px] font-semibold uppercase tracking-wider text-base-content/40 px-4 py-2.5 hidden lg:table-cell">Updated</th>
						<th class="w-10 px-2 py-2.5"></th>
					</tr>
				</thead>
				<tbody class="divide-y divide-base-300/40">
					{#each $entries as entry (entry.id)}
						{@const ui = entryUiStatus(entry, { deadlinePassed })}
						{@const badge = entryStatusBadge(ui)}
						{@const showNoPrize = shouldShowPrizeModifier(entry, ui)}
						{@const isWithdrawn = entry.withdrawn_at !== null}
						{@const completion = completionMap.get(entry.id)}
						{@const noPredictions =
							!completion ||
							(completion.groups.done === 0 &&
								completion.bracket.done === 0 &&
								completion.bonus.done === 0)}

						<tr
							class="group/row transition-colors duration-100 cursor-pointer
								hover:bg-base-200/40
								{isWithdrawn ? 'opacity-50' : ''}"
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
											class="w-2 h-2 rounded-full flex-shrink-0 {entryStatusDot(ui)}"
											aria-hidden="true"
										></span>
										<div class="min-w-0 flex-1">
											<div class="flex items-center gap-1.5 group/name min-w-0">
												<span class="font-medium truncate">
													{entry.display_name || `Entry #${entry.entry_number}`}
												</span>
												<!-- Pencil — visible on row hover or touch -->
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
											<!-- Reference + date sub-line (mobile) -->
											<div class="flex items-center gap-1.5 mt-0.5 sm:hidden">
												<span class="text-[10px] font-mono text-base-content/35">{entry.reference}</span>
											</div>
										</div>
									</div>
									<!-- Reference sub-line (sm+, under the name) -->
									<div class="hidden sm:block text-[10px] font-mono text-base-content/35 mt-0.5 ml-4">
										{entry.reference}
									</div>
								{/if}
							</td>

							<!-- Status -->
							<td class="px-4 py-3">
								<span class="inline-flex items-center gap-1.5 flex-wrap">
									<span class="badge badge-sm {badge.class} whitespace-nowrap">{badge.label}</span>
									{#if showNoPrize}
										<span class="badge badge-ghost badge-sm whitespace-nowrap" title="Not eligible for the prize pool">NO PRIZE</span>
									{/if}
								</span>
							</td>

							<!-- Completion doughnut (hidden < sm) -->
							<td class="px-4 py-3 hidden sm:table-cell">
								{#if completionLoading}
									<div class="skeleton w-10 h-10 rounded-full"></div>
								{:else if completion}
									<ProgressSection
										groupProgress={completion.groups}
										bracketProgress={completion.bracket}
										bonusProgress={completion.bonus}
										status={toProgressStatus(ui, isWithdrawn)}
										sizeClass="w-10 h-10"
									/>
								{:else}
									<span class="text-xs text-base-content/25">—</span>
								{/if}
							</td>

							<!-- Updated (hidden < lg) -->
							<td class="px-4 py-3 hidden lg:table-cell">
								<span class="text-xs text-base-content/50">{formatUpdated(entry.updated_at)}</span>
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
										<!-- Vertical dots -->
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
										{#if !isWithdrawn}
											<!-- Open -->
											<li>
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors"
													on:click={() => openEntry(entry.id)}
												>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6"/>
													</svg>
													Open
												</button>
											</li>
											<!-- Rename -->
											<li>
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors"
													on:click={() => startEdit(entry.id, entry.display_name)}
												>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z"/>
													</svg>
													Rename
												</button>
											</li>
											<!-- Duplicate -->
											<li>
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
													disabled={noPredictions || actionBusy !== null}
													title={noPredictions ? 'Add predictions before duplicating' : undefined}
													on:click={() => handleDuplicate(entry.id)}
												>
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
											<!-- Print -->
											<li>
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors"
													on:click={() => goto(`/entries/${entry.id}?print=1`)}
												>
													<svg class="w-4 h-4 text-base-content/50 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
													</svg>
													Print
												</button>
											</li>
											<!-- Separator + Withdraw -->
											<li class="border-t border-base-300/40 mt-1 pt-1">
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-error/5 text-error/80 transition-colors"
													disabled={actionBusy !== null}
													on:click={() => (confirmWithdrawId = entry.id)}
												>
													<svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/>
													</svg>
													Withdraw
												</button>
											</li>

										{:else}
											<!-- Reinstate only (withdrawn rows) -->
											<li>
												<button
													type="button"
													class="w-full px-4 py-2.5 text-sm text-left flex items-center gap-2.5 hover:bg-base-200/70 transition-colors disabled:opacity-40"
													disabled={actionBusy !== null}
													on:click={() => handleReinstate(entry.id)}
												>
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

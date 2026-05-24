<!--
	/entries — list view of every prediction entry the user owns.

	Features:
	  - "＋ New Entry" button — disabled at max_entries_per_user limit
	  - Completion dots (groups / bracket / bonus) in a dedicated column
	  - Per-row Duplicate, Withdraw/Reinstate, Print actions
	  - Mobile: secondary actions collapse into a ⋯ overflow menu
	  - Withdrawn rows: faded + only Reinstate shown
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
		loadEntries
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
		duplicateEntry,
		withdrawEntry,
		reinstateEntry,
		getCompletionSummary
	} from '$lib/api/entries';
	import type { CompletionSummary } from '$lib/types/entry';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Hydrate when $user.id resolves — reactive (not onMount) because
	// initAuth() can complete AFTER this page mounts on a fresh reload.
	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted && $entries.length === 0 && !$entriesLoading) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	$: deadlinePassed = $isPhase1Locked;

	// ---- Completion data ----
	let completionMap = new Map<string, CompletionSummary>();
	let completionLoading = true;

	async function loadCompletion(): Promise<void> {
		completionLoading = true;
		try {
			const summaries = await getCompletionSummary();
			completionMap = new Map(summaries.map((s) => [s.entry_id, s]));
		} catch {
			// Non-fatal — completion dots just won't show
		} finally {
			completionLoading = false;
		}
	}

	onMount(() => {
		void loadCompletion();
	});

	// ---- Action state ----
	let actionBusy: string | null = null;
	let confirmWithdrawId: string | null = null;

	async function handleCreate(): Promise<void> {
		actionBusy = 'new';
		try {
			await createEntry({});
			await loadEntries($user!.id);
			await loadCompletion();
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Failed to create entry');
		} finally {
			actionBusy = null;
		}
	}

	async function handleDuplicate(entryId: string): Promise<void> {
		actionBusy = entryId + ':dup';
		try {
			await duplicateEntry(entryId);
			await loadEntries($user!.id);
			await loadCompletion();
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Failed to duplicate entry');
		} finally {
			actionBusy = null;
		}
	}

	async function handleWithdraw(entryId: string): Promise<void> {
		confirmWithdrawId = null;
		actionBusy = entryId + ':withdraw';
		try {
			await withdrawEntry(entryId);
			await loadEntries($user!.id);
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Failed to withdraw entry');
		} finally {
			actionBusy = null;
		}
	}

	async function handleReinstate(entryId: string): Promise<void> {
		actionBusy = entryId + ':reinstate';
		try {
			await reinstateEntry(entryId);
			await loadEntries($user!.id);
			await loadCompletion();
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Failed to reinstate entry');
		} finally {
			actionBusy = null;
		}
	}

	function openEntry(entryId: string): void {
		goto(`/entries/${entryId}`);
	}

	function formatUpdated(iso: string): string {
		try {
			return new Date(iso).toLocaleString(undefined, {
				dateStyle: 'medium',
				timeStyle: 'short'
			});
		} catch {
			return iso;
		}
	}

	// Completion dot colour: success when full, warning when partial, ghost when empty
	function dotColor(done: number, total: number): string {
		if (total === 0 || done === 0) return 'bg-base-content/15';
		if (done >= total) return 'bg-success';
		return 'bg-warning';
	}

	$: maxEntries = $entrySettings?.max_entries_per_user ?? 1;
	$: activeEntries = $entries.filter((e) => e.withdrawn_at === null);
	$: canCreate = activeEntries.length < maxEntries;
</script>

<svelte:head>
	<title>Entries - Predictor v2</title>
</svelte:head>

<!-- Withdraw confirmation dialog -->
{#if confirmWithdrawId !== null}
	{@const entry = $entries.find((e) => e.id === confirmWithdrawId)}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		role="dialog"
		aria-modal="true"
		aria-label="Confirm withdrawal"
	>
		<div class="card bg-base-100 shadow-xl max-w-sm mx-4 w-full">
			<div class="card-body">
				<h2 class="card-title text-base">Withdraw this entry?</h2>
				<p class="text-sm text-base-content/70">
					<strong>{entry?.display_name ?? 'This entry'}</strong> will be marked as withdrawn.
					You can reinstate it any time before the deadline.
				</p>
				<div class="card-actions justify-end gap-2 mt-2">
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						on:click={() => (confirmWithdrawId = null)}
					>
						Cancel
					</button>
					<button
						type="button"
						class="btn btn-error btn-sm"
						disabled={actionBusy !== null}
						on:click={() => { if (confirmWithdrawId) handleWithdraw(confirmWithdrawId); }}
					>
						{#if actionBusy?.endsWith(':withdraw')}
							<span class="loading loading-spinner loading-xs"></span>
						{/if}
						Withdraw
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<div class="container mx-auto px-4 py-6 max-w-5xl">
	<!-- Header -->
	<header class="flex items-center justify-between mb-6 gap-4">
		<div>
			<h1 class="text-2xl font-bold">Entries</h1>
			<p class="text-sm text-base-content/60 mt-1">
				{#if $entriesLoading}
					Loading…
				{:else}
					{$entries.length}
					{$entries.length === 1 ? 'entry' : 'entries'} ·
					{$submittedEntries.length} submitted, {$editableEntries.length} draft
				{/if}
			</p>
		</div>

		<!-- New Entry button -->
		<button
			type="button"
			class="btn btn-primary btn-sm gap-1.5 flex-shrink-0"
			disabled={!canCreate || actionBusy === 'new' || $entriesLoading}
			title={!canCreate
				? `Maximum of ${maxEntries} active ${maxEntries === 1 ? 'entry' : 'entries'} allowed`
				: undefined}
			on:click={handleCreate}
		>
			{#if actionBusy === 'new'}
				<span class="loading loading-spinner loading-xs"></span>
			{:else}
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
			{/if}
			New Entry
		</button>
	</header>

	{#if $entriesError}
		<div class="alert alert-error mb-4">
			<span>{$entriesError}</span>
		</div>
	{/if}

	{#if $entriesLoading && $entries.length === 0}
		<div class="space-y-2">
			{#each Array(3) as _}
				<div class="skeleton h-14 w-full"></div>
			{/each}
		</div>
	{:else if $entries.length === 0}
		<div class="card bg-base-200 border border-base-300/50">
			<div class="card-body items-center text-center py-12">
				<h2 class="card-title">No entries yet</h2>
				<p class="text-sm text-base-content/60">
					Click "New Entry" above to get started, or contact your competition admin if one
					should have been created automatically.
				</p>
			</div>
		</div>
	{:else}
		<div class="overflow-x-auto rounded-xl border border-base-300/50 bg-base-200">
			<table class="table table-hover">
				<thead>
					<tr class="text-xs uppercase tracking-wider text-base-content/60">
						<th>Name</th>
						<th class="hidden sm:table-cell">Reference</th>
						<th>Status</th>
						<th class="hidden sm:table-cell">Completion</th>
						<th class="hidden md:table-cell">Updated</th>
						<th class="text-right">Actions</th>
					</tr>
				</thead>
				<tbody>
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
						<tr class="hover:bg-base-300/40 {isWithdrawn ? 'opacity-50' : ''}">
							<!-- Name cell — click navigates to wizard (non-withdrawn only) -->
							<td>
								<button
									type="button"
									class="flex items-center gap-2 min-w-0 text-left w-full"
									disabled={isWithdrawn}
									on:click={() => !isWithdrawn && openEntry(entry.id)}
								>
									<span
										class="w-2.5 h-2.5 rounded-full {entryStatusDot(ui)} flex-shrink-0"
										aria-hidden="true"
									></span>
									<div class="min-w-0">
										<div class="font-medium truncate">
											{entry.display_name || `Entry #${entry.entry_number}`}
										</div>
										<div class="text-xs font-mono text-base-content/50 sm:hidden">
											{entry.reference}
										</div>
									</div>
								</button>
							</td>

							<!-- Reference (hidden < sm) -->
							<td class="hidden sm:table-cell">
								<span class="text-xs font-mono text-base-content/60">{entry.reference}</span>
							</td>

							<!-- Status badge -->
							<td>
								<span class="inline-flex items-center gap-1.5 flex-wrap">
									<span class="badge badge-sm {badge.class} whitespace-nowrap">{badge.label}</span>
									{#if showNoPrize}
										<span
											class="badge badge-ghost badge-sm whitespace-nowrap"
											title="This entry is not eligible for the prize pool"
										>NO PRIZE</span>
									{/if}
								</span>
							</td>

							<!-- Completion (hidden < sm) -->
							<td class="hidden sm:table-cell">
								{#if completionLoading}
									<div class="flex gap-1.5">
										{#each Array(3) as _}
											<div class="skeleton w-10 h-3 rounded"></div>
										{/each}
									</div>
								{:else if completion}
									<div class="flex items-center gap-2 text-xs font-mono tabular-nums">
										<!-- Groups dot -->
										<span
											class="flex items-center gap-0.5"
											title="Group stage: {completion.groups.done}/{completion.groups.total} predictions"
										>
											<span
												class="w-2 h-2 rounded-full {dotColor(
													completion.groups.done,
													completion.groups.total
												)}"
												aria-hidden="true"
											></span>
											<span class="text-base-content/60">{completion.groups.done}/{completion.groups.total}</span>
										</span>
										<!-- Bracket dot -->
										<span
											class="flex items-center gap-0.5"
											title="Bracket: {completion.bracket.done}/{completion.bracket.total} picks"
										>
											<span
												class="w-2 h-2 rounded-full {dotColor(
													completion.bracket.done,
													completion.bracket.total
												)}"
												aria-hidden="true"
											></span>
											<span class="text-base-content/60">{completion.bracket.done}/{completion.bracket.total}</span>
										</span>
										<!-- Bonus dot -->
										<span
											class="flex items-center gap-0.5"
											title="Bonus: {completion.bonus.done}/{completion.bonus.total} answered"
										>
											<span
												class="w-2 h-2 rounded-full {dotColor(
													completion.bonus.done,
													completion.bonus.total
												)}"
												aria-hidden="true"
											></span>
											<span class="text-base-content/60">{completion.bonus.done}/{completion.bonus.total}</span>
										</span>
									</div>
								{:else}
									<span class="text-xs text-base-content/30">—</span>
								{/if}
							</td>

							<!-- Updated (hidden < md) -->
							<td class="hidden md:table-cell">
								<span class="text-xs text-base-content/60">{formatUpdated(entry.updated_at)}</span>
							</td>

							<!-- Actions -->
							<td class="text-right">
								<div class="flex items-center justify-end gap-1">
									<!-- Open (desktop: always visible; hidden on withdrawn) -->
									{#if !isWithdrawn}
										<button
											type="button"
											class="btn btn-ghost btn-sm"
											on:click={() => openEntry(entry.id)}
											aria-label="Open {entry.display_name}"
										>
											Open
											<svg
												class="w-4 h-4"
												fill="none"
												viewBox="0 0 24 24"
												stroke="currentColor"
												stroke-width="2"
												aria-hidden="true"
											>
												<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
											</svg>
										</button>
									{/if}

									<!-- Desktop secondary actions (hidden on mobile) -->
									{#if !isWithdrawn}
										<button
											type="button"
											class="btn btn-ghost btn-sm hidden md:inline-flex"
											disabled={noPredictions || actionBusy === entry.id + ':dup'}
											title={noPredictions
												? 'Nothing to duplicate — add predictions first'
												: 'Duplicate this entry'}
											on:click={() => handleDuplicate(entry.id)}
										>
											{#if actionBusy === entry.id + ':dup'}
												<span class="loading loading-spinner loading-xs"></span>
											{:else}
												Copy
											{/if}
										</button>
										<button
											type="button"
											class="btn btn-ghost btn-sm text-error/70 hidden md:inline-flex"
											disabled={actionBusy !== null}
											on:click={() => (confirmWithdrawId = entry.id)}
										>
											Withdraw
										</button>
									{:else}
										<!-- Reinstate (desktop) -->
										<button
											type="button"
											class="btn btn-ghost btn-sm hidden md:inline-flex"
											disabled={actionBusy === entry.id + ':reinstate'}
											on:click={() => handleReinstate(entry.id)}
										>
											{#if actionBusy === entry.id + ':reinstate'}
												<span class="loading loading-spinner loading-xs"></span>
											{:else}
												Reinstate
											{/if}
										</button>
									{/if}

									<!-- Mobile ⋯ overflow menu (<details> dropdown) -->
									<details class="relative md:hidden">
										<summary
											class="btn btn-ghost btn-sm btn-square list-none"
											aria-label="More actions for {entry.display_name}"
										>
											<svg
												class="w-4 h-4"
												fill="currentColor"
												viewBox="0 0 20 20"
												aria-hidden="true"
											>
												<circle cx="10" cy="4" r="1.5" />
												<circle cx="10" cy="10" r="1.5" />
												<circle cx="10" cy="16" r="1.5" />
											</svg>
										</summary>
										<ul
											class="absolute right-0 mt-1 min-w-36 bg-base-100 border border-base-300/60 rounded-xl shadow-lg z-20 overflow-hidden"
										>
											{#if !isWithdrawn}
												<li>
													<button
														type="button"
														class="w-full px-4 py-2.5 text-sm text-left hover:bg-base-200 disabled:opacity-40 disabled:cursor-not-allowed"
														disabled={noPredictions || actionBusy !== null}
														title={noPredictions
															? 'Nothing to duplicate — add predictions first'
															: undefined}
														on:click={() => handleDuplicate(entry.id)}
													>
														Copy / Duplicate
													</button>
												</li>
												<li>
													<button
														type="button"
														class="w-full px-4 py-2.5 text-sm text-left text-error/80 hover:bg-base-200 disabled:opacity-40"
														disabled={actionBusy !== null}
														on:click={() => (confirmWithdrawId = entry.id)}
													>
														Withdraw
													</button>
												</li>
											{:else}
												<li>
													<button
														type="button"
														class="w-full px-4 py-2.5 text-sm text-left hover:bg-base-200 disabled:opacity-40"
														disabled={actionBusy !== null}
														on:click={() => handleReinstate(entry.id)}
													>
														Reinstate
													</button>
												</li>
											{/if}
											{#if !isWithdrawn}
												<li>
													<button
														type="button"
														class="w-full px-4 py-2.5 text-sm text-left hover:bg-base-200"
														on:click={() => goto(`/entries/${entry.id}?print=1`)}
													>
														🖨 Print
													</button>
												</li>
											{/if}
										</ul>
									</details>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<!--
	/entries — list view of every prediction entry the user owns.

	Tapping a row navigates to /entries/{id} (full-page replacement, not
	a modal). The destination page reads the URL param and scopes the
	stores accordingly. Status badges reuse the same 4-state vocabulary
	as the wizard via $lib/utils/entryStatusBadge.

	Scope (per plan i-want-to-create-fluttering-quokka.md):
	  - Status badges only (no fixtures done/total counts)
	  - "Open" is the sole row action — Submit/Edit/Rename/Duplicate
	    stay inside the wizard for this iteration
	  - Renders unconditionally, even when the user has only one entry
-->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		entries,
		entriesLoading,
		entriesError,
		editableEntries,
		submittedEntries,
		loadEntries
	} from '$stores/entries';
	import { isPhase1Locked } from '$stores/phase';
	import {
		entryUiStatus,
		entryStatusBadge,
		entryStatusDot,
		shouldShowPrizeModifier
	} from '$lib/utils/entryStatusBadge';

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
</script>

<svelte:head>
	<title>Entries - Predictor v2</title>
</svelte:head>

<div class="container mx-auto px-4 py-6 max-w-4xl">
	<header class="mb-6">
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
					An entry will be created for you automatically. If you don't see one,
					contact your competition admin.
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
						<th class="hidden md:table-cell">Updated</th>
						<th class="text-right">Action</th>
					</tr>
				</thead>
				<tbody>
					{#each $entries as entry (entry.id)}
						{@const ui = entryUiStatus(entry, { deadlinePassed })}
						{@const badge = entryStatusBadge(ui)}
						{@const showNoPrize = shouldShowPrizeModifier(entry, ui)}
						<tr
							class="cursor-pointer hover:bg-base-300/40"
							on:click={() => openEntry(entry.id)}
						>
							<td>
								<div class="flex items-center gap-2 min-w-0">
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
								</div>
							</td>
							<td class="hidden sm:table-cell">
								<span class="text-xs font-mono text-base-content/60">{entry.reference}</span>
							</td>
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
							<td class="hidden md:table-cell">
								<span class="text-xs text-base-content/60">{formatUpdated(entry.updated_at)}</span>
							</td>
							<td class="text-right">
								<button
									type="button"
									class="btn btn-ghost btn-sm"
									on:click|stopPropagation={() => openEntry(entry.id)}
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
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M9 5l7 7-7 7"
										/>
									</svg>
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

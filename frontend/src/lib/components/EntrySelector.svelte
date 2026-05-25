<!--
	EntrySelector
	==============================================================
	Wizard entry chooser. In single-entry mode it collapses to a
	status pill. In multi-entry mode it opens a dropdown listing
	every entry + status badge, with footer actions for create /
	duplicate / rename gated on competition settings.

	Reads `entries`, `activeEntry`, `entrySettings`, `isSingleEntryMode`
	from $stores/entries. Dispatches: select { entryId }, create,
	duplicate, rename. Rename/duplicate/create are handled by the parent.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import {
		entries,
		activeEntry,
		entrySettings,
		isSingleEntryMode,
		setActiveEntry
	} from '$stores/entries';
	import { currentPhase } from '$stores/phase';
	import { computeDisplayStatus, type EntryStatus, type Entry } from '$lib/types/entry';
	import type { PredictionPhase } from '$types';

	const dispatch = createEventDispatcher<{
		select: { entryId: string };
		create: void;
		duplicate: void;
		rename: void;
	}>();

	let open = false;

	$: maxEntries = $entrySettings?.max_entries_per_user ?? 1;
	$: canCreate = $entries.length < maxEntries;
	$: canDuplicate =
		$entrySettings?.allow_duplicate_from_existing === true && canCreate && !!$activeEntry;
	$: canRename = $entrySettings?.allow_user_rename === true && !!$activeEntry;

	function badgeClass(status: EntryStatus): string {
		switch (status) {
			case 'submitted':
				return 'badge-success';
			case 'withdrawn':
				return 'badge-error';
			case 'draft':
			default:
				return 'badge-ghost';
		}
	}

	function entryStatus(entry: Entry): EntryStatus {
		return computeDisplayStatus(entry, $currentPhase as PredictionPhase);
	}

	function handleToggle() {
		if ($isSingleEntryMode) return;
		open = !open;
	}

	function handleSelect(entry: Entry) {
		if (entry.id !== $activeEntry?.id) {
			setActiveEntry(entry.id);
			dispatch('select', { entryId: entry.id });
		}
		open = false;
	}

	function handleCreate() {
		open = false;
		dispatch('create');
	}
	function handleDuplicate() {
		open = false;
		dispatch('duplicate');
	}
	function handleRename() {
		open = false;
		dispatch('rename');
	}

	function clickOutside(node: HTMLElement) {
		function handle(e: MouseEvent) {
			if (open && !node.contains(e.target as Node)) open = false;
		}
		document.addEventListener('mousedown', handle);
		return { destroy: () => document.removeEventListener('mousedown', handle) };
	}
</script>

<div class="relative inline-flex items-center" use:clickOutside>
	{#if !$activeEntry}
		<div class="flex items-center gap-2">
			<span class="text-xs uppercase tracking-wider text-base-content/50">No entry</span>
			{#if canCreate}
				<button class="btn btn-xs btn-outline" type="button" on:click={handleCreate}>+ New entry</button>
			{/if}
		</div>
	{:else}
		<button
			class="flex items-center gap-2 px-3 py-2 rounded-lg bg-base-300/40 border border-base-300 {$isSingleEntryMode ? 'cursor-default' : 'hover:border-base-content/30'}"
			type="button"
			aria-haspopup={$isSingleEntryMode ? undefined : 'menu'}
			aria-expanded={open}
			on:click={handleToggle}
		>
			<span class="text-[10px] uppercase tracking-wider text-base-content/40">Entry</span>
			<span class="font-semibold text-sm">{$activeEntry.display_name}</span>
			<span class="badge badge-sm {badgeClass(entryStatus($activeEntry))}">{entryStatus($activeEntry).toUpperCase()}</span>
			{#if !$isSingleEntryMode}<span class="text-xs text-base-content/50">▾</span>{/if}
		</button>

		{#if open && !$isSingleEntryMode}
			<div class="absolute top-full left-0 mt-2 z-30 w-72 rounded-xl bg-base-200 border border-base-300 shadow-lg overflow-hidden" role="menu">
				<ul class="max-h-72 overflow-y-auto">
					{#each $entries as entry (entry.id)}
						<li>
							<button
								type="button"
								class="w-full flex items-center gap-2 px-3 py-2.5 text-left border-b border-base-300/50 hover:bg-base-300/40 {entry.id === $activeEntry.id ? 'bg-base-300/60' : ''}"
								on:click={() => handleSelect(entry)}
								role="menuitem"
							>
								<span class="font-semibold text-sm flex-1 truncate">{entry.display_name}</span>
								<span class="text-[10px] font-mono text-base-content/40">{entry.reference}</span>
								<span class="badge badge-xs {badgeClass(entryStatus(entry))}">{entryStatus(entry).toUpperCase()}</span>
							</button>
						</li>
					{/each}
				</ul>
				<div class="flex flex-wrap gap-2 p-3 border-t border-base-300 bg-base-300/20">
					{#if canCreate}
						<button class="btn btn-xs btn-outline" type="button" on:click={handleCreate}>+ New entry</button>
					{/if}
					{#if canDuplicate}
						<button class="btn btn-xs btn-outline" type="button" on:click={handleDuplicate}>Duplicate</button>
					{/if}
					{#if canRename}
						<button class="btn btn-xs btn-outline" type="button" on:click={handleRename}>Rename</button>
					{/if}
				</div>
			</div>
		{/if}
	{/if}
</div>

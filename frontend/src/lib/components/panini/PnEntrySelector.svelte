<!--
	PnEntrySelector
	==============================================================
	Wizard-hero entry chooser. In single-entry mode the dropdown
	collapses to a status pill (the wizard looks identical to the
	pre-Task-E single-entry surface). In multi-entry mode it opens
	a menu listing every entry + status chip, with footer actions
	for create / duplicate / rename gated on competition settings.

	State: reads `entries`, `activeEntry`, `entrySettings`,
	`isSingleEntryMode` from `$stores/entries`. Dispatches:
	  - `select` { entryId }
	  - `create`
	  - `duplicate`
	  - `rename`

	Rename / duplicate are handled by the parent — the selector
	is a controller, not a transaction owner.
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
	let triggerEl: HTMLButtonElement | undefined;

	$: maxEntries = $entrySettings?.max_entries_per_user ?? 1;
	$: canCreate = $entries.length < maxEntries;
	$: canDuplicate =
		$entrySettings?.allow_duplicate_from_existing === true && canCreate && !!$activeEntry;
	$: canRename = $entrySettings?.allow_user_rename === true && !!$activeEntry;

	function statusClass(status: EntryStatus): string {
		switch (status) {
			case 'submitted':
			case 'locked':
				return 'pn-tag got';
			case 'ready':
				return 'pn-tag gold';
			case 'disabled':
				return 'pn-tag red';
			case 'withdrawn':
				return 'pn-tag muted';
			default:
				return 'pn-tag';
		}
	}

	function statusLabel(status: EntryStatus): string {
		return status.toUpperCase();
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

	function handleOutsideClick(event: MouseEvent) {
		if (!open) return;
		const target = event.target as Node | null;
		if (triggerEl && target && !triggerEl.parentElement?.contains(target)) {
			open = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && open) {
			open = false;
			triggerEl?.focus();
		}
	}
</script>

<svelte:window on:click={handleOutsideClick} on:keydown={handleKeydown} />

<div class="pn-entry-selector" class:single={$isSingleEntryMode}>
	{#if !$activeEntry}
		<div class="empty">
			<span class="lbl">No entry</span>
			{#if canCreate}
				<button class="pn-btn ghost sm" type="button" on:click={handleCreate}>
					+ New entry
				</button>
			{/if}
		</div>
	{:else}
		<button
			bind:this={triggerEl}
			class="trigger"
			class:disabled={$isSingleEntryMode}
			type="button"
			aria-haspopup={$isSingleEntryMode ? undefined : 'menu'}
			aria-expanded={open}
			on:click={handleToggle}
		>
			<span class="lbl">Entry</span>
			<span class="name">{$activeEntry.display_name}</span>
			<span class={statusClass(entryStatus($activeEntry))}>
				{statusLabel(entryStatus($activeEntry))}
			</span>
			{#if !$isSingleEntryMode}
				<span class="caret" aria-hidden="true">▾</span>
			{/if}
		</button>

		{#if open && !$isSingleEntryMode}
			<div class="menu" role="menu">
				<ul class="entry-list">
					{#each $entries as entry (entry.id)}
						<li>
							<button
								type="button"
								class="row"
								class:active={entry.id === $activeEntry.id}
								on:click={() => handleSelect(entry)}
								role="menuitem"
							>
								<span class="row-name">{entry.display_name}</span>
								<span class="row-ref">{entry.reference}</span>
								<span class={statusClass(entryStatus(entry))}>
									{statusLabel(entryStatus(entry))}
								</span>
							</button>
						</li>
					{/each}
				</ul>
				<div class="actions">
					{#if canCreate}
						<button class="pn-btn ghost sm" type="button" on:click={handleCreate}>
							+ New entry
						</button>
					{/if}
					{#if canDuplicate}
						<button class="pn-btn ghost sm" type="button" on:click={handleDuplicate}>
							Duplicate
						</button>
					{/if}
					{#if canRename}
						<button class="pn-btn ghost sm" type="button" on:click={handleRename}>
							Rename
						</button>
					{/if}
				</div>
			</div>
		{/if}
	{/if}
</div>

<style>
	.pn-entry-selector {
		position: relative;
		display: flex;
		align-items: center;
	}

	.empty {
		display: inline-flex;
		align-items: center;
		gap: 10px;
	}

	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		padding: 8px 12px;
		background: var(--paper);
		border: 2px solid var(--ink);
		box-shadow: 3px 3px 0 var(--ink);
		font-family: var(--body);
		color: var(--ink);
		cursor: pointer;
		transition: transform 0.12s ease, box-shadow 0.12s ease;
		min-height: 38px;
	}
	.trigger:hover:not(.disabled) {
		transform: translate(-1px, -1px);
		box-shadow: 4px 4px 0 var(--ink);
	}
	.trigger.disabled {
		cursor: default;
	}

	.lbl {
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: 0.10em;
		text-transform: uppercase;
		color: var(--ink-3);
	}

	.name {
		font-family: var(--display2);
		font-weight: 700;
		font-size: 14px;
		color: var(--ink);
	}

	.caret {
		font-size: 12px;
		color: var(--ink-2);
		margin-left: 2px;
	}

	/* Status chip overrides */
	.pn-tag.muted {
		background: var(--paper-3);
		color: var(--ink-3);
		border-color: var(--ink-3);
	}

	/* Sized-down button for menu actions */
	:global(.pn-entry-selector .pn-btn.sm) {
		padding: 6px 12px;
		font-size: 11px;
		box-shadow: 2px 2px 0 var(--ink);
	}

	.menu {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		min-width: 280px;
		max-width: 360px;
		background: var(--paper);
		border: 2px solid var(--ink);
		box-shadow: 5px 5px 0 var(--ink);
		z-index: 30;
	}

	.entry-list {
		list-style: none;
		margin: 0;
		padding: 0;
		max-height: 280px;
		overflow-y: auto;
	}

	.row {
		display: grid;
		grid-template-columns: 1fr auto auto;
		align-items: center;
		gap: 10px;
		width: 100%;
		padding: 10px 12px;
		background: var(--paper);
		border: none;
		border-bottom: 1px solid var(--paper-3);
		font-family: var(--body);
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.row:hover {
		background: var(--paper-2);
	}
	.row.active {
		background: var(--paper-3);
	}
	.row-name {
		font-family: var(--display2);
		font-weight: 700;
		font-size: 13px;
	}
	.row-ref {
		font-family: var(--mono);
		font-size: 10px;
		color: var(--ink-3);
		letter-spacing: 0.06em;
	}

	.actions {
		display: flex;
		gap: 8px;
		padding: 10px 12px;
		border-top: 2px solid var(--ink);
		background: var(--paper-2);
		flex-wrap: wrap;
	}

	/* Single-entry mode: cleaner — drop the trigger affordance */
	.pn-entry-selector.single .trigger {
		box-shadow: none;
		background: transparent;
		border: none;
		padding: 4px 0;
	}
</style>

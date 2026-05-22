<!--
	SheetSelector — dropdown to switch between prediction sheets.

	Replaces the legacy `EntrySelector.svelte` on the predictions page.
	The old file stays available for other pages (dashboard, etc.) until
	Prompt 14's cleanup pass.

	Trigger:
		[● status-dot]  ENTRY  Entry-name  [STATUS-BADGE]  ▾

	Panel rows (one per sheet):
		[● dot]  Sheet name  [STATUS]  48/72*  ✎
		* completion count only shown for the active sheet — the
		  `predictionsByFixture` store is scoped to the active entry,
		  so we don't have a cheap way to compute per-entry counts
		  for inactive rows. Backend extension is the right fix.

	Footer: "+ New Sheet" (when `allow_user_rename` settings permit a
	  new entry AND count < max_entries_per_user AND deadline hasn't
	  passed).

	Per the resolved decisions in `prompt-1-i-need-eventual-thimble.md`:
	  - NO per-sheet color (status color is the only encoding)
	  - NO ✕ delete button (admins are the sole irreversible actors)

	Dispatches:
	  - `create`             — when user taps "+ New Sheet"
	  - `rename` { entryId } — when user taps ✎ on any row

	Parent (`+page.svelte`) handles the API call + store refresh for
	both. Row selection is internal: tapping a row calls
	`setActiveEntry()` directly and closes the dropdown.
-->
<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import {
		entries,
		activeEntry,
		activeEntryId,
		setActiveEntry,
		entrySettings
	} from '$lib/stores/entries';
	import { isPhase1Locked } from '$lib/stores/phase';
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';

	/**
	 * Active sheet's fixture-completion progress (done / total). Optional:
	 * parent computes from the predictions store, passes down. Inactive rows
	 * have no count.
	 */
	export let activeProgress: { done: number; total: number } | null = null;

	const dispatch = createEventDispatcher<{
		create: void;
		rename: { entryId: string };
	}>();

	type UiStatus = 'draft' | 'locked' | 'scored' | 'missed';

	function uiStatusFor(entry: Entry, deadlinePassed: boolean): UiStatus {
		const s = computeDisplayStatus(entry, 'phase_1');
		if (s === 'withdrawn') return 'missed';
		if (s === 'submitted') return deadlinePassed ? 'scored' : 'locked';
		// status === 'draft'
		return deadlinePassed ? 'missed' : 'draft';
	}

	// Badge label + DaisyUI semantic class. DRAFT is plain (in-progress
	// default); the three "final" states carry a glyph for at-a-glance
	// recognition without relying on color alone (a11y win for color-blind
	// users who can't easily distinguish green from amber).
	const BADGE: Record<UiStatus, { label: string; class: string }> = {
		draft: { label: 'DRAFT', class: 'badge-warning' },
		locked: { label: '🔒 LOCKED', class: 'badge-success' },
		scored: { label: '✓ SCORED', class: 'badge-success' },
		missed: { label: '✗ NOT SUBMITTED', class: 'badge-error' }
	};

	const DOT_FILL: Record<UiStatus, string> = {
		draft: 'bg-warning',
		locked: 'bg-success',
		scored: 'bg-success',
		missed: 'bg-error'
	};

	let open = false;
	let triggerEl: HTMLButtonElement;
	let panelEl: HTMLDivElement;

	function toggleOpen() {
		open = !open;
	}

	// Outside-click closes the dropdown. Mounted on window to catch every
	// click in capture order; bail early when the click is inside the
	// trigger or panel.
	function handleDocClick(e: MouseEvent) {
		if (!open) return;
		const t = e.target as Node;
		if (triggerEl?.contains(t) || panelEl?.contains(t)) return;
		open = false;
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) open = false;
	}

	onMount(() => {
		window.addEventListener('click', handleDocClick);
		window.addEventListener('keydown', handleKey);
		return () => {
			window.removeEventListener('click', handleDocClick);
			window.removeEventListener('keydown', handleKey);
		};
	});

	function handleRowTap(entryId: string) {
		setActiveEntry(entryId);
		open = false;
	}

	function handleRename(entryId: string, ev: MouseEvent) {
		ev.stopPropagation();
		dispatch('rename', { entryId });
		open = false;
	}

	function handleCreate() {
		dispatch('create');
		open = false;
	}

	$: deadlinePassed = $isPhase1Locked;
	$: canCreate = $entrySettings
		? $entries.length < $entrySettings.max_entries_per_user
		: false;
	$: canRename = $entrySettings?.allow_user_rename ?? false;
	$: activeUi = $activeEntry ? uiStatusFor($activeEntry, deadlinePassed) : null;
</script>

<div class="relative inline-block">
	<!-- Trigger -->
	{#if $activeEntry && activeUi}
		<button
			bind:this={triggerEl}
			type="button"
			class="flex items-center gap-2 px-3 py-2 rounded-lg bg-base-300/40 border border-base-content/10 hover:bg-base-300/60 min-h-11 max-w-full text-left"
			aria-haspopup="listbox"
			aria-expanded={open}
			on:click={toggleOpen}
		>
			<span
				class="w-2.5 h-2.5 rounded-full {DOT_FILL[activeUi]} flex-shrink-0"
				aria-hidden="true"
			></span>
			<span class="text-[10px] uppercase tracking-wider opacity-50 font-semibold">Entry</span>
			<span class="font-semibold truncate max-w-[8rem] sm:max-w-[12rem]"
				>{$activeEntry.display_name}</span
			>
			<span class="badge badge-sm {BADGE[activeUi].class}">{BADGE[activeUi].label}</span>
			<svg
				class="w-4 h-4 opacity-60 flex-shrink-0 transition-transform"
				class:rotate-180={open}
				viewBox="0 0 20 20"
				fill="currentColor"
				aria-hidden="true"
			>
				<path
					fill-rule="evenodd"
					d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
					clip-rule="evenodd"
				/>
			</svg>
		</button>
	{/if}

	<!-- Dropdown panel -->
	{#if open}
		<div
			bind:this={panelEl}
			class="absolute top-full left-0 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl bg-base-200 border border-base-content/10 shadow-lg overflow-hidden z-30"
		>
			<ul class="max-h-72 overflow-y-auto py-1">
				{#each $entries as e (e.id)}
					{@const ui = uiStatusFor(e, deadlinePassed)}
					{@const isActive = e.id === $activeEntryId}
					<li class="flex items-center gap-1 px-1.5 py-0.5">
						<!-- Row-select button (fills most of the row) -->
						<button
							type="button"
							class="flex-1 flex items-center gap-2 min-w-0 text-left px-2 py-2 rounded-lg hover:bg-base-300/40 min-h-11 {isActive
								? 'bg-base-300/30'
								: ''}"
							on:click={() => handleRowTap(e.id)}
							aria-current={isActive ? 'true' : undefined}
						>
							<span
								class="w-2.5 h-2.5 rounded-full {DOT_FILL[ui]} flex-shrink-0"
								aria-hidden="true"
							></span>
							<span class="font-medium truncate flex-1">{e.display_name}</span>
							<span class="badge badge-xs {BADGE[ui].class} whitespace-nowrap"
								>{BADGE[ui].label}</span
							>
							{#if isActive && activeProgress}
								<span class="text-xs font-mono opacity-60 ml-1 whitespace-nowrap"
									>{activeProgress.done}/{activeProgress.total}</span
								>
							{/if}
						</button>

						<!-- Rename action (✎). Hidden once the deadline passes
						     or if competition disables user rename. -->
						{#if canRename && !deadlinePassed}
							<button
								type="button"
								class="btn btn-ghost btn-sm btn-square flex-shrink-0"
								on:click={(ev) => handleRename(e.id, ev)}
								aria-label="Rename {e.display_name}"
								title="Rename"
							>
								<span aria-hidden="true" class="text-sm">✎</span>
							</button>
						{/if}
					</li>
				{/each}
			</ul>

			<!-- Footer: + New Sheet -->
			{#if canCreate && !deadlinePassed}
				<div class="border-t border-base-content/10 p-1">
					<button
						type="button"
						class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium hover:bg-base-300/40 min-h-11"
						on:click={handleCreate}
					>
						<span class="text-lg leading-none">+</span>
						<span>New Sheet</span>
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

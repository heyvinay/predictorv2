<script lang="ts">
	/** Entry switcher — V4 Results. Floating popover pattern: a single
	 *  chip displays the active entry; clicking it opens a list of all
	 *  entries beneath. Parent renders this only for multi-entry users
	 *  (spec: single-entry users never see a switcher). Post-deadline
	 *  only submitted entries are visible (page gate). */
	import type { Entry } from '$lib/types/entry';
	import type { EntryRankInfo } from '$lib/types/results';

	export let entries: Entry[];
	export let selectedId: string;
	export let rankByEntry: Map<string, EntryRankInfo>;
	export let onSelect: (entryId: string) => void;

	let open = false;
	let containerEl: HTMLDivElement;

	function ordinal(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}

	$: active = entries.find((e) => e.id === selectedId) ?? entries[0];
	$: activeRank = active ? rankByEntry.get(active.id) : undefined;

	function pick(id: string) {
		onSelect(id);
		open = false;
	}

	function handleWindowClick(event: MouseEvent) {
		if (!open || !containerEl) return;
		if (!containerEl.contains(event.target as Node)) open = false;
	}

	function handleKey(event: KeyboardEvent) {
		if (open && event.key === 'Escape') open = false;
	}
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleKey} />

<div bind:this={containerEl} class="relative inline-block">
	<button
		type="button"
		aria-haspopup="listbox"
		aria-expanded={open}
		class="inline-flex items-center gap-2.5 whitespace-nowrap rounded-2xl border border-primary/55 bg-primary/10 px-3 py-1.5 text-left transition-colors hover:bg-primary/15"
		on:click={() => (open = !open)}
	>
		<span class="flex flex-col items-start leading-tight">
			<span class="font-display text-[12.5px] text-base-content">{active?.display_name}</span>
			{#if activeRank}
				<span class="text-[10px] font-bold leading-[1.15]">
					<span class="text-primary">{ordinal(activeRank.position)}</span>
					<span class="text-base-content/55">· {activeRank.total_points} pts</span>
				</span>
			{/if}
		</span>
		<span
			class="text-[10px] text-base-content/55 transition-transform {open ? 'rotate-180' : ''}"
			aria-hidden="true">▾</span
		>
	</button>

	{#if open}
		<div
			class="absolute left-0 top-[calc(100%+6px)] z-20 flex max-h-[60vh] min-w-[200px] flex-col overflow-y-auto rounded-box border border-base-300/70 bg-base-200 p-1 shadow-card"
			role="listbox"
			aria-label="Switch entry"
		>
			{#each entries as e (e.id)}
				{@const rank = rankByEntry.get(e.id)}
				{@const isActive = e.id === selectedId}
				<button
					type="button"
					role="option"
					aria-selected={isActive}
					class="flex items-center justify-between gap-3 whitespace-nowrap rounded-btn px-2.5 py-1.5 text-left transition-colors {isActive
						? 'bg-primary/15'
						: 'hover:bg-base-300/40'}"
					on:click={() => pick(e.id)}
				>
					<span class="flex flex-col leading-tight">
						<span
							class="font-display text-[12.5px] {isActive
								? 'text-base-content'
								: 'text-base-content/85'}">{e.display_name}</span
						>
						{#if rank}
							<span class="text-[10px] font-bold leading-[1.15]">
								<span class={isActive ? 'text-primary' : 'text-base-content/70'}
									>{ordinal(rank.position)}</span
								>
								<span class="text-base-content/45">· {rank.total_points} pts</span>
							</span>
						{/if}
					</span>
					{#if isActive}
						<span class="text-[11px] font-bold text-primary" aria-hidden="true">✓</span>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>

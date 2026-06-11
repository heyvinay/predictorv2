<script lang="ts">
	/** Merged entry-switcher + points-summary pill — Results page top
	 *  strip. Left segment surfaces the person/entry identity and (for
	 *  multi-entry users) acts as the dropdown switcher. Right segments
	 *  show GROUP / KNOCKOUT / TOTAL with optional bonus suffixes.
	 *
	 *  Single-entry users get the same shell minus the caret + dropdown
	 *  (the label is still informative so the page never reads as
	 *  ambiguous about whose card it is).
	 */
	import type { Entry } from '$lib/types/entry';
	import type { EntryRankInfo } from '$lib/types/results';

	export let entries: Entry[];
	export let selectedId: string;
	export let rankByEntry: Map<string, EntryRankInfo>;
	export let onSelect: (entryId: string) => void;
	/** Logged-in user's display name — always surfaced as the prefix
	 *  ("Vinay Aarohi · Entry 7") per the cross-app naming rule. */
	export let userName: string;
	export let groupTotal: number;
	export let knockoutTotal: number;
	export let bonusGroup = 0;
	export let bonusKnockout = 0;

	let open = false;
	let containerEl: HTMLDivElement;

	function ordinal(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}

	$: multiEntry = entries.length > 1;
	$: active = entries.find((e) => e.id === selectedId) ?? entries[0];
	$: activeRank = active ? rankByEntry.get(active.id) : undefined;
	$: grandTotal = groupTotal + knockoutTotal + bonusGroup + bonusKnockout;
	$: identityLabel = multiEntry
		? `${userName} — ${active?.display_name ?? ''}`
		: userName;

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

<div
	bind:this={containerEl}
	class="relative flex w-full flex-wrap items-stretch gap-0 overflow-visible rounded-btn border border-primary/45 bg-base-200"
>
	<!-- Left segment: identity + (optional) dropdown trigger -->
	<button
		type="button"
		aria-haspopup={multiEntry ? 'listbox' : undefined}
		aria-expanded={multiEntry ? open : undefined}
		disabled={!multiEntry}
		class="flex flex-1 items-center gap-2 rounded-l-btn bg-primary/10 px-3 py-1.5 text-left transition-colors disabled:cursor-default {multiEntry
			? 'hover:bg-primary/15'
			: ''}"
		on:click={() => multiEntry && (open = !open)}
	>
		<span class="flex min-w-0 flex-col leading-tight">
			<span class="truncate font-display text-[12.5px] font-bold text-base-content"
				>{identityLabel}</span
			>
			{#if activeRank}
				<span class="text-[10px] font-bold leading-[1.15]">
					<span class="text-primary">{ordinal(activeRank.position)}</span>
					<span class="text-base-content/55">· {activeRank.total_points} pts</span>
				</span>
			{/if}
		</span>
		{#if multiEntry}
			<span
				class="ml-auto text-[10px] text-base-content/55 transition-transform {open
					? 'rotate-180'
					: ''}"
				aria-hidden="true">▾</span
			>
		{/if}
	</button>

	<!-- Right segments: Group / Knockout / Total -->
	<div class="flex items-center gap-1.5 px-2.5 py-1">
		<div class="flex items-baseline gap-1.5 pr-2 sm:pr-3">
			<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
				>Group</span
			>
			<span class="font-display text-[13px] leading-none text-base-content">{groupTotal}</span>
			{#if bonusGroup > 0}
				<span class="text-[9px] font-bold leading-none text-base-content/55">+{bonusGroup}b</span>
			{/if}
		</div>
		<div class="flex items-baseline gap-1.5 border-l border-base-300/40 px-2 sm:px-3">
			<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
				>Knockout</span
			>
			<span class="font-display text-[13px] leading-none text-base-content">{knockoutTotal}</span>
			{#if bonusKnockout > 0}
				<span class="text-[9px] font-bold leading-none text-base-content/55"
					>+{bonusKnockout}b</span
				>
			{/if}
		</div>
		<div class="flex items-baseline gap-1.5 border-l border-base-300/40 pl-2 sm:pl-3">
			<span class="text-[9px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
				>Total</span
			>
			<span class="font-display text-[14px] leading-none text-primary">{grandTotal}</span>
		</div>
	</div>

	{#if open && multiEntry}
		<div
			class="absolute left-0 top-[calc(100%+6px)] z-20 flex max-h-[60vh] min-w-[240px] flex-col overflow-y-auto rounded-box border border-base-300/70 bg-base-200 p-1 shadow-card"
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
							class="font-display text-[12.5px] font-bold {isActive
								? 'text-base-content'
								: 'text-base-content/85'}">{userName} — {e.display_name}</span
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

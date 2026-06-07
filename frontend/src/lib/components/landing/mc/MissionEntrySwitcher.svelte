<!--
  MissionEntrySwitcher — Instagram-stories-style horizontal pill row.
  Mockup-original (no upstream equivalent — upstream is single-entry).

  Each pill = circular avatar ring (initials) + stacked name + rank·pts.
  Active pill: gold ring glow + primary-soft fill.
  Best (lowest-rank) pill: gold ★ overlay on avatar ring.
  DRAFT entries: amber DRAFT chip next to name.

  Scrollbar hidden; horizontal scroll on mobile. Touch-friendly.
-->
<script lang="ts">
	import { entries, activeEntryId, setActiveEntry } from '$stores/entries';
	import { bestEntryId, myLeaderboardByEntryId } from '$stores/missionDerived';
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';

	function initialsOf(entry: Entry): string {
		const ref = entry.reference || '';
		const trimmed = ref.trim();
		if (!trimmed) return '·';
		const parts = trimmed.split(/\s+/);
		if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
		return trimmed.slice(0, 2).toUpperCase();
	}

	function ordSuffix(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return s[(v - 20) % 10] || s[v] || s[0];
	}

	function rankLabel(entryId: string): string {
		const row = $myLeaderboardByEntryId.get(entryId);
		if (!row) return 'no rank yet';
		return `${row.position}${ordSuffix(row.position)} · ${row.total_points} pts`;
	}

	function isDraft(entry: Entry): boolean {
		return computeDisplayStatus(entry, 'phase_1') === 'draft';
	}

	$: visibleEntries = $entries.filter((e) => !e.is_disabled && !e.withdrawn_at);
</script>

{#if visibleEntries.length > 1}
	<div
		class="flex gap-3 overflow-x-auto py-1 px-0.5 mb-4 -mx-2 px-2"
		style="scrollbar-width: none; -webkit-overflow-scrolling: touch;"
	>
		{#each visibleEntries as entry (entry.id)}
			{@const isActive = entry.id === $activeEntryId}
			{@const isBest = entry.id === $bestEntryId}
			{@const draft = isDraft(entry)}
			<button
				type="button"
				class="flex items-center gap-3 px-4 py-2 rounded-full border whitespace-nowrap transition flex-none hover:-translate-y-px"
				style:background={isActive ? 'rgba(212,175,55,0.16)' : 'var(--b2, #1C2541)'}
				style:border-color={isActive ? 'rgba(212,175,55,0.55)' : 'rgba(42,53,82,0.65)'}
				style:box-shadow={isActive ? '0 0 0 1px rgba(212,175,55,0.30)' : 'none'}
				on:click={() => setActiveEntry(entry.id)}
				aria-pressed={isActive}
			>
				<span class="relative flex-none">
					<span
						class="w-10 h-10 rounded-full grid place-items-center font-display font-extrabold text-sm"
						style:background={isActive ? 'rgba(212,175,55,0.18)' : 'var(--b3, #2A3552)'}
						style:color={isActive ? 'var(--p, #D4AF37)' : 'rgba(226,232,240,0.72)'}
						style:box-shadow={isActive ? '0 0 0 2px var(--b2, #1C2541), 0 0 0 4px var(--p, #D4AF37)' : 'none'}
					>
						{initialsOf(entry)}
					</span>
					{#if isBest}
						<span
							class="absolute -top-1.5 -right-1.5 grid place-items-center w-4 h-4 rounded-full text-[10px] text-primary"
							style:background="var(--b1, #0B1329)"
							style:box-shadow="0 0 0 1px rgba(212,175,55,0.5)"
						>
							★
						</span>
					{/if}
				</span>
				<span class="flex flex-col leading-tight items-start">
					<span class="text-sm font-bold text-base-content flex items-center gap-1.5">
						{entry.reference}
						{#if draft}
							<span
								class="text-[9px] font-bold uppercase tracking-[0.06em] px-1.5 py-0.5 rounded-full"
								style:background="rgba(217,119,6,0.20)"
								style:color="var(--warning-text, #fbbf24)"
							>
								DRAFT
							</span>
						{/if}
					</span>
					<span class="text-[11px] text-base-content/55">
						{rankLabel(entry.id)}
					</span>
				</span>
			</button>
		{/each}
	</div>
{/if}

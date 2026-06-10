<script lang="ts">
	/** "How the rarity bonus was assigned" — the D.4 locked note plus a
	 *  four-band scale with a marker at the pick share. Parent renders
	 *  this only when the entry has a pick and the pool is available. */
	import { rarityNote } from '$lib/utils/rarityNote';

	/** Callers of the entry's outcome (incl. the entry). */
	export let n: number;
	export let total: number;
	/** Rarity points for that outcome (banked value when finished). */
	export let pts: number;
	export let finished: boolean;

	$: note = rarityNote({ n, total, pts, finished });
	$: sharePct = total > 0 ? (n / total) * 100 : 0;
	// Lower share → further right on the rarity scale.
	$: markerLeft = `calc(${Math.max(0, Math.min(100, 100 - sharePct))}% - 6px)`;
	$: activeBand = n <= 1 ? 3 : pts >= 5 ? 2 : pts >= 2 ? 1 : 0;

	const BANDS = [
		{ label: 'Common', note: '+0' },
		{ label: 'Uncommon', note: '+2' },
		{ label: 'Rare', note: '+6' },
		{ label: 'Only-you', note: '+10' }
	];
</script>

{#if note}
	<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
		<div class="mb-1.5 font-display text-[15px]">★ How the rarity bonus was assigned</div>
		<p class="m-0 text-[12.5px] leading-relaxed text-base-content/70">{note}</p>

		<div class="relative mt-8 flex gap-1">
			{#each BANDS as b, i (b.label)}
				<div
					class="flex flex-1 flex-col items-center gap-0.5 rounded-btn px-1 py-1.5 text-center {i ===
					activeBand
						? 'bg-primary/15 ring-1 ring-primary/50'
						: 'bg-base-300/25'}"
				>
					<span class="text-[9px] font-extrabold tracking-[0.06em] text-base-content/70">{b.label}</span>
					<span class="text-[10px] font-bold text-base-content/55">{b.note}</span>
				</div>
			{/each}
			<div class="absolute -top-6 flex flex-col items-center" style="left: {markerLeft}">
				<div
					class="whitespace-nowrap rounded-badge bg-primary px-1.5 py-px text-[9px] font-extrabold text-primary-content"
				>
					you · {Math.round(sharePct * 10) / 10}% · +{pts}
				</div>
				<div class="h-2 w-px bg-primary"></div>
			</div>
		</div>
	</div>
{/if}

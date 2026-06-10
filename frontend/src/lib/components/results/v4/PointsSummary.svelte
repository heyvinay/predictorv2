<script lang="ts">
	/** Top points-summary card — Result/Exact/Rarity/Total on ONE line.
	 *  Derived from the per-fixture points the backend computed (B.1), so
	 *  this card and the fixtures tables can never disagree. Match points
	 *  only by design (KO + winner points live on the Summary tab). */
	import type { MatchPredictionWithPoints } from '$lib/types/results';

	export let predictions: MatchPredictionWithPoints[];
	/** Stretches full-width for single-entry users (parent toggles). */
	export let fullWidth = false;

	$: scored = predictions.filter((p) => p.points != null);
	$: resultHits = scored.filter((p) => p.points!.base_kind === 'result').length;
	$: exactHits = scored.filter((p) => p.points!.base_kind === 'exact').length;
	$: rarityHits = scored.filter((p) => (p.points!.rarity ?? 0) > 0).length;
	$: resultPts = scored
		.filter((p) => p.points!.base_kind === 'result')
		.reduce((s, p) => s + p.points!.base, 0);
	$: exactPts = scored
		.filter((p) => p.points!.base_kind === 'exact')
		.reduce((s, p) => s + p.points!.base, 0);
	$: rarityPts = scored.reduce((s, p) => s + (p.points!.rarity ?? 0), 0);
	$: total = scored.reduce((s, p) => s + p.points!.total, 0);
</script>

<div
	class="flex items-stretch gap-3 rounded-box border border-base-300/60 bg-base-200 px-4 py-3 {fullWidth
		? 'w-full justify-between'
		: ''}"
>
	<div class="flex items-stretch gap-4">
		<div class="flex flex-col gap-1">
			<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
				Results<span class="text-base-content/70"> · {resultHits}</span>
			</span>
			<span class="flex items-center gap-2">
				<span
					class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-warning/20 font-display text-[10px] font-extrabold text-warning-text"
					>R</span
				>
				<span class="font-display text-[15px] text-base-content">{resultPts}</span>
			</span>
		</div>
		<div class="flex flex-col gap-1">
			<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
				Exact<span class="text-base-content/70"> · {exactHits}</span>
			</span>
			<span class="flex items-center gap-2">
				<span
					class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-success/20 font-display text-[10px] font-extrabold text-success"
					>E</span
				>
				<span class="font-display text-[15px] text-base-content">{exactPts}</span>
			</span>
		</div>
		<div class="flex flex-col gap-1">
			<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
				Rarity<span class="text-base-content/70"> · {rarityHits}</span>
			</span>
			<span class="flex items-center gap-2">
				<span
					class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-primary/20 font-display text-[10px] font-extrabold text-primary"
					>★</span
				>
				<span class="font-display text-[15px] text-base-content">{rarityPts}</span>
			</span>
		</div>
	</div>
	<div class="ml-auto flex flex-col items-end gap-1 border-l border-base-300/40 pl-4">
		<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
			>Total</span
		>
		<span class="font-display text-[22px] leading-none text-primary">{total}</span>
	</div>
</div>

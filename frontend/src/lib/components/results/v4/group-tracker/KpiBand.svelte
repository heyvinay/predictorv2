<script lang="ts">
	export let topTwoOnTrack: number;
	export let topTwoTotal: number;
	export let locked: number;
	export let groupsTotal: number;
	export let atRisk: number;
	export let orderSwaps: number;
</script>

<section class="mb-4 grid grid-cols-2 gap-2.5 lg:grid-cols-4" aria-label="Reality-check summary">
	<div class="relative overflow-hidden rounded-xl border border-base-300 bg-base-200 px-3.5 py-2.5">
		<span class="absolute inset-y-0 left-0 w-[3px] bg-success"></span>
		<p class="text-[10px] font-semibold uppercase tracking-wide text-base-content/55">
			Top-2 picks on track
		</p>
		<p class="mt-0.5 font-mono text-xl font-extrabold leading-tight tabular-nums">
			{topTwoOnTrack}<span class="text-sm font-medium text-base-content/40">/{topTwoTotal}</span>
		</p>
	</div>

	<div class="relative overflow-hidden rounded-xl border border-base-300 bg-base-200 px-3.5 py-2.5">
		<span class="absolute inset-y-0 left-0 w-[3px] bg-base-300"></span>
		<p class="text-[10px] font-semibold uppercase tracking-wide text-base-content/55">
			Groups fully locked
		</p>
		<p class="mt-0.5 font-mono text-xl font-extrabold leading-tight tabular-nums">
			{locked}<span class="text-sm font-medium text-base-content/40">/{groupsTotal}</span>
		</p>
	</div>

	<div class="relative overflow-hidden rounded-xl border border-base-300 bg-base-200 px-3.5 py-2.5">
		<span class="absolute inset-y-0 left-0 w-[3px] bg-warning"></span>
		<p class="text-[10px] font-semibold uppercase tracking-wide text-base-content/55">
			Groups at risk
		</p>
		<p class="mt-0.5 font-mono text-xl font-extrabold leading-tight tabular-nums">{atRisk}</p>
	</div>

	<div class="relative overflow-hidden rounded-xl border border-base-300 bg-base-200 px-3.5 py-2.5">
		<span class="absolute inset-y-0 left-0 w-[3px] bg-primary"></span>
		<p class="text-[10px] font-semibold uppercase tracking-wide text-base-content/55">
			Order swaps
		</p>
		<p class="mt-0.5 font-mono text-xl font-extrabold leading-tight tabular-nums">{orderSwaps}</p>
		<p class="text-[10px] text-base-content/55">Right teams, wrong slot</p>
	</div>
</section>

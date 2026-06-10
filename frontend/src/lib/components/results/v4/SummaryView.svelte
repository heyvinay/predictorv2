<script lang="ts">
	/** Summary tab — tournament-wide decomposition. The grand-total card is
	 *  the page's single glow element. Per-round rows mirror the round-tab
	 *  LIVE dots from the same roundsWithLive set (D.1b). Tournament total
	 *  here = match + bracket + winner rounds; bonus-question points are a
	 *  separate surface (leaderboard) by design — noted in spec. */
	import type { BracketPrediction, Fixture } from '$types';
	import type {
		MatchPredictionWithPoints,
		RoundDef,
		RoundId,
		ScoringRules
	} from '$lib/types/results';
	import { bracketPicksForRound, fixtureKoHits, stagePointsForRound } from '$lib/utils/koPoints';

	export let rounds: RoundDef[];
	export let fixtureById: Map<string, Fixture>;
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;
	export let bracket: BracketPrediction | null;
	export let rules: ScoringRules;
	export let liveRounds: Set<RoundId>;
	export let onJump: (id: RoundId) => void;

	interface Row {
		id: RoundId;
		label: string;
		dates: string;
		isKO: boolean;
		isWinner: boolean;
		pending: boolean;
		exact: number;
		result: number;
		rarity: number;
		hits: number;
		total: number;
	}

	function championOfFinal(): string | null {
		const fRound = rounds.find((r) => r.id === 'f');
		for (const fid of fRound?.fixtureIds ?? []) {
			const f = fixtureById.get(fid);
			if (f && f.stage === 'final' && f.status === 'finished' && f.score) {
				if (f.score.outcome === '1') return f.home_team;
				if (f.score.outcome === '2') return f.away_team;
			}
		}
		return null;
	}

	$: rows = rounds
		.filter((r) => r.id !== 'summary')
		.map((r): Row => {
			if (r.id === 'winner') {
				const champion = championOfFinal();
				const correct = !!champion && !!bracket?.winner && champion === bracket.winner;
				return {
					id: r.id,
					label: r.label,
					dates: r.dates || '—',
					isKO: true,
					isWinner: true,
					pending: !champion,
					exact: 0,
					result: 0,
					rarity: 0,
					hits: correct ? 1 : 0,
					total: correct ? rules.advancement.winner : 0
				};
			}
			if (r.isKnockout) {
				const picks = bracketPicksForRound(bracket, r.id);
				const stagePts = stagePointsForRound(rules.advancement, r.id);
				let hits = 0;
				for (const fid of r.fixtureIds) {
					const f = fixtureById.get(fid);
					if (f) hits += fixtureKoHits(f, picks).hits;
				}
				return {
					id: r.id,
					label: r.label,
					dates: r.dates,
					isKO: true,
					isWinner: false,
					pending: false,
					exact: 0,
					result: 0,
					rarity: 0,
					hits,
					total: hits * stagePts
				};
			}
			let exact = 0,
				result = 0,
				rarity = 0,
				total = 0;
			for (const fid of r.fixtureIds) {
				const pts = predictionsByFixture.get(fid)?.points;
				if (!pts) continue;
				total += pts.total;
				if (pts.base_kind === 'exact') exact++;
				else if (pts.base_kind === 'result') result++;
				if (pts.rarity > 0) rarity++;
			}
			return {
				id: r.id,
				label: r.label,
				dates: r.dates,
				isKO: false,
				isWinner: false,
				pending: false,
				exact,
				result,
				rarity,
				hits: 0,
				total
			};
		});

	$: groupTotal = rows.filter((b) => !b.isKO).reduce((s, b) => s + b.total, 0);
	$: koTotal = rows.filter((b) => b.isKO).reduce((s, b) => s + b.total, 0);
	$: grand = groupTotal + koTotal;
	$: totalExact = rows.reduce((s, b) => s + b.exact, 0);
	$: totalResult = rows.reduce((s, b) => s + b.result, 0);
	$: totalRarity = rows.reduce((s, b) => s + b.rarity, 0);
	$: totalHits = rows.filter((b) => b.isKO && !b.isWinner).reduce((s, b) => s + b.hits, 0);
</script>

<div class="mt-4 flex flex-col gap-4">
	<!-- Subtotal cards — compact: title + value on one row, stats inline beneath -->
	<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
		<div class="flex flex-col gap-1 rounded-box border border-base-300/60 bg-base-200 px-3 py-2">
			<div class="flex items-baseline justify-between gap-2">
				<span class="font-display text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-base-content/70"
					>Group stage</span
				>
				<span class="font-display text-[22px] leading-none">{groupTotal}</span>
			</div>
			<div class="flex flex-wrap gap-1.5 text-[10.5px] font-bold text-base-content/70">
				<span class="inline-flex items-center gap-1">
					<span class="grid h-[14px] w-[14px] place-items-center rounded-[4px] bg-success/20 text-[9px] text-success">E</span>
					<span>{totalExact}</span>
				</span>
				<span class="inline-flex items-center gap-1">
					<span class="grid h-[14px] w-[14px] place-items-center rounded-[4px] bg-warning/20 text-[9px] text-warning-text">R</span>
					<span>{totalResult}</span>
				</span>
				<span class="inline-flex items-center gap-1">
					<span class="grid h-[14px] w-[14px] place-items-center rounded-[4px] bg-primary/20 text-[9px] text-primary">★</span>
					<span>{totalRarity}</span>
				</span>
			</div>
		</div>
		<div class="flex flex-col gap-1 rounded-box border border-base-300/60 bg-base-200 px-3 py-2">
			<div class="flex items-baseline justify-between gap-2">
				<span class="font-display text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-base-content/70"
					>Knockouts</span
				>
				<span class="font-display text-[22px] leading-none">{koTotal}</span>
			</div>
			<div class="flex flex-wrap gap-1.5 text-[10.5px] font-bold text-base-content/70">
				<span class="inline-flex items-center gap-1">
					<span class="grid h-[14px] w-[14px] place-items-center rounded-[4px] bg-success/20 text-[9px] text-success">✓</span>
					<span>{totalHits} bracket hits</span>
				</span>
			</div>
		</div>
		<!-- Tournament total — THE one glow element on the page -->
		<div
			class="flex items-center justify-between gap-2 rounded-box border border-primary bg-gradient-to-r from-primary/15 to-base-200 px-3 py-2 shadow-glow-gold"
		>
			<span class="font-display text-[10.5px] font-extrabold uppercase tracking-[0.08em]"
				>Tournament total</span
			>
			<span class="font-display text-[26px] leading-none text-primary">{grand}</span>
		</div>
	</div>

	<!-- Per-round table -->
	<div class="overflow-hidden rounded-box border border-base-300/60 bg-base-200">
		<div
			class="grid grid-cols-[minmax(120px,1.4fr)_minmax(90px,1fr)_minmax(110px,1.1fr)_64px_24px] items-center gap-2 border-b border-base-300/50 bg-base-300/20 px-3 py-1.5"
		>
			<span class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>Round</span
			>
			<span
				class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>Dates</span
			>
			<span
				class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>Hits</span
			>
			<span
				class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>Points</span
			>
			<span></span>
		</div>
		{#each rows as b (b.id)}
			<button
				type="button"
				class="group grid w-full grid-cols-[minmax(120px,1.4fr)_minmax(90px,1fr)_minmax(110px,1.1fr)_64px_24px] items-center gap-2 border-t border-base-300/45 px-3 py-1.5 text-left transition-colors first:border-t-0 hover:bg-primary/5"
				on:click={() => onJump(b.id)}
				aria-label={`Jump to ${b.label}`}
			>
				<span class="flex min-w-0 items-center gap-2.5">
					<span
						class="rounded-badge px-1.5 py-px text-[9px] font-extrabold {b.isKO
							? 'bg-success/20 text-success'
							: 'bg-primary/20 text-primary'}">{b.isKO ? 'KO' : 'GP'}</span
					>
					<span class="flex items-center gap-1.5 truncate text-[13px] font-semibold">
						{b.label}
						{#if liveRounds.has(b.id)}
							<span
								class="h-[7px] w-[7px] flex-none rounded-full bg-error animate-pulse-soft"
								title="Match in progress"
							></span>
						{/if}
					</span>
				</span>
				<span class="text-center text-[11.5px] text-base-content/55">{b.dates}</span>
				<span class="flex justify-center">
					{#if b.isWinner}
						{#if b.pending}
							<span class="text-[11px] font-bold text-base-content/40">pending</span>
						{:else if b.hits > 0}
							<span class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success"
								>🏆 +{b.total}</span
							>
						{:else}
							<span class="text-[11px] font-bold text-base-content/40">✗ missed</span>
						{/if}
					{:else if b.isKO}
						{#if b.hits > 0}
							<span class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success"
								>✓ {b.hits}</span
							>
						{:else}
							<span class="text-[11px] font-bold text-base-content/40">—</span>
						{/if}
					{:else if b.exact + b.result + b.rarity > 0}
						<span class="flex gap-1">
							{#if b.exact > 0}<span
									class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success"
									>E {b.exact}</span
								>{/if}
							{#if b.result > 0}<span
									class="rounded-badge bg-warning/20 px-1.5 py-px text-[11px] font-bold text-warning-text"
									>R {b.result}</span
								>{/if}
							{#if b.rarity > 0}<span
									class="rounded-badge bg-primary/20 px-1.5 py-px text-[11px] font-bold text-primary"
									>★ {b.rarity}</span
								>{/if}
						</span>
					{:else}
						<span class="text-[11px] font-bold text-base-content/40">—</span>
					{/if}
				</span>
				<span
					class="text-right font-display text-[15px] {b.total > 0
						? 'text-primary'
						: 'text-base-content/30'}">{b.total}</span
				>
				<span
					class="text-base-content/40 transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
					>→</span
				>
			</button>
		{/each}
		<div class="flex items-center justify-between border-t border-base-300/50 px-3 py-2">
			<span class="text-[12px] font-bold tracking-[0.06em] text-primary">Tournament Total</span>
			<span class="font-display text-[18px] text-primary">{grand}</span>
		</div>
	</div>
</div>

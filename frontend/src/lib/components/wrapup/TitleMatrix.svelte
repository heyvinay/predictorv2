<script lang="ts">
	/**
	 * TitleMatrix — "How the title was won." Top-3 podium entries side by
	 * side: points-by-column, a handful of decisive moments (the elements
	 * that most separated the champion from 2nd/3rd), and a "race in
	 * numbers" strip. Reuses the shared compareEntries engine (Plan B) —
	 * never re-derives deltas/points here.
	 *
	 * Guest / no-rules degradation: per-entry prediction fetches 401 for
	 * anonymous visitors (entry-scoped routes) — the catch leaves
	 * `moments = []` so the decisive-moments section simply doesn't
	 * render. The points/race-in-numbers rows come straight from the
	 * public `podium` payload and always show, same when `rules` is null.
	 */
	import { onMount } from 'svelte';
	import { isAuthenticated } from '$stores/auth';
	import { fixtures, fixtureById } from '$stores/fixtures';
	import { getEntryBonusReads } from '$api/leaderboard';
	import { getMatchPredictions, getBracketPredictions } from '$api/predictions';
	import { getBonusQuestions } from '$api/bonus';
	import { track } from '$lib/analytics';
	import {
		buildSwings,
		elementValues,
		type ActualAdvancement,
		type CompareEntryInput,
		type Swing
	} from '$lib/utils/compareEntries';
	import { seededByStage } from '$lib/utils/leaderboardV4';
	import type { FinalPodium, FinalPodiumEntry } from '$lib/types/wrapup';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';

	export let podium: FinalPodium;
	export let rows: LbEntryV4[];
	export let rules: ScoringRules | null;

	$: top3 = podium.entries.slice(0, 3);

	interface Moment {
		label: string;
		why: string;
		values: number[];
	}
	let moments: Moment[] = [];

	async function loadInput(e: FinalPodiumEntry): Promise<CompareEntryInput> {
		const [m, br, bq, qs] = await Promise.all([
			getMatchPredictions(e.entry_id) as Promise<MatchPredictionWithPoints[]>,
			getBracketPredictions(e.entry_id, 'phase_1'),
			getEntryBonusReads(e.entry_id),
			getBonusQuestions().catch(() => [])
		]);
		return {
			entryId: e.entry_id,
			displayName: e.user_name,
			finalRank: e.final_rank,
			totalPoints: e.total_points,
			groupPoints: e.group_points,
			knockoutPoints: e.knockout_points,
			bonusPoints: e.bonus_points,
			matches: m,
			bracket: br,
			bonusReads: bq,
			questionLabels: new Map(qs.map((q) => [q.id, q.label]))
		};
	}

	const keyOf = (s: Swing) => `${s.kind}:${s.key}`;

	// Row definitions hoisted to typed consts — Svelte template expressions
	// are parsed as plain JS even inside a `lang="ts"` component, so an
	// inline `(e: FinalPodiumEntry) => …` arrow with a type annotation
	// inside `{#each [...] as row}` fails to compile (CLAUDE.md frontend
	// gotcha: "Svelte template expressions do NOT extend TypeScript").
	type ColumnRow = { label: string; get: (e: FinalPodiumEntry) => number };
	const POINTS_ROWS: ColumnRow[] = [
		{ label: 'Group stage', get: (e) => e.group_points },
		{ label: 'Knockouts', get: (e) => e.knockout_points },
		{ label: 'Bonus', get: (e) => e.bonus_points }
	];
	const RACE_ROWS: ColumnRow[] = [
		{ label: 'Exact scores', get: (e) => e.exact_scores },
		{ label: 'Rarity bonus', get: (e) => e.rarity_points },
		{ label: 'Days at #1', get: (e) => e.days_at_top }
	];

	onMount(async () => {
		if (top3.length < 2 || !rules) return;
		try {
			const inputs = await Promise.all(top3.map(loadInput));
			const actual = Object.fromEntries(seededByStage($fixtures)) as ActualAdvancement;
			const vs2 = buildSwings(inputs[0], inputs[1], $fixtureById, actual, rules);
			const vs3 = inputs[2] ? buildSwings(inputs[0], inputs[2], $fixtureById, actual, rules) : [];

			// Merge champion-vs-2nd and champion-vs-3rd swings, keeping the
			// larger-magnitude delta on key collisions, then re-rank by |delta|
			// so the top 3 decisive moments reflect whichever comparison
			// produced the bigger swing.
			const merged = new Map<string, Swing>();
			for (const s of [...vs2, ...vs3]) {
				const k = keyOf(s);
				const existing = merged.get(k);
				if (!existing || Math.abs(s.delta) > Math.abs(existing.delta)) merged.set(k, s);
			}
			const topSwings = [...merged.values()]
				.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
				.slice(0, 3);

			moments = topSwings.map((s) => ({
				label: s.label,
				why: s.why,
				values: elementValues(inputs, s, actual, rules!)
			}));
		} catch {
			moments = [];
		}
	});
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">How the title was won</h2>
	<p class="mb-2 text-xs text-base-content/50">
		The top three side by side — where each entry built its points, and the handful of moments
		that split them.
	</p>

	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="text-right text-[10px] uppercase tracking-wider text-base-content/40">
					<th class="text-left"></th>
					{#each top3 as e, i}
						<th class="{i === 0 ? 'rounded-t-lg bg-primary/10 text-primary' : ''} px-2 py-1">
							{i === 0 ? '🏆' : i === 1 ? '🥈' : '🥉'}
							{e.user_name}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody class="tabular-nums">
				{#each POINTS_ROWS as row}
					{@const vals = top3.map(row.get)}
					{@const best = Math.max(...vals)}
					<tr class="border-t border-base-300/40">
						<td class="max-w-[110px] truncate py-1.5">{row.label}</td>
						{#each vals as v, i}
							<td
								class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10' : ''} {v === best
									? 'font-bold text-primary'
									: ''}">{v}</td
							>
						{/each}
					</tr>
				{/each}
				<tr class="border-t border-primary/40 font-extrabold">
					<td class="py-1.5">Total</td>
					{#each top3 as e, i}
						<td class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10 text-primary' : ''}"
							>{e.total_points}</td
						>
					{/each}
				</tr>
				{#if moments.length}
					<tr>
						<td
							colspan={top3.length + 1}
							class="pb-0.5 pt-2.5 text-[10px] font-bold uppercase tracking-[.12em] text-base-content/40"
							>Decisive moments</td
						>
					</tr>
					{#each moments as m}
						<tr class="border-t border-base-300/40">
							<td class="max-w-[130px] py-1.5">
								<span class="block truncate">{m.label}</span>
								<span class="block truncate text-[10px] text-base-content/40">{m.why}</span>
							</td>
							{#each m.values as v, i}
								<td
									class="px-2 py-1.5 text-right {i === 0
										? 'bg-primary/10 font-bold text-primary'
										: 'text-base-content/60'}"
									>{v > 0 ? '+' : ''}{Math.round(v * 10) / 10}</td
								>
							{/each}
						</tr>
					{/each}
				{/if}
				<tr>
					<td
						colspan={top3.length + 1}
						class="pb-0.5 pt-2.5 text-[10px] font-bold uppercase tracking-[.12em] text-base-content/40"
						>The race in numbers</td
					>
				</tr>
				{#each RACE_ROWS as row}
					{@const vals = top3.map(row.get)}
					{@const best = Math.max(...vals)}
					<tr class="border-t border-base-300/40">
						<td class="py-1.5">{row.label}</td>
						{#each vals as v, i}
							<td
								class="px-2 py-1.5 text-right {i === 0 ? 'bg-primary/10' : ''} {v === best
									? 'font-bold text-primary'
									: ''}">{v}</td
							>
						{/each}
					</tr>
				{/each}
				<tr class="border-t border-base-300/40">
					<td class="py-1.5">Champion pick</td>
					{#each top3 as e, i}
						<td
							class="px-2 py-1.5 text-right text-xs {i === 0 ? 'bg-primary/10' : ''} {e.champion_hit
								? 'font-bold text-primary'
								: 'text-base-content/55'}"
						>
							{e.champion_pick ?? '—'}
							{e.champion_hit ? '✓' : '✗'}
						</td>
					{/each}
				</tr>
			</tbody>
		</table>
	</div>

	<div class="mt-2 flex flex-wrap items-center justify-between gap-2">
		<span class="text-[11px] text-base-content/40"
			>Gold = best in row · the title was decided in the knockouts</span
		>
		{#if $isAuthenticated && top3.length > 1}
			<a
				href="/compare?a={top3[1]?.entry_id}&b={top3[0]?.entry_id}"
				class="text-[11px] font-bold text-primary"
				on:click={() => track('wrapup_matrix_compare_clicked', {})}>Full head-to-head → /compare</a
			>
		{/if}
	</div>
</div>

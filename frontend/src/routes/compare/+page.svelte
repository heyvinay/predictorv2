<script lang="ts">
	/**
	 * /compare — head-to-head entry comparison (v2.214.0 draft).
	 *
	 * Admin-only staged rollout (same recipe as V4 Results/Leaderboard at
	 * their initial ship): V4_COMPARE_ENABLED kill switch + $user?.is_admin
	 * gate. Opening it to the whole pool is a future release task — do NOT
	 * add a postDeadlineLive-style OR clause here without an explicit
	 * instruction to ship it.
	 *
	 * Powered entirely by the shared compareEntries engine
	 * ($lib/utils/compareEntries) — this page only fetches data and wires
	 * it into buildSummary/buildBracketRows/buildBonusRows/buildSwings.
	 */
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { fixtureById, fixtures, fetchAllFixtures } from '$stores/fixtures';
	import { pageTitle } from '$stores/pageTitle';
	import { getLeaderboardV4, getEntryBonusReads, getScoringRules } from '$api/leaderboard';
	import { getMatchPredictions, getBracketPredictions } from '$api/predictions';
	import { getBonusQuestions } from '$api/bonus';
	import { track } from '$lib/analytics';
	import { rowDisplayName, searchRows, groupPtsOf, koPtsOf, foldBonus, multiEntryUserIds, seededByStage } from '$lib/utils/leaderboardV4';
	import {
		buildBonusRows, buildBracketRows, buildMatchRows, buildSummary, buildSwings,
		type ActualAdvancement, type CompareEntryInput
	} from '$lib/utils/compareEntries';
	import CompareSummaryStrip from '$lib/components/compare/CompareSummaryStrip.svelte';
	import SwingList from '$lib/components/compare/SwingList.svelte';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';

	// ── Gate: admin-only staged rollout. Release = delete the is_admin
	// clause + redeploy (future task, not this one). ──
	const V4_COMPARE_ENABLED = true;
	$: compareOpen = V4_COMPARE_ENABLED && $user?.is_admin === true;
	$: if (!$isAuthenticated) goto('/login');

	onMount(() => pageTitle.set('Compare'));

	let rows: LbEntryV4[] = [];
	let rules: ScoringRules | null = null;
	let multiOwners = new Set<string>();
	let loading = true;

	let aId: string | null = null;
	let bId: string | null = null;
	let inputA: CompareEntryInput | null = null;
	let inputB: CompareEntryInput | null = null;
	type CompareTab = 'matches' | 'bracket' | 'bonus';
	let tab: CompareTab = 'matches';
	const TABS: CompareTab[] = ['matches', 'bracket', 'bonus'];

	// KO stages where real (non-slot) teams are seeded = "reached" — reuse
	// the canonical resolver (leaderboardV4.seededByStage) rather than
	// re-deriving advancement here; it already encodes the lineup-based
	// advancement rule (CLAUDE.md ★ invariant) and backs EntryDrawer too.
	$: actual = Object.fromEntries(seededByStage($fixtures)) as ActualAdvancement;

	async function loadBoard() {
		loading = true;
		const [lb, sr] = await Promise.all([getLeaderboardV4(), getScoringRules(), fetchAllFixtures()]);
		rows = lb.entries;
		rules = sr;
		multiOwners = multiEntryUserIds(rows);
		// defaults: A = viewer's best entry, B = current #1 (the leader)
		const mine = rows.filter((r) => r.user_id === $user?.id).sort((x, y) => x.position - y.position);
		const leader = rows.slice().sort((x, y) => x.position - y.position)[0];
		aId = $page.url.searchParams.get('a') ?? mine[0]?.entry_id ?? leader?.entry_id ?? null;
		bId = $page.url.searchParams.get('b') ?? leader?.entry_id ?? null;
		loading = false;
		track('compare_opened', { default_pair: !$page.url.searchParams.get('a') });
	}
	onMount(() => void loadBoard());

	async function loadEntry(id: string): Promise<CompareEntryInput | null> {
		const row = rows.find((r) => r.entry_id === id);
		if (!row) return null;
		const [m, br, bq, qs] = await Promise.all([
			getMatchPredictions(id) as Promise<MatchPredictionWithPoints[]>,
			getBracketPredictions(id, 'phase_1'),
			getEntryBonusReads(id),
			getBonusQuestions().catch(() => [])
		]);
		const fold = foldBonus(bq);
		return {
			entryId: id,
			displayName: rowDisplayName(row, multiOwners),
			finalRank: row.position,
			totalPoints: row.total_points,
			groupPoints: groupPtsOf(row, fold.group),
			knockoutPoints: koPtsOf(row, fold.knockout),
			bonusPoints: fold.group + fold.knockout,
			matches: m,
			bracket: br,
			bonusReads: bq,
			questionLabels: new Map(qs.map((q) => [q.id, q.label]))
		};
	}

	let loadedPair = '';
	$: if (browser && aId && bId && rows.length && `${aId}|${bId}` !== loadedPair) {
		loadedPair = `${aId}|${bId}`;
		void Promise.all([loadEntry(aId), loadEntry(bId)]).then(([ia, ib]) => {
			inputA = ia;
			inputB = ib;
			const url = new URL($page.url);
			url.searchParams.set('a', aId!);
			url.searchParams.set('b', bId!);
			history.replaceState({}, '', url);
		});
	}

	$: summary = inputA && inputB ? buildSummary(inputA, inputB) : null;
	$: swings = inputA && inputB && rules ? buildSwings(inputA, inputB, $fixtureById, actual, rules) : [];
	$: matchRows = inputA && inputB ? buildMatchRows(inputA, inputB, $fixtureById) : [];
	$: bracketRows = inputA && inputB && rules ? buildBracketRows(inputA, inputB, actual, rules) : [];
	$: bonusRows = inputA && inputB ? buildBonusRows(inputA, inputB) : [];

	function swap() {
		[aId, bId] = [bId, aId];
		track('compare_pair_changed', { via: 'swap' });
	}

	// picker dropdown with search (searchRows — accent-insensitive)
	let pickerOpen: 'a' | 'b' | null = null;
	let query = '';
	$: pickerRows = searchRows(rows, query);
	function choose(side: 'a' | 'b', id: string) {
		if (side === 'a') aId = id;
		else bId = id;
		pickerOpen = null;
		query = '';
		track('compare_pair_changed', { via: 'picker' });
	}
	function togglePicker(side: 'a' | 'b') {
		pickerOpen = pickerOpen === side ? null : side;
	}
	function setTab(t: CompareTab) {
		tab = t;
		track('compare_tab_changed', { tab: t });
	}
	const tabLabel = (t: CompareTab) => (t === 'matches' ? 'Matches' : t === 'bracket' ? 'Bracket' : 'Bonus');

	const fmtPts = (n: number) => Math.round(n * 10) / 10;
	const pickTone = (kind: string) =>
		kind === 'exact' ? 'text-primary font-bold' : kind === 'result' ? 'text-success' : 'text-base-content/40';
	const deltaTone = (n: number) => (n > 0 ? 'text-success' : n < 0 ? 'text-error' : 'text-base-content/40');
</script>

<svelte:head><title>Compare entries — The Predictor</title></svelte:head>

{#if $isAuthenticated && !compareOpen}
	<div class="hero min-h-[60vh]"><div class="hero-content text-center"><div class="max-w-md">
		<h1 class="text-2xl font-display font-extrabold">Head-to-head is coming</h1>
		<p class="text-base-content/60 mt-2">The compare view opens after the Final.</p>
	</div></div></div>
{/if}

{#if $isAuthenticated && compareOpen}
	<div class="container mx-auto max-w-[980px] mobile-padding pb-10 pt-3">
		<h1 class="font-display text-xl font-extrabold mb-1">Head-to-head</h1>
		<p class="text-sm text-base-content/55 mb-4">Every pick, side by side — and the exact moments the gap was made.</p>

		{#if loading}
			<div class="stadium-card no-glow p-8 text-center text-base-content/50">Loading…</div>
		{:else if inputA && inputB && summary}
			<!-- picker bar -->
			<div class="grid grid-cols-1 sm:grid-cols-[1fr_44px_1fr] gap-2 items-stretch mb-4">
				<div class="relative">
					<button
						class="group flex w-full items-center justify-between gap-2 rounded-box border px-3 py-2.5 text-left transition-colors {pickerOpen ===
						'a'
							? 'border-primary/60 bg-primary/5'
							: 'border-base-300/60 bg-base-100 hover:border-primary/40 hover:bg-primary/5'}"
						on:click={() => togglePicker('a')}
						aria-haspopup="listbox"
						aria-expanded={pickerOpen === 'a'}
					>
						<span class="min-w-0">
							<span class="block text-[10px] font-bold uppercase tracking-wider text-base-content/40"
								>Entry A · tap to change</span
							>
							<span class="block truncate font-bold">{inputA.displayName}</span>
							<span class="block text-xs text-base-content/55"
								>{inputA.totalPoints} pts · #{inputA.finalRank}</span
							>
						</span>
						<span
							class="grid h-7 w-7 flex-none place-items-center rounded-full text-sm transition-transform {pickerOpen ===
							'a'
								? 'rotate-180 bg-primary/15 text-primary'
								: 'bg-base-300/60 text-base-content/60 group-hover:bg-primary/15 group-hover:text-primary'}"
							aria-hidden="true">▾</span
						>
					</button>
					{#if pickerOpen === 'a'}
						<div class="absolute z-30 mt-1 w-full rounded-box border border-primary/40 bg-base-200 p-2 shadow-card">
							<p class="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-wider text-base-content/40">
								Choose Entry A
							</p>
							<input
								class="input input-sm input-bordered w-full mb-1"
								placeholder="Search person or entry name…"
								bind:value={query}
							/>
							<div class="max-h-64 overflow-y-auto">
								{#each pickerRows.slice(0, 50) as r (r.entry_id)}
									<button
										class="flex w-full items-center justify-between gap-2 rounded-btn px-2 py-1.5 text-left text-sm hover:bg-primary/10 {r.entry_id ===
										aId
											? 'bg-primary/10 font-semibold text-primary'
											: ''}"
										on:click={() => choose('a', r.entry_id)}
									>
										<span class="truncate">{rowDisplayName(r, multiOwners)}</span>
										<span class="flex flex-none items-center gap-1 text-xs text-base-content/50">
											#{r.position} · {r.total_points}
											{#if r.entry_id === aId}<span class="text-primary">✓</span>{/if}
										</span>
									</button>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				<button
					class="hidden place-items-center rounded-box border border-base-300/60 bg-base-100 text-base-content/60 transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary sm:grid"
					on:click={swap}
					aria-label="Swap entries"
					title="Swap Entry A and Entry B"
				>⇄</button>

				<div class="relative">
					<button
						class="group flex w-full items-center justify-between gap-2 rounded-box border px-3 py-2.5 text-left transition-colors {pickerOpen ===
						'b'
							? 'border-primary/60 bg-primary/5'
							: 'border-primary/50 bg-base-100 hover:border-primary/70 hover:bg-primary/5'}"
						on:click={() => togglePicker('b')}
						aria-haspopup="listbox"
						aria-expanded={pickerOpen === 'b'}
					>
						<span class="min-w-0">
							<span class="block text-[10px] font-bold uppercase tracking-wider text-base-content/40"
								>Entry B · tap to change</span
							>
							<span class="block truncate font-bold">{inputB.displayName}</span>
							<span class="block text-xs text-base-content/55"
								>{inputB.totalPoints} pts · #{inputB.finalRank}</span
							>
						</span>
						<span
							class="grid h-7 w-7 flex-none place-items-center rounded-full text-sm transition-transform {pickerOpen ===
							'b'
								? 'rotate-180 bg-primary/15 text-primary'
								: 'bg-base-300/60 text-base-content/60 group-hover:bg-primary/15 group-hover:text-primary'}"
							aria-hidden="true">▾</span
						>
					</button>
					{#if pickerOpen === 'b'}
						<div class="absolute z-30 mt-1 w-full rounded-box border border-primary/40 bg-base-200 p-2 shadow-card">
							<p class="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-wider text-base-content/40">
								Choose Entry B
							</p>
							<input
								class="input input-sm input-bordered w-full mb-1"
								placeholder="Search person or entry name…"
								bind:value={query}
							/>
							<div class="max-h-64 overflow-y-auto">
								{#each pickerRows.slice(0, 50) as r (r.entry_id)}
									<button
										class="flex w-full items-center justify-between gap-2 rounded-btn px-2 py-1.5 text-left text-sm hover:bg-primary/10 {r.entry_id ===
										bId
											? 'bg-primary/10 font-semibold text-primary'
											: ''}"
										on:click={() => choose('b', r.entry_id)}
									>
										<span class="truncate">{rowDisplayName(r, multiOwners)}</span>
										<span class="flex flex-none items-center gap-1 text-xs text-base-content/50">
											#{r.position} · {r.total_points}
											{#if r.entry_id === bId}<span class="text-primary">✓</span>{/if}
										</span>
									</button>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			</div>

			<div class="stadium-card no-glow p-4 mb-4">
				<CompareSummaryStrip {summary} aName={inputA.displayName} bName={inputB.displayName} />
			</div>

			<div class="stadium-card no-glow p-4 mb-4">
				<h2 class="font-display font-extrabold mb-2">Where the gap was made</h2>
				<SwingList {swings} limit={5} />
			</div>

			<!-- tabs -->
			<div class="flex gap-1.5 mb-2">
				{#each TABS as t}
					<button
						class="rounded-badge px-3.5 py-1 text-xs font-semibold border
							{tab === t ? 'bg-primary/15 border-primary/50 text-primary' : 'border-base-300/60 text-base-content/55'}"
						on:click={() => setTab(t)}
					>{tabLabel(t)}</button>
				{/each}
			</div>

			<div class="stadium-card no-glow p-4 overflow-x-auto">
				{#if tab === 'matches'}
					<table class="w-full table-fixed text-sm">
						<colgroup>
							<col class="w-[34%]" />
							<col class="w-[27%]" />
							<col class="w-[27%]" />
							<col class="w-[12%]" />
						</colgroup>
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Match</th><th class="py-1 pr-2">{inputA.displayName}</th>
							<th class="py-1 pr-2">{inputB.displayName}</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each matchRows as r (r.fixtureId)}
								<tr class="border-t border-base-300/40">
									<td class="max-w-0 truncate py-1.5 pr-2">{r.label}</td>
									<td class="py-1.5 pr-2">
										<span class="flex items-baseline gap-1.5">
											<span class="{pickTone(r.aKind)} truncate">{r.aPick ?? '—'}</span>
											<span class="flex-none text-xs tabular-nums text-base-content/50">{fmtPts(r.aPoints)}</span>
										</span>
									</td>
									<td class="py-1.5 pr-2">
										<span class="flex items-baseline gap-1.5">
											<span class="{pickTone(r.bKind)} truncate">{r.bPick ?? '—'}</span>
											<span class="flex-none text-xs tabular-nums text-base-content/50">{fmtPts(r.bPoints)}</span>
										</span>
									</td>
									<td class="py-1.5 text-right tabular-nums font-bold {deltaTone(r.delta)}">{r.delta > 0 ? '+' : ''}{fmtPts(r.delta)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else if tab === 'bracket'}
					<table class="w-full text-sm">
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Stage</th><th class="py-1 pr-2 text-right">{inputA.displayName}</th>
							<th class="py-1 pr-2 text-right">{inputB.displayName}</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each bracketRows as r (r.stage)}
								<tr class="border-t border-base-300/40">
									<td class="py-1.5 pr-2">{r.label}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{r.aHits}/{r.aTeams.length || '—'} · +{r.aPoints}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{r.bHits}/{r.bTeams.length || '—'} · +{r.bPoints}</td>
									<td class="py-1.5 text-right tabular-nums font-bold {deltaTone(r.delta)}">{r.delta > 0 ? '+' : ''}{r.delta}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<table class="w-full text-sm">
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Question</th><th class="py-1 pr-2">{inputA.displayName}</th>
							<th class="py-1 pr-2">{inputB.displayName}</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each bonusRows as r (r.questionId)}
								<tr class="border-t border-base-300/40">
									<td class="py-1.5 pr-2">{r.label}</td>
									<td class="py-1.5 pr-2 {r.aHit ? 'text-success font-semibold' : 'text-base-content/50'}">{r.aAnswer ?? '—'} {r.aHit ? '✓' : r.aHit === false ? '✗' : ''}</td>
									<td class="py-1.5 pr-2 {r.bHit ? 'text-success font-semibold' : 'text-base-content/50'}">{r.bAnswer ?? '—'} {r.bHit ? '✓' : r.bHit === false ? '✗' : ''}</td>
									<td class="py-1.5 text-right tabular-nums font-bold {deltaTone(r.delta)}">{r.delta > 0 ? '+' : ''}{r.delta}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		{/if}
	</div>
{/if}

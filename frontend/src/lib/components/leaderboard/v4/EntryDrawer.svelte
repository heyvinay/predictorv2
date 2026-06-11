<script lang="ts">
	/**
	 * Entry detail drawer (spec §4) — right panel with the entry's FULL
	 * locked predictions and scoring. Open pool: works for any entry
	 * post-deadline (backend enforces visibility).
	 *
	 * Section order: header → story line → summary cells → DNA →
	 * champion → knockout bracket (latest round first) → group picks
	 * (latest matchday first) → bonus questions → open-pool footer.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { fixtureById, fixtures } from '$stores/fixtures';
	import { getEntryBonusReads, getEntryBreakdown } from '$api/leaderboard';
	import { getMatchPredictions, getBracketPredictions } from '$api/predictions';
	import { getBonusQuestions } from '$api/bonus';
	import type { BracketPrediction, Fixture, PointBreakdown } from '$types';
	import type { BonusPredictionRead, LbEntryV4 } from '$lib/types/leaderboard';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
	import {
		chipState,
		dnaOf,
		eliminatedTeams,
		foldBonus,
		groupPtsOf,
		initialsOf,
		koPtsOf,
		rowDisplayName,
		seededByStage,
		storyLine
	} from '$lib/utils/leaderboardV4';
	import { deriveGroupMatchdays } from '$lib/utils/resultsRounds';
	import DnaBar from './DnaBar.svelte';
	import FlagCode from './FlagCode.svelte';
	import MoveChip from './MoveChip.svelte';
	import PointsCellGroup from '$lib/components/results/v4/PointsCellGroup.svelte';
	import YouTag from './YouTag.svelte';

	export let row: LbEntryV4;
	export let isOwn: boolean;
	export let rules: ScoringRules | null;
	/** Users with >1 entries — same display-name rule as the table. */
	export let multiOwners: Set<string>;
	export let onClose: () => void;

	let panel: HTMLElement;
	let loading = true;
	let loadError = false;
	let breakdown: PointBreakdown | null = null;
	let matches: MatchPredictionWithPoints[] = [];
	let bracket: BracketPrediction | null = null;
	let bonusReads: BonusPredictionRead[] = [];
	let questionLabels = new Map<string, string>();

	async function load() {
		loading = true;
		loadError = false;
		try {
			const [b, m, br, bq, qs] = await Promise.all([
				getEntryBreakdown(row.entry_id),
				getMatchPredictions(row.entry_id) as Promise<MatchPredictionWithPoints[]>,
				getBracketPredictions(row.entry_id, 'phase_1'),
				getEntryBonusReads(row.entry_id),
				getBonusQuestions().catch(() => [])
			]);
			breakdown = b;
			matches = m;
			bracket = br;
			bonusReads = bq;
			questionLabels = new Map(qs.map((q) => [q.id, q.label]));
		} catch {
			loadError = true;
		}
		loading = false;
	}

	// Reload when the user navigates between rows while the drawer is open.
	let loadedFor: string | null = null;
	$: if (row.entry_id !== loadedFor) {
		loadedFor = row.entry_id;
		void load();
	}

	// ── chrome: esc / scroll lock / focus restore ──
	let restoreFocus: HTMLElement | null = null;
	onMount(() => {
		restoreFocus = document.activeElement as HTMLElement | null;
		document.body.style.overflow = 'hidden';
		panel?.focus();
	});
	onDestroy(() => {
		document.body.style.overflow = '';
		restoreFocus?.focus?.();
	});
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.stopPropagation();
			onClose();
			return;
		}
		// Minimal focus trap: keep Tab cycling inside the panel.
		if (e.key === 'Tab' && panel) {
			const focusables = panel.querySelectorAll<HTMLElement>(
				'button, a[href], [tabindex]:not([tabindex="-1"])'
			);
			if (focusables.length === 0) return;
			const first = focusables[0];
			const last = focusables[focusables.length - 1];
			if (e.shiftKey && document.activeElement === first) {
				e.preventDefault();
				last.focus();
			} else if (!e.shiftKey && document.activeElement === last) {
				e.preventDefault();
				first.focus();
			}
		}
	}

	// ── derivations ──
	$: dna = breakdown ? dnaOf(breakdown) : null;
	$: fold = foldBonus(bonusReads);
	$: rowForTotals = breakdown ? { ...row, breakdown } : row;
	$: groupPts = groupPtsOf(rowForTotals, fold.group);
	$: koPts = koPtsOf(rowForTotals, fold.knockout);
	$: rarityHits = matches.filter((m) => (m.points?.rarity ?? 0) > 0).length;
	$: resultCount = breakdown ? breakdown.correct_outcomes - breakdown.exact_scores : 0;

	$: eliminated = eliminatedTeams($fixtures);
	$: seeded = seededByStage($fixtures);

	// Bracket rounds, most recent first — ALL scored knockout rounds
	// (R32 +20 and R16 +30 pay points too, so they must be visible).
	const KO_ROUNDS: {
		label: string;
		stage: string;
		key: 'final' | 'semi_finals' | 'quarter_finals' | 'round_of_16' | 'round_of_32';
	}[] = [
		{ label: 'Finalists', stage: 'final', key: 'final' },
		{ label: 'Semi-finalists', stage: 'semi_final', key: 'semi_finals' },
		{ label: 'Quarter-finalists', stage: 'quarter_final', key: 'quarter_finals' },
		{ label: 'Round of 16', stage: 'round_of_16', key: 'round_of_16' },
		{ label: 'Round of 32', stage: 'round_of_32', key: 'round_of_32' }
	];
	type KoRoundView = {
		label: string;
		stage: string;
		teams: { team: string; state: 'hit' | 'out' | 'pend' }[];
		hits: number;
		alive: number;
		pts: number;
	};
	$: koRounds = KO_ROUNDS.map((r): KoRoundView => {
		const teams = (bracket?.[r.key] ?? []).map((team) => ({
			team,
			state: chipState(team, r.stage, seeded, eliminated)
		}));
		const hits = teams.filter((t) => t.state === 'hit').length;
		const alive = teams.filter((t) => t.state !== 'out').length;
		const per = rules?.advancement?.[r.stage] ?? 0;
		return { ...r, teams, hits, alive, pts: hits * per };
	});

	// Group picks bucketed by matchday, latest first; fixtures latest-first.
	$: matchdays = deriveGroupMatchdays($fixtures);
	type DayBucket = { day: 1 | 2 | 3; picks: MatchPredictionWithPoints[]; pts: number };
	$: dayBuckets = ([3, 2, 1] as const)
		.map((day): DayBucket => {
			const picks = matches
				.filter((m) => (matchdays.get(m.fixture_id) ?? 1) === day)
				.sort(
					(a, b) => new Date(b.kickoff ?? 0).getTime() - new Date(a.kickoff ?? 0).getTime()
				);
			const pts = picks.reduce((s, p) => s + (p.points?.total ?? 0), 0);
			return { day, picks, pts };
		})
		.filter((b) => b.picks.length > 0);

	function fx(id: string): Fixture | undefined {
		return $fixtureById.get(id);
	}
	function kickoffShort(iso: string | null | undefined): string {
		if (!iso) return '';
		return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
	}
	$: bonusRows = bonusReads.map((r, i) => ({
		...r,
		n: i + 1,
		label: questionLabels.get(r.question_id) ?? r.question_id
	}));
</script>

<svelte:window on:keydown={onKeydown} />

<!-- scrim -->
<div
	class="fixed inset-0 z-[79] bg-[rgba(2,6,18,0.55)]"
	transition:fade={{ duration: 200 }}
	on:click={onClose}
	aria-hidden="true"
></div>

<!-- panel -->
<aside
	bind:this={panel}
	tabindex="-1"
	role="dialog"
	aria-modal="true"
	aria-label="Entry detail — {row.entry_name}"
	class="fixed bottom-0 right-0 top-0 z-[80] w-[min(480px,94vw)] overflow-y-auto overscroll-contain border-l border-base-300/70 bg-base-200 px-5 pb-6 pt-4 shadow-[-24px_0_60px_rgba(0,0,0,0.45)] outline-none"
	transition:fly={{ x: 40, duration: 250, opacity: 0 }}
>
	<!-- header -->
	<div class="flex items-center gap-3">
		<span
			class="grid h-[38px] w-[38px] flex-none place-items-center rounded-full font-display text-xs font-extrabold {isOwn
				? 'bg-primary/15 text-primary ring-[1.5px] ring-primary'
				: 'bg-base-300 text-base-content/70'}">{initialsOf(row.user_name)}</span
		>
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2 font-display text-base font-extrabold">
				<span class="truncate">{rowDisplayName(row, multiOwners)}</span>
				{#if isOwn}<YouTag />{/if}
			</div>
			<div class="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-base-content/55">
				{#if isOwn}<span>your entry</span>
					<span>·</span>{/if}
				<span class="font-display font-extrabold text-base-content/80">#{row.position}</span>
				<MoveChip move={row.daily_movement} />
			</div>
		</div>
		<button
			class="grid h-8 w-8 flex-none place-items-center rounded-lg bg-base-300/50 text-base-content/70 transition-colors hover:bg-base-300 hover:text-base-content"
			on:click={onClose}
			aria-label="Close entry detail">✕</button
		>
	</div>

	{#if loading}
		<div class="grid h-64 place-items-center">
			<span class="loading loading-spinner loading-lg text-primary"></span>
		</div>
	{:else if loadError}
		<div class="mt-6 rounded-xl border border-error/40 bg-error/10 px-4 py-5 text-center">
			<p class="text-sm">Couldn't load this entry's picks.</p>
			<button class="btn btn-outline btn-sm mt-3" on:click={load}>Retry</button>
		</div>
	{:else}
		<!-- story line -->
		<div class="mt-3 rounded-[9px] bg-base-300/30 px-3 py-2 text-[11.5px] leading-snug text-base-content/70">
			{storyLine(row)}
		</div>

		<!-- summary cells -->
		<div class="mt-3 grid grid-cols-[1.2fr_1fr_1fr] gap-2">
			<div class="flex flex-col gap-0.5 rounded-[10px] bg-primary/10 px-3 py-2.5">
				<span class="font-display text-xl font-extrabold text-primary">{row.total_points}</span>
				<span class="text-[10px] font-bold uppercase tracking-[0.08em] text-base-content/55"
					>Total</span
				>
			</div>
			<div class="flex flex-col gap-0.5 rounded-[10px] bg-base-300/30 px-3 py-2.5">
				<span class="font-display text-xl font-extrabold">{groupPts}</span>
				<span class="text-[10px] font-bold uppercase tracking-[0.08em] text-base-content/55">
					Group{#if fold.group}<span class="ml-1 normal-case tracking-normal text-primary"
							>+{fold.group} bonus</span
						>{/if}
				</span>
			</div>
			<div class="flex flex-col gap-0.5 rounded-[10px] bg-base-300/30 px-3 py-2.5">
				<span class="font-display text-xl font-extrabold">{koPts}</span>
				<span class="text-[10px] font-bold uppercase tracking-[0.08em] text-base-content/55">
					Knockout{#if fold.knockout}<span class="ml-1 normal-case tracking-normal text-primary"
							>+{fold.knockout} bonus</span
						>{/if}
				</span>
			</div>
		</div>

		<!-- DNA -->
		{#if dna && breakdown}
			<div class="mt-2.5 flex flex-col gap-1.5">
				<DnaBar split={dna} />
				<span class="text-[11.5px] text-base-content/55">
					<b class="font-display">{breakdown.exact_scores}</b> exact ·
					<b class="font-display">{resultCount}</b> results ·
					<b class="font-display">{rarityHits}</b> rarity hits ·
					<b class="font-display">{fold.hits}/{bonusReads.length || 4}</b> bonus
				</span>
			</div>
		{/if}

		<!-- champion -->
		{#if row.champion_pick}
			<div class="mt-3.5 flex items-center gap-3 rounded-[10px] bg-base-300/30 px-3 py-2.5">
				<span class="text-[10px] font-extrabold uppercase tracking-[0.1em] text-base-content/55"
					>Champion pick</span
				>
				<FlagCode team={row.champion_pick} alive={row.champion_alive ?? true} size="md" />
				<span
					class="rounded-badge px-2 py-0.5 text-[10px] font-extrabold {row.champion_alive
						? 'bg-success/15 text-success'
						: 'bg-error/15 text-error'}"
					>{row.champion_alive ? 'still alive' : 'eliminated'}</span
				>
			</div>
		{/if}

		<!-- knockout bracket — latest round first -->
		<section class="mt-4">
			<div class="mb-2 flex items-baseline justify-between gap-2.5">
				<h3 class="flex-none whitespace-nowrap font-hero text-[17px] tracking-[0.05em]">
					Knockout bracket
				</h3>
				<span class="text-right text-[10.5px] text-base-content/55"
					>lineup-banked — picks pay when the round is seeded</span
				>
			</div>
			{#each koRounds as kr (kr.stage)}
				<div class="mb-3">
					<div class="mb-1.5 flex items-baseline justify-between">
						<span class="text-[11px] font-bold text-base-content/70">{kr.label}</span>
						<span class="text-[10.5px] text-base-content/55">
							<b class="font-display font-extrabold text-success">{kr.hits}/{kr.teams.length}</b>
							through · {kr.alive} alive{#if kr.pts > 0}
								· <b class="font-display font-extrabold text-success">+{kr.pts}</b>{/if}
						</span>
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each kr.teams as t (t.team)}
							<span
								class="inline-flex items-center gap-1.5 rounded-[7px] px-2 py-1 font-display text-[10.5px] font-bold tracking-[0.04em] {t.state ===
								'hit'
									? 'bg-success/15 text-success'
									: t.state === 'out'
									? 'bg-base-300/35 text-base-content/55 opacity-60'
									: 'bg-base-300/35 text-base-content/70'}"
							>
								<FlagCode team={t.team} alive={t.state !== 'out'} size="sm" />
								{#if t.state === 'hit'}<span class="text-[9px] font-extrabold">✓</span>
								{:else if t.state === 'out'}<span class="text-[9px] font-extrabold text-error"
										>✗</span
									>
								{:else}<span class="text-[9px] font-extrabold text-base-content/30">·</span>{/if}
							</span>
						{:else}
							<span class="text-xs text-base-content/40">no picks recorded</span>
						{/each}
					</div>
				</div>
			{/each}
		</section>

		<!-- group picks — latest matchday first -->
		<section class="mt-4">
			<div class="mb-2 flex items-baseline justify-between gap-2.5">
				<h3 class="flex-none whitespace-nowrap font-hero text-[17px] tracking-[0.05em]">
					Group stage picks
				</h3>
				<span class="text-right text-[10.5px] text-base-content/55">latest round first</span>
			</div>
			{#each dayBuckets as bucket (bucket.day)}
				<div class="mb-3">
					<div
						class="mb-1 flex items-baseline justify-between rounded-[7px] bg-base-300/30 px-2.5 py-1 text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-base-content/55"
					>
						<span>Matchday {bucket.day}</span>
						<b class="font-display normal-case tracking-normal text-base-content/70"
							>+{bucket.pts} pts</b
						>
					</div>
					{#each bucket.picks as pick (pick.fixture_id)}
						{@const f = fx(pick.fixture_id)}
						<div
							class="grid grid-cols-[1fr_40px_104px] items-center gap-2 rounded-[7px] px-2.5 py-1 hover:bg-base-content/5"
						>
							<span class="flex min-w-0 items-center gap-1.5 text-[11px] text-base-content/70">
								<FlagCode team={pick.home_team ?? ''} size="sm" />
								{#if f?.status === 'live' || f?.status === 'halftime'}
									<b class="min-w-[30px] text-center font-display text-[11.5px] font-extrabold"
										>{f?.score?.home_score ?? 0}-{f?.score?.away_score ?? 0}</b
									>
									<span class="text-[9px] font-extrabold text-error animate-pulse-soft"
										>{f?.minute ?? ''}′</span
									>
								{:else if f?.score}
									<b class="min-w-[30px] text-center font-display text-[11.5px] font-extrabold"
										>{f.score.home_score}-{f.score.away_score}</b
									>
								{:else}
									<span class="min-w-[30px] text-center text-[10px] text-base-content/40"
										>{kickoffShort(pick.kickoff)}</span
									>
								{/if}
								<FlagCode team={pick.away_team ?? ''} size="sm" />
							</span>
							<span class="text-center font-display text-[11.5px] font-bold text-base-content/55"
								>{pick.home_score}-{pick.away_score}</span
							>
							<span class="justify-self-end">
								<PointsCellGroup points={pick.points ?? null} />
							</span>
						</div>
					{/each}
				</div>
			{/each}
		</section>

		<!-- bonus questions -->
		<section class="mt-4">
			<div class="mb-2 flex items-baseline justify-between gap-2.5">
				<h3 class="flex-none whitespace-nowrap font-hero text-[17px] tracking-[0.05em]">
					Bonus questions
				</h3>
			</div>
			<div class="flex flex-col gap-1.5">
				{#each bonusRows as bq (bq.question_id)}
					<div
						class="grid grid-cols-[1fr_auto_44px] items-center gap-2.5 rounded-[9px] px-2.5 py-1.5 {bq.hit ===
						true
							? 'bg-success/[0.07]'
							: 'bg-base-300/20'}"
					>
						<span class="flex items-baseline gap-2 text-[11.5px] text-base-content/70">
							<span class="font-display text-[9.5px] font-extrabold text-base-content/55"
								>Q{bq.n}</span
							>
							<span class="leading-snug">{bq.label}</span>
						</span>
						<span class="whitespace-nowrap text-[11.5px] font-bold text-base-content"
							>{bq.answer}</span
						>
						{#if bq.hit === true}
							<span
								class="rounded-badge bg-success/15 px-1.5 py-0.5 text-center font-display text-[11px] font-extrabold text-success"
								>+{bq.points}</span
							>
						{:else if bq.hit === false}
							<span class="text-center font-display text-[11px] font-extrabold text-base-content/30"
								>0</span
							>
						{:else}
							<span
								class="rounded-badge bg-base-300/40 px-1.5 py-0.5 text-center text-[9px] font-bold text-base-content/55"
								>pending</span
							>
						{/if}
					</div>
				{:else}
					<span class="text-xs text-base-content/40">no bonus answers recorded</span>
				{/each}
			</div>
		</section>

		<!-- footer -->
		<div class="mt-4 border-t border-base-300/45 pt-3 text-[10.5px] leading-relaxed text-base-content/55">
			Open pool — every entry's predictions are visible. All picks locked before kick-off.
		</div>
	{/if}
</aside>

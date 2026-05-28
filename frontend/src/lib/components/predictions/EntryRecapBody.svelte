<!--
	EntryRecapBody — shared recap of all predictions in an entry.

	Used by:
	  · PrintPreviewModal (mode="print")  — wrapped in modal chrome + print stylesheet
	  · SubmitSummary    (mode="review") — wrapped in submission status panel

	Sections:
	  1. Header — brand mark, player/entry, and an optional 2-col identity/metadata grid
	     (Where you work, Contact at Atlas/JMFA, Who you paid the fee to / Ref, Status, Rendered on)
	  2. Group Stage — all 48 fixtures with predicted scores (or "_ – _")
	  3. Knockout Bracket — resolved matchups per round ("Team A vs Team B") + champion
	  4. Bonus Questions — Q + A pairs

	Edit affordances appear only in review mode (showEditLinks={true}); they
	dispatch `editStep` so the parent (wizard page) can switch active step.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { FixturesByGroup, BracketPrediction, Employer } from '$types';
	import type { BonusQuestion } from '$api/bonus';
	import { user } from '$stores/auth';
	import {
		predictionToBracketState,
		getDisplayMatches,
		type GroupStandingsMap
	} from '$lib/utils/bracketResolver';

	export let entryName: string = '';
	export let entryRef: string = '';
	export let playerName: string = '';
	export let groupFixtures: FixturesByGroup[] = [];
	/** Map of fixture_id → { home: string; away: string } (may be empty string for no pick) */
	export let scoreValueMap: Map<string, { home: string; away: string }> = new Map();
	export let displayBracket: BracketPrediction | null = null;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: Map<string, string> = new Map();

	/**
	 * Group standings used to resolve knockout matchups (R32 / R16 / QF) into
	 * concrete "Team A vs Team B" pairings via bracketResolver. When absent,
	 * the component falls back to the legacy "comma-joined advancing teams"
	 * rendering — preserves behaviour for callers that haven't been wired up
	 * yet.
	 */
	export let groupStandings: GroupStandingsMap | null = null;

	/**
	 * Optional submission metadata for the identity/metadata header block.
	 * When provided alongside `entryRef`, the recap renders the receipt-
	 * style header (Where you work / Contact / Paid-to / Ref / Status /
	 * Rendered on). When `null`, only the minimal Player+Entry header shows.
	 *
	 * `status` is the entry-level state; `statusAt` is the timestamp of the
	 * most relevant change (last save for DRAFT, submission for SUBMITTED).
	 */
	export let submissionMeta: {
		status: 'draft' | 'submitted' | 'withdrawn';
		statusAt: string; // ISO datetime string
	} | null = null;

	/**
	 * When false, the Status row in the identity/metadata header is omitted.
	 * SubmitSummary sets this false because the user is by-definition in a
	 * draft state inside the Submit step — "Status: Draft (as at …)" adds
	 * no information there. Print Preview keeps the default `true` because
	 * the receipt benefits from the timestamp.
	 */
	export let showStatus: boolean = true;

	/**
	 * Visual mode:
	 *  - 'print' → typography + density tuned for paper / print modal (current PrintPreviewModal look).
	 *  - 'review' → slightly bigger type for in-page reading inside the wizard's Submit step.
	 */
	export let mode: 'print' | 'review' = 'print';

	/**
	 * When true, render a small "Edit" link next to each section heading
	 * that dispatches `editStep`. Off by default (print mode never needs them).
	 */
	export let showEditLinks: boolean = false;

	const dispatch = createEventDispatcher<{
		editStep: { step: 'groups' | 'knockout' | 'bonus' };
	}>();

	const EMPLOYER_LABELS: Record<Employer, string> = {
		atlas: 'Atlas',
		jmfa: 'JMFA',
		neither: 'Neither'
	};

	const ROUND_LABELS: Record<string, string> = {
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_finals: 'Quarter-Finals',
		semi_finals: 'Semi-Finals',
		final: 'Final'
	};

	const ROUND_ORDER = [
		'round_of_32',
		'round_of_16',
		'quarter_finals',
		'semi_finals',
		'final'
	] as const;

	// Grid columns per round. R32+R16 → 3 cols, QF → 2 cols, SF + Final → 1 col.
	const ROUND_COLS: Record<(typeof ROUND_ORDER)[number], string> = {
		round_of_32: 'grid grid-cols-3 gap-x-6 gap-y-1',
		round_of_16: 'grid grid-cols-3 gap-x-6 gap-y-1',
		quarter_finals: 'grid grid-cols-2 gap-x-6 gap-y-1',
		semi_finals: '',
		final: ''
	};

	function scoreDisplay(fixtureId: string): string {
		const s = scoreValueMap.get(fixtureId);
		if (!s || (s.home === '' && s.away === '')) return '_ – _';
		return `${s.home === '' ? '_' : s.home} – ${s.away === '' ? '_' : s.away}`;
	}

	// Resolved bracket state when standings are available — concrete team
	// names for every round, with TBD fallbacks for unresolved slots.
	$: bracketState =
		groupStandings && displayBracket
			? predictionToBracketState(displayBracket, groupStandings)
			: null;

	function fmtDateTime(iso: string | null | undefined): string {
		if (!iso) return '—';
		try {
			return new Date(iso).toLocaleString('en-GB', {
				dateStyle: 'medium',
				timeStyle: 'short'
			});
		} catch {
			return iso;
		}
	}

	function statusLabel(meta: NonNullable<typeof submissionMeta>): string {
		const ts = fmtDateTime(meta.statusAt);
		const label =
			meta.status === 'submitted'
				? 'Submitted'
				: meta.status === 'withdrawn'
					? 'Withdrawn'
					: 'Draft';
		return `${label} (as at ${ts})`;
	}

	const renderedOn = new Date().toLocaleString('en-GB', {
		dateStyle: 'medium',
		timeStyle: 'short'
	});

	// Legacy fallback path (no standings) — flat list of advancing teams per round.
	function bracketTeams(stage: keyof BracketPrediction): string[] {
		if (!displayBracket) return [];
		const val = displayBracket[stage];
		if (!val) return [];
		if (Array.isArray(val)) return val.filter(Boolean) as string[];
		return [];
	}

	$: containerTextSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: fixtureTextSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: heading2Size = mode === 'review' ? 'text-lg' : 'text-base';
	$: bonusItemSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: sectionDividerMt = mode === 'review' ? 'mt-6 pt-4' : 'mt-4 pt-3';

	// Winner highlight: gold in the on-screen submission panel (review mode);
	// underline-only in the printable receipt (print mode) so it survives
	// grayscale printing and works on a white background — no colour.
	$: winnerClass = mode === 'print' ? 'font-bold underline' : 'font-bold text-primary';
	$: loserClass = 'font-normal text-base-content/80';
	// Group-stage score chip: gold on screen, just bold on print so the
	// printed receipt stays colour-free overall.
	$: scoreClass = mode === 'print' ? 'font-bold px-1' : 'font-bold px-1 text-primary';

	/** Group-stage fixture outcome from the user's predicted score. */
	function fixtureOutcome(
		fixtureId: string
	): 'home' | 'away' | 'draw' | 'unset' {
		const s = scoreValueMap.get(fixtureId);
		if (!s) return 'unset';
		const h = parseInt(s.home, 10);
		const a = parseInt(s.away, 10);
		if (Number.isNaN(h) || Number.isNaN(a)) return 'unset';
		if (h > a) return 'home';
		if (a > h) return 'away';
		return 'draw';
	}
</script>

<div class="entry-recap {mode === 'review' ? 'mode-review' : 'mode-print'}">
	<!-- ── Header ──────────────────────────────────────── -->
	<div class="mb-4 pb-3 border-b-2 border-base-content/20">
		<div class="font-display text-xl tracking-wide uppercase mb-1">Atlas World Cup 2026 Pools</div>
		<div class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-base-content/70 font-mono">
			<span>Player: <span class="text-base-content font-medium">{playerName}</span></span>
			<span>Entry: <span class="text-base-content font-medium">{entryName}</span></span>
		</div>

		{#if submissionMeta && $user}
			<!-- 2-col identity / metadata receipt block. Identity on the left,
			     metadata on the right; "Contact at Atlas or JMFA" only shows
			     when employer is "Neither". -->
			<div class="grid grid-cols-2 gap-x-8 gap-y-1 mt-3 text-xs font-mono">
				<!-- Column 1: identity -->
				<div class="space-y-1">
					<div>
						<span class="uppercase tracking-wider text-base-content/50">Where you work:</span>
						<span class="text-base-content font-medium ml-1">
							{$user.employer ? EMPLOYER_LABELS[$user.employer] : '—'}
						</span>
					</div>
					{#if $user.employer === 'neither'}
						<div>
							<span class="uppercase tracking-wider text-base-content/50">Contact at Atlas / JMFA:</span>
							<span class="text-base-content font-medium ml-1">{$user.company_contact || '—'}</span>
						</div>
					{/if}
					<div>
						<span class="uppercase tracking-wider text-base-content/50">Paid the fee to:</span>
						<span class="text-base-content font-medium ml-1">{$user.paid_to || '—'}</span>
					</div>
				</div>
				<!-- Column 2: metadata -->
				<div class="space-y-1">
					{#if entryRef}
						<div>
							<span class="uppercase tracking-wider text-base-content/50">Ref:</span>
							<span class="text-base-content font-medium ml-1">{entryRef}</span>
						</div>
					{/if}
					{#if showStatus}
						<div>
							<span class="uppercase tracking-wider text-base-content/50">Status:</span>
							<span class="text-base-content font-medium ml-1">{statusLabel(submissionMeta)}</span>
						</div>
					{/if}
					<div>
						<span class="uppercase tracking-wider text-base-content/50">Rendered on:</span>
						<span class="text-base-content font-medium ml-1">{renderedOn}</span>
					</div>
				</div>
			</div>
		{:else if entryRef}
			<!-- Minimal fallback when submissionMeta not provided (preserves legacy callers). -->
			<div class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-base-content/70 font-mono mt-1">
				<span>Ref: <span class="text-base-content font-medium">{entryRef}</span></span>
				<span>Rendered on: <span class="text-base-content font-medium">{renderedOn}</span></span>
			</div>
		{/if}
	</div>

	<!-- ── Group Stage ──────────────────────────────── -->
	<div class="flex items-baseline justify-between mb-2 print:break-inside-avoid">
		<h2 class="font-display {heading2Size} tracking-wide uppercase">
			Group Stage <span class="text-xs font-normal text-base-content/40 normal-case">{groupFixtures.reduce((n, g) => n + g.fixtures.length, 0)} matches</span>
		</h2>
		{#if showEditLinks}
			<button
				type="button"
				class="btn btn-ghost btn-xs text-base-content/60 hover:text-primary"
				on:click={() => dispatch('editStep', { step: 'groups' })}
			>
				Edit
			</button>
		{/if}
	</div>

	{#each groupFixtures.filter((g) => g.group !== 'thirdplace') as g}
		<div class="mb-3 print:break-inside-avoid">
			<h3 class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Group {g.group}</h3>
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
				{#each g.fixtures as f}
						{@const outcome = fixtureOutcome(f.id)}
						<div class="flex items-center gap-1 py-0.5 font-mono {fixtureTextSize}">
							<span class="text-base-content/40 w-6 flex-shrink-0 text-right">{f.match_number ?? ''}.</span>
							<span class="flex-1 text-right truncate {outcome === 'home' ? winnerClass : loserClass}">{f.home_team}</span>
							<span class={scoreClass}>{scoreDisplay(f.id)}</span>
							<span class="flex-1 truncate {outcome === 'away' ? winnerClass : loserClass}">{f.away_team}</span>
						</div>
				{/each}
			</div>
		</div>
	{/each}

	<!-- ── Knockout Bracket ─────────────────────────── -->
	<div class="{sectionDividerMt} border-t border-base-content/10">
		<div class="flex items-baseline justify-between mb-2">
			<h2 class="font-display {heading2Size} tracking-wide uppercase">Knockout Bracket</h2>
			{#if showEditLinks}
				<button
					type="button"
					class="btn btn-ghost btn-xs text-base-content/60 hover:text-primary"
					on:click={() => dispatch('editStep', { step: 'knockout' })}
				>
					Edit
				</button>
			{/if}
		</div>

		{#each ROUND_ORDER as stage}
			{#if bracketState}
				{@const matches = getDisplayMatches(bracketState, stage)}
				{#if matches.length > 0}
					<div class="mb-3 print:break-inside-avoid">
						<span class="text-xs font-bold uppercase tracking-widest text-base-content/50">{ROUND_LABELS[stage]}</span>
						<div class="{ROUND_COLS[stage]} font-mono {fixtureTextSize} mt-1 ml-2">
							{#each matches as m}
							{@const homeWins = !!m.winner && m.winner === m.homeTeam}
							{@const awayWins = !!m.winner && m.winner === m.awayTeam}
							<div>
								<span class={homeWins ? winnerClass : loserClass}>{m.homeTeam ?? 'TBD'}</span>
								<span class="text-base-content/40 mx-1">vs</span>
								<span class={awayWins ? winnerClass : loserClass}>{m.awayTeam ?? 'TBD'}</span>
							</div>
							{/each}
						</div>
					</div>
				{/if}
			{:else}
				<!-- Legacy fallback: list advancing teams (no standings provided). -->
				{@const teams = bracketTeams(stage)}
				{#if teams.length > 0}
					<div class="mb-2 print:break-inside-avoid">
						<span class="text-xs font-bold uppercase tracking-widest text-base-content/50">{ROUND_LABELS[stage]}</span>
						{#if stage === 'semi_finals' || stage === 'final'}
							<div class="font-mono {fixtureTextSize} mt-0.5 ml-2">
								{#each Array(Math.floor(teams.length / 2)) as _, i}
									<div>{teams[i * 2] ?? '?'} <span class="text-base-content/40">v</span> {teams[i * 2 + 1] ?? '?'}</div>
								{/each}
							</div>
						{:else}
							<div class="font-mono {fixtureTextSize} mt-0.5 ml-2 text-base-content/80">
								{teams.join(', ')}
							</div>
						{/if}
					</div>
				{/if}
			{/if}
		{/each}

		<!-- Champion -->
		<div class="mt-2 flex items-center gap-2">
			<span class="text-base">🏆</span>
			{#if displayBracket?.winner}
				<span class="font-display {heading2Size} tracking-wide">{displayBracket.winner}</span>
			{:else}
				<span class="text-base-content/40 italic text-sm">Not selected</span>
			{/if}
		</div>
	</div>

	<!-- ── Bonus Questions ────────────────────────── -->
	{#if bonusQuestions.length > 0}
		<div class="{sectionDividerMt} border-t border-base-content/10">
			<div class="flex items-baseline justify-between mb-2">
				<h2 class="font-display {heading2Size} tracking-wide uppercase">Bonus Questions</h2>
				{#if showEditLinks}
					<button
						type="button"
						class="btn btn-ghost btn-xs text-base-content/60 hover:text-primary"
						on:click={() => dispatch('editStep', { step: 'bonus' })}
					>
						Edit
					</button>
				{/if}
			</div>
			<ol class="space-y-1">
				{#each bonusQuestions as q, i}
					{@const answer = bonusAnswers.get(q.id)}
					<li class="flex gap-2 {bonusItemSize} font-mono">
						<span class="text-base-content/40 w-5 flex-shrink-0 text-right">{i + 1}.</span>
						<span class="flex-1">{q.label}</span>
						{#if answer}
							<span class="font-medium">{answer}</span>
						{:else}
							<span class="text-base-content/30 italic">not answered</span>
						{/if}
					</li>
				{/each}
			</ol>
		</div>
	{/if}
</div>

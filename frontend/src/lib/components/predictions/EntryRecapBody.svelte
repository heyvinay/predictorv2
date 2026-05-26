<!--
	EntryRecapBody — shared recap of all predictions in an entry.

	Used by:
	  · PrintPreviewModal (mode="print")  — wrapped in modal chrome + print stylesheet
	  · SubmitSummary    (mode="review") — wrapped in submission status panel

	Sections:
	  1. Header — entry name, player, date, ref
	  2. Group Stage — all 48 fixtures with predicted scores (or "_ – _")
	  3. Knockout Bracket — advancing teams per round + champion
	  4. Bonus Questions — Q + A pairs

	Edit affordances appear only in review mode (showEditLinks={true}); they
	dispatch `editStep` so the parent (wizard page) can switch active step.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';

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
	 * Visual mode:
	 *  - 'print' → typography + density tuned for paper / print modal (current PrintPreviewModal look).
	 *  - 'review' → slightly bigger type for in-page reading inside the wizard's Submit step.
	 *
	 * The two modes use very similar markup; only sizes/spacing differ via a few
	 * conditional class strings. This keeps the data + helper logic shared.
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

	const today = new Date().toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'long',
		year: 'numeric'
	});

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

	function scoreDisplay(fixtureId: string): string {
		const s = scoreValueMap.get(fixtureId);
		if (!s || (s.home === '' && s.away === '')) return '_ – _';
		return `${s.home === '' ? '_' : s.home} – ${s.away === '' ? '_' : s.away}`;
	}

	function bracketTeams(stage: keyof BracketPrediction): string[] {
		if (!displayBracket) return [];
		const val = displayBracket[stage];
		if (!val) return [];
		if (Array.isArray(val)) return val.filter(Boolean) as string[];
		return [];
	}

	// Mode-conditional size classes — kept in one place so the contrast
	// between print and review is easy to scan. Print stays exactly as it
	// was in PrintPreviewModal; review bumps text up one Tailwind step.
	$: containerTextSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: fixtureTextSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: heading2Size = mode === 'review' ? 'text-lg' : 'text-base';
	$: bonusItemSize = mode === 'review' ? 'text-sm' : 'text-xs';
	$: sectionDividerMt = mode === 'review' ? 'mt-6 pt-4' : 'mt-4 pt-3';
</script>

<!-- The whole recap. PrintPreviewModal wraps this inside `.print-preview-target`
     so the print stylesheet in app.css can scope to its descendants. -->
<div class="entry-recap {mode === 'review' ? 'mode-review' : 'mode-print'}">
	<!-- ── Header ──────────────────────────────────────── -->
	<div class="mb-4 pb-3 border-b-2 border-base-content/20">
		<div class="font-display text-xl tracking-wide uppercase mb-1">World Cup 2026 — Predictor</div>
		<div class="grid grid-cols-2 gap-x-4 gap-y-0.5 {containerTextSize === 'text-sm' ? 'text-xs' : 'text-xs'} text-base-content/70 font-mono">
			<span>Player: <span class="text-base-content font-medium">{playerName}</span></span>
			<span>{mode === 'print' ? 'Printed' : 'As of'}: <span class="text-base-content font-medium">{today}</span></span>
			<span>Entry: <span class="text-base-content font-medium">{entryName}</span></span>
			{#if entryRef}
				<span>Ref: <span class="text-base-content font-medium">{entryRef}</span></span>
			{/if}
		</div>
	</div>

	<!-- ── Group Stage ──────────────────────────────── -->
	<div class="flex items-baseline justify-between mb-2">
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
		<div class="mb-3">
			<h3 class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Group {g.group}</h3>
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
				{#each g.fixtures as f}
					<div class="flex items-center gap-1 py-0.5 font-mono {fixtureTextSize}">
						<span class="text-base-content/40 w-6 flex-shrink-0 text-right">{f.match_number ?? ''}.</span>
						<span class="flex-1 text-right truncate">{f.home_team}</span>
						<span class="font-bold px-1 text-primary">{scoreDisplay(f.id)}</span>
						<span class="flex-1 truncate">{f.away_team}</span>
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
			{@const teams = bracketTeams(stage)}
			{#if teams.length > 0}
				<div class="mb-2">
					<span class="text-xs font-bold uppercase tracking-widest text-base-content/50">{ROUND_LABELS[stage]}</span>
					{#if stage === 'semi_finals' || stage === 'final'}
						<!-- Show as matchups for later rounds -->
						<div class="font-mono {fixtureTextSize} mt-0.5 ml-2">
							{#each Array(Math.floor(teams.length / 2)) as _, i}
								<div>{teams[i * 2] ?? '?'} <span class="text-base-content/40">v</span> {teams[i * 2 + 1] ?? '?'}</div>
							{/each}
						</div>
					{:else}
						<!-- List advancing teams -->
						<div class="font-mono {fixtureTextSize} mt-0.5 ml-2 text-base-content/80">
							{teams.join(', ')}
						</div>
					{/if}
				</div>
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

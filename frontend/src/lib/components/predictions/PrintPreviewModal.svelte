<!--
	PrintPreviewModal — dual-use summary of all predictions.

	Used for:
	  (a) Pre-submission "confirm everything on one page" review
	  (b) Post-submission permanent record

	Sections:
	  1. Header — entry name, player, date
	  2. Group Stage — all 48 fixtures with predicted scores (or _ – _)
	  3. Knockout Bracket — advancing teams listed per round
	  4. Bonus Questions — numbered Q + A pairs

	Print: window.print() + @media print in app.css hides all chrome except
	the .print-preview-target div.
-->
<script lang="ts">
	import type { FixturesByGroup, BracketPrediction } from '$types';
	import type { BonusQuestion } from '$api/bonus';

	export let open: boolean = false;
	export let entryName: string = '';
	export let entryRef: string = '';
	export let playerName: string = '';
	export let groupFixtures: FixturesByGroup[] = [];
	/** Map of fixture_id → { home: string; away: string } (may be empty string for no pick) */
	export let scoreValueMap: Map<string, { home: string; away: string }> = new Map();
	export let displayBracket: BracketPrediction | null = null;
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: Map<string, string> = new Map();
	export let onClose: () => void = () => {};

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

	function handlePrint() {
		window.print();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4"
		on:click|self={onClose}
		on:keydown={handleKeydown}
	>
		<!-- Modal shell -->
		<div class="bg-base-100 w-full sm:max-w-2xl sm:rounded-xl flex flex-col max-h-[90dvh] sm:max-h-[85dvh]">
			<!-- Header bar -->
			<div class="flex items-center justify-between px-4 py-3 border-b border-base-300/50 flex-shrink-0">
				<span class="font-display text-base tracking-wide">Prediction Summary</span>
				<button type="button" class="btn btn-ghost btn-sm btn-square" on:click={onClose} aria-label="Close">
					<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Scrollable content — this div gets the print-preview-target class -->
			<div class="print-preview-target overflow-y-auto flex-1 px-4 py-4 text-sm">

				<!-- ── Print header ──────────────────────────────────────── -->
				<div class="mb-4 pb-3 border-b-2 border-base-content/20">
					<div class="font-display text-xl tracking-wide uppercase mb-1">World Cup 2026 — Predictor</div>
					<div class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-base-content/70 font-mono">
						<span>Player: <span class="text-base-content font-medium">{playerName}</span></span>
						<span>Printed: <span class="text-base-content font-medium">{today}</span></span>
						<span>Entry: <span class="text-base-content font-medium">{entryName}</span></span>
						{#if entryRef}
							<span>Ref: <span class="text-base-content font-medium">{entryRef}</span></span>
						{/if}
					</div>
				</div>

				<!-- ── Group Stage ───────────────────────────────────────── -->
				<h2 class="font-display text-base tracking-wide uppercase mb-2">
					Group Stage <span class="text-xs font-normal text-base-content/40 normal-case">{groupFixtures.reduce((n, g) => n + g.fixtures.length, 0)} matches</span>
				</h2>

				{#each groupFixtures.filter(g => g.group !== 'thirdplace') as g}
					<div class="mb-3">
						<h3 class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Group {g.group}</h3>
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
							{#each g.fixtures as f}
								<div class="flex items-center gap-1 py-0.5 font-mono text-xs">
									<span class="text-base-content/40 w-6 flex-shrink-0 text-right">{f.match_number ?? ''}.</span>
									<span class="flex-1 text-right truncate">{f.home_team}</span>
									<span class="font-bold px-1 text-primary">{scoreDisplay(f.id)}</span>
									<span class="flex-1 truncate">{f.away_team}</span>
								</div>
							{/each}
						</div>
					</div>
				{/each}

				<!-- ── Knockout Bracket ──────────────────────────────────── -->
				<div class="mt-4 pt-3 border-t border-base-content/10">
					<h2 class="font-display text-base tracking-wide uppercase mb-2">Knockout Bracket</h2>

					{#each ROUND_ORDER as stage}
						{@const teams = bracketTeams(stage)}
						{#if teams.length > 0}
							<div class="mb-2">
								<span class="text-xs font-bold uppercase tracking-widest text-base-content/50">{ROUND_LABELS[stage]}</span>
								{#if stage === 'semi_finals' || stage === 'final'}
									<!-- Show as matchups for later rounds -->
									<div class="font-mono text-xs mt-0.5 ml-2">
										{#each Array(Math.floor(teams.length / 2)) as _, i}
											<div>{teams[i * 2] ?? '?'} <span class="text-base-content/40">v</span> {teams[i * 2 + 1] ?? '?'}</div>
										{/each}
									</div>
								{:else}
									<!-- List advancing teams -->
									<div class="font-mono text-xs mt-0.5 ml-2 text-base-content/80">
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
							<span class="font-display text-base tracking-wide">{displayBracket.winner}</span>
						{:else}
							<span class="text-base-content/40 italic text-sm">Not selected</span>
						{/if}
					</div>
				</div>

				<!-- ── Bonus Questions ───────────────────────────────────── -->
				{#if bonusQuestions.length > 0}
					<div class="mt-4 pt-3 border-t border-base-content/10">
						<h2 class="font-display text-base tracking-wide uppercase mb-2">Bonus Questions</h2>
						<ol class="space-y-1">
							{#each bonusQuestions as q, i}
								{@const answer = bonusAnswers.get(q.id)}
								<li class="flex gap-2 text-xs font-mono">
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

			<!-- Footer: Close + Print -->
			<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/50 flex-shrink-0">
				<button type="button" class="btn btn-ghost btn-sm" on:click={onClose}>Close</button>
				<button type="button" class="btn btn-outline btn-sm gap-1" on:click={handlePrint}>
					🖨 Print
				</button>
			</div>
		</div>
	</div>
{/if}

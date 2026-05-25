<script lang="ts">
	// Public rules page. No auth gate — prospective joiners should be able
	// to read this before signing up. Pulls live values from the public
	// /api/competition/info and /api/predictions/bonus/questions endpoints
	// with sensible static fallbacks so the first paint is correct even if
	// the API is unreachable.
	import { onMount } from 'svelte';
	import { getCompetitionInfo, type CompetitionInfo } from '$api/competition';
	import { getBonusQuestions, type BonusQuestion } from '$api/bonus';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';

	let info: CompetitionInfo | null = null;
	let bonusQuestions: BonusQuestion[] = [];

	/** Cap of the rarity bonus — matches `match.rarity_cap` in
	 *  config/worldcup2026.yml. Hardcoded here because this is the public
	 *  rules page (no auth → no /scoring-config call). Touch both if you
	 *  tune the value. */
	const RARITY_CAP = 10;

	/** Group consecutive correct-predictor counts (1..P) that yield the
	 *  same logarithmic rarity bonus into bands so the published table is
	 *  compact (e.g. "5–6 of 30 → +3"). */
	function rarityBands(
		totalPredictors: number,
		cap: number
	): Array<{ countLabel: string; bonus: number }> {
		if (totalPredictors <= 0) return [];
		const bands: Array<{ countLabel: string; bonus: number }> = [];
		let bandStart = 1;
		let bandBonus = logarithmicRarityBonus(totalPredictors, 1, cap);
		for (let k = 2; k <= totalPredictors; k++) {
			const r = logarithmicRarityBonus(totalPredictors, k, cap);
			if (r !== bandBonus) {
				bands.push({
					countLabel: bandStart === k - 1 ? `${bandStart}` : `${bandStart}–${k - 1}`,
					bonus: bandBonus
				});
				bandStart = k;
				bandBonus = r;
			}
		}
		bands.push({
			countLabel:
				bandStart === totalPredictors ? `${bandStart}` : `${bandStart}–${totalPredictors}`,
			bonus: bandBonus
		});
		return bands;
	}

	// Fall back to 30 (the design anchor for the rarity formula) before
	// /competition/info loads, so the table renders on first paint.
	$: rarityPredictorCount = info?.total_players ?? 30;
	$: rarityRows = rarityBands(rarityPredictorCount, RARITY_CAP);

	onMount(async () => {
		try {
			[info, bonusQuestions] = await Promise.all([
				getCompetitionInfo(),
				getBonusQuestions()
			]);
		} catch (_e) {
			// Public endpoints — failure usually means backend is down. Page
			// still renders with hardcoded defaults below.
		}
	});

	function fmtCurrency(n: number): string {
		if (!n || n === 0) return '—';
		return `€${n.toFixed(0)}`;
	}

	function fmtDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	$: poolTotal =
		info && info.entry_fee && info.paid_players
			? info.entry_fee * info.paid_players
			: 0;

	const CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		top_flop: 'Top / Flop',
		awards: 'Awards'
	};
	$: bonusByCategory = (() => {
		const groups: Record<string, BonusQuestion[]> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const q of bonusQuestions) {
			(groups[q.category] ?? (groups[q.category] = [])).push(q);
		}
		return groups;
	})();

	const BRACKET_STAGES: { lbl: string; pts: number; winner?: boolean }[] = [
		{ lbl: 'Group advance', pts: 10 },
		{ lbl: 'Group position', pts: 5 },
		{ lbl: 'Round of 32', pts: 10 },
		{ lbl: 'Round of 16', pts: 15 },
		{ lbl: 'Quarter-final', pts: 20 },
		{ lbl: 'Semi-final', pts: 40 },
		{ lbl: 'Final', pts: 60 },
		{ lbl: 'Tournament winner', pts: 100, winner: true }
	];
</script>

<svelte:head>
	<title>Rules - Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6 max-w-4xl">
	<!-- Hero -->
	<div class="stadium-card p-6">
		<h1 class="text-4xl font-display tracking-wide mb-2">The <span class="text-gradient">Rules</span></h1>
		<p class="text-sm text-base-content/60 mb-4">
			How predictions, points and prizes work in {info?.name ?? 'FIFA World Cup 2026'}.
		</p>
		<div class="grid grid-cols-3 gap-3">
			<div class="stat-card"><p class="stat-title">Entry fee</p><p class="stat-value text-2xl">{info ? fmtCurrency(info.entry_fee) : '—'}</p></div>
			<div class="stat-card"><p class="stat-title">Players signed up</p><p class="stat-value text-2xl">{info?.total_players ?? '—'}</p></div>
			<div class="stat-card"><p class="stat-title">Phase I lock</p><p class="text-sm font-semibold mt-2">{info ? fmtDate(info.phase1_deadline) : '—'}</p></div>
		</div>
	</div>

	<!-- 01 — The tournament -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">01 · The Tournament <span class="text-xs text-base-content/40">· FIFA 2026 · 48 teams</span></h2>
		<div class="space-y-2 text-sm text-base-content/80">
			<p>FIFA World Cup 2026 features <b>48 teams</b> drawn into <b>12 groups of 4</b>. Each group plays a single round-robin of three matches across the group stage.</p>
			<p>The top two teams from each group <b>advance directly</b> to the Round of 32. The eight best-ranked third-placed teams (across all 12 groups) <b>also advance</b>, filling the bracket to 32 teams. From there it's straight knockout: R32 → R16 → QF → SF → Final.</p>
		</div>
	</section>

	<!-- 02 — Phases -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">02 · Two Phases <span class="text-xs text-base-content/40">· Phase II points at 70% value</span></h2>
		<p class="text-sm text-base-content/80 mb-4">The competition is split into two phases. Phase I is the headline event — everything is up for grabs and predictions are made blind, before a ball is kicked. Phase II opens after the group stage, gives you a second crack at the bracket with full knowledge of who advanced, and is worth less per pick to keep Phase I players in the game.</p>
		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			<div class="rounded-xl border-2 border-accent/40 p-4">
				<h3 class="font-display text-xl tracking-wide mb-1">Phase <span class="text-accent">I</span></h3>
				<div class="text-xs text-base-content/50 mb-2">Locks at tournament start</div>
				<ul class="text-sm space-y-1 list-disc list-inside text-base-content/80">
					<li>Predict every group-stage match score</li>
					<li>Build a full knockout bracket from group winners</li>
					<li>Answer the 9 bonus questions</li>
					<li>All Phase I points are 1× face value</li>
				</ul>
			</div>
			<div class="rounded-xl border border-base-300 p-4">
				<h3 class="font-display text-xl tracking-wide mb-1">Phase <span class="text-primary">II</span></h3>
				<div class="text-xs text-base-content/50 mb-2">Opens after group stage · admin-activated</div>
				<ul class="text-sm space-y-1 list-disc list-inside text-base-content/80">
					<li>Re-build the bracket using <b>actual</b> group standings</li>
					<li>Predict the score of each knockout match</li>
					<li>Phase II points are scaled to <b>70%</b> of face value</li>
					<li>Phase I picks remain frozen — Phase II is additive</li>
				</ul>
			</div>
		</div>
	</section>

	<!-- 03 — Match scoring -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">03 · Scoring · Match Predictions <span class="text-xs text-base-content/40">· per match</span></h2>
		<p class="text-sm text-base-content/80 mb-4">For each match you predict, three things can earn you points. They stack — a perfectly-called exact score that nobody else got hits all three at once.</p>
		<div class="space-y-2">
			<div class="flex items-center gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-2xl tracking-wide w-20 text-center">5</span>
				<div><div class="font-semibold">Correct outcome</div><div class="text-xs text-base-content/50">Picking the right side (1/X/2). Awarded even if the exact score is wrong.</div></div>
			</div>
			<div class="flex items-center gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-2xl tracking-wide w-20 text-center text-success">+10</span>
				<div><div class="font-semibold">Exact score bonus</div><div class="text-xs text-base-content/50">Stacks on top of the outcome — 15 pts total if you nail the result.</div></div>
			</div>
			<div class="flex items-center gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-xl tracking-wide w-20 text-center text-accent">up to +10</span>
				<div>
					<div class="font-semibold">Rarity bonus</div>
					<div class="text-xs text-base-content/50">
						The fewer of your fellow predictors who picked the same outcome,
						the higher this bonus. Gated at 50% — consensus picks pay nothing
						extra. Derived from Shannon surprisal (the same logarithmic
						scoring rule used in forecasting tournaments), scaled so a uniquely
						correct call out of ~30 predictors hits the cap of +10.
					</div>
				</div>
			</div>
		</div>

		<!-- Rarity bonus table: how many predictors → bonus for the current pool size. -->
		<div class="mt-4 rounded-lg border border-base-300/60 overflow-hidden">
			<div class="flex items-baseline justify-between bg-base-300/60 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-base-content/70">
				<span>How many friends picked the same outcome as you</span>
				<span class="font-bold">Bonus</span>
			</div>
			{#each rarityRows as band (band.countLabel)}
				<div
					class="flex items-baseline justify-between px-3 py-2 border-t border-base-300/40 {band.bonus === RARITY_CAP
						? 'bg-accent/10'
						: ''} {band.bonus === 0 ? 'opacity-60' : ''}"
				>
					<span class="font-mono text-xs text-base-content/80">
						{band.countLabel} of {rarityPredictorCount}
					</span>
					<span
						class="font-display text-xl leading-none {band.bonus === RARITY_CAP
							? 'text-error'
							: band.bonus === 0
							? 'text-base-content/40'
							: 'text-accent'}"
					>
						{band.bonus > 0 ? `+${band.bonus}` : '—'}
					</span>
				</div>
			{/each}
			<div class="border-t-2 border-base-300/60 bg-base-200/40 px-3 py-2 font-mono text-[10px] tracking-wider text-base-content/50">
				Scales with how many friends predicted that fixture. Numbers shown
				assume all {rarityPredictorCount} of you submitted — bands shift if
				fewer predictors are in.
			</div>
		</div>
	</section>

	<!-- 04 — Bracket scoring -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">04 · Scoring · Bracket Advancements <span class="text-xs text-base-content/40">· per team-stage pick</span></h2>
		<p class="text-sm text-base-content/80 mb-4">Your bracket awards points for each team you correctly predict to reach a stage — cumulative through the bracket. Picking the champion who beat their final opponent awards the Winner points <i>plus</i> the Final points, plus their SF / QF / R16 / R32 stage points.</p>
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			{#each BRACKET_STAGES as s (s.lbl)}
				<div class="stat-card {s.winner ? 'border-accent/50' : ''}">
					<p class="stat-title">{s.lbl}</p>
					<p class="stat-value text-2xl {s.winner ? 'text-accent' : ''}">{s.pts}</p>
				</div>
			{/each}
		</div>
	</section>

	<!-- 05 — Bonus questions -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">05 · Bonus Questions <span class="text-xs text-base-content/40">· {bonusQuestions.length || 9} questions · lock with Phase I</span></h2>
		<p class="text-sm text-base-content/80 mb-4">A small set of pre-tournament wagers on side-stories beyond the bracket. Submit your picks before Phase I locks; the admin reveals the correct answer as each question resolves. Player-name answers are matched leniently — capitalisation and accents don't matter.</p>
		{#each ['group_stage', 'top_flop', 'awards'] as cat (cat)}
			{@const qs = bonusByCategory[cat] ?? []}
			{#if qs.length > 0}
				<h3 class="text-sm font-display uppercase tracking-wide mt-4 mb-2">{CATEGORY_LABEL[cat]}</h3>
				<div class="space-y-1.5">
					{#each qs as q (q.id)}
						<div class="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-base-300/30">
							<span class="text-sm">{q.label}</span>
							<span class="badge badge-accent">+{q.points}</span>
						</div>
					{/each}
				</div>
			{/if}
		{/each}
		{#if bonusQuestions.length === 0}
			<p class="text-xs text-base-content/50 mt-2">Loading bonus questions…</p>
		{/if}
	</section>

	<!-- 06 — Buy-in & pool -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">06 · Buy-in & Pool <span class="text-xs text-base-content/40">· cash, paid pre-tournament</span></h2>
		<p class="text-sm text-base-content/80 mb-4">Entry to the competition costs <b>{info ? fmtCurrency(info.entry_fee) : 'tbd'}</b> per player, payable to the admin before the tournament starts. Anyone who hasn't paid by Phase I lock can still play, but isn't eligible for the prize pool.</p>
		<div class="grid grid-cols-3 gap-3">
			<div class="stat-card"><p class="stat-title">Entry fee</p><p class="stat-value text-2xl">{info ? fmtCurrency(info.entry_fee) : '—'}</p><p class="text-xs text-base-content/40 mt-1">per player</p></div>
			<div class="stat-card"><p class="stat-title">Players paid</p><p class="stat-value text-2xl">{info?.paid_players ?? '—'}</p><p class="text-xs text-base-content/40 mt-1">of {info?.total_players ?? '—'} signed up</p></div>
			<div class="stat-card"><p class="stat-title">Pool (so far)</p><p class="stat-value text-2xl">{poolTotal > 0 ? fmtCurrency(poolTotal) : '—'}</p><p class="text-xs text-base-content/40 mt-1">grows as buy-ins land</p></div>
		</div>
		<p class="text-sm text-base-content/80 mt-4"><b>Prize distribution</b> is decided by the admin pre-tournament and announced in the group chat. A common split: <b>60 / 25 / 15</b> for 1st / 2nd / 3rd, or winner-takes-all for small pools. Final split is fixed before Phase I locks.</p>
	</section>

	<!-- 07 — Fine print -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">07 · The Fine Print <span class="text-xs text-base-content/40">· read once · then never again</span></h2>
		<div class="space-y-3 text-sm text-base-content/80">
			<div><b class="text-base-content">Per-match lock · 5 minutes before kickoff.</b> Once a match locks you can't change your prediction for it, regardless of phase.</div>
			<div><b class="text-base-content">Blind pool.</b> You can't see anyone else's pick for a match until that match locks. Rarity bonuses are computed once the field is set.</div>
			<div><b class="text-base-content">Score cap · 15 goals per side.</b> The wizard caps any single team's score at 15.</div>
			<div><b class="text-base-content">Phase I bracket gate.</b> The Phase I knockout bracket only opens once all group-stage matches have been predicted — it needs your predicted standings to seed R32.</div>
			<div><b class="text-base-content">Phase II is optional but recommended.</b> If the admin activates Phase II, you can re-build the bracket using actual group results. You're not penalised for skipping it.</div>
			<div><b class="text-base-content">Disputes.</b> If a fixture's score is corrected after the fact, the admin can update the result and the leaderboard recomputes on the next request.</div>
			<div><b class="text-base-content">Have fun.</b> This is a friend competition, not Vegas. Trash talk is encouraged.</div>
		</div>
	</section>
</div>

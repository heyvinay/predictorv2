<script lang="ts">
	// Public rules page. No auth gate — prospective joiners should be able
	// to read this before signing up. Pulls live values from the public
	// /api/competition/info and /api/predictions/bonus/questions endpoints
	// with sensible static fallbacks so the first paint is correct even if
	// the API is unreachable.
	//
	// SCORING NOTE: the rarity cap, outcome/exact/rarity match-scoring
	// numbers, the BRACKET_STAGES values, and the per-category BONUS_POINTS
	// map are all maintained BY HAND in this file (no public
	// /scoring-config endpoint exists). If you tune scoring config in
	// config/worldcup2026.yml, mirror the values here too — there's no
	// runtime check that the two are in sync. As of 2026-06-01, the YAML
	// has been brought up to match this file (both for bracket and bonus
	// points), so this page is once again the source of truth visible to
	// users — keep them aligned.
	import { onMount } from 'svelte';
	import { getCompetitionInfo, type CompetitionInfo } from '$api/competition';
	import { getBonusQuestions, type BonusQuestion } from '$api/bonus';
	import { logarithmicRarityBonus } from '$lib/utils/matchBreakdown';
	import { pageTitle } from '$stores/pageTitle';
	import CountdownTimer from '$components/predictions/CountdownTimer.svelte';

	let info: CompetitionInfo | null = null;
	let bonusQuestions: BonusQuestion[] = [];

	/** Cap of the rarity bonus — matches `match.rarity_cap` in
	 *  config/worldcup2026.yml. Hardcoded here because this is the public
	 *  rules page (no auth → no /scoring-config call). Touch both if you
	 *  tune the value. */
	const RARITY_CAP = 10;

	/** Worked-example sample size for the rarity-bonus table. Fixed at
	 *  100 for the pre-tournament window so the table is stable and easy
	 *  to read as percentages. Bump manually after the deadline once the
	 *  real predictor pool is known. */
	const rarityPredictorCount = 100;

	/** Per-category bonus point values, displayed against each bonus
	 *  question's badge. Mirror this in config/worldcup2026.yml
	 *  (bonus.points) when you tune — the runtime scoring engine uses
	 *  the YAML; this constant just dictates what the rules page
	 *  advertises. Both should agree. */
	const BONUS_POINTS: Record<string, number> = {
		group_stage: 15,
		top_flop: 20,
		awards: 20
	};

	/** Group consecutive correct-predictor counts (1..P) that yield the
	 *  same logarithmic rarity bonus into bands so the published table is
	 *  compact (e.g. "5–6 of 100 → +3"). */
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

	$: rarityRows = rarityBands(rarityPredictorCount, RARITY_CAP);

	onMount(async () => {
		pageTitle.set('Rules');
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

	const CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		// Internal `top_flop` literal stays; display flips to the longer
		// phrase so users understand these are knockout-stage outcomes.
		top_flop: 'Knockout Stage — Top / Flop',
		// Kept defensively in case awards questions are re-added.
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

	/** Six knockout-only bracket stages. Group-stage advancement is
	 *  rewarded via group-stage match scoring (outcome/exact/rarity), not
	 *  via a separate bracket point. Sync these values with the backend
	 *  scoring config when you tune. */
	const BRACKET_STAGES: { lbl: string; pts: number; winner?: boolean }[] = [
		{ lbl: 'Round of 32', pts: 20 },
		{ lbl: 'Round of 16', pts: 30 },
		{ lbl: 'Quarter-final', pts: 40 },
		{ lbl: 'Semi-final', pts: 50 },
		{ lbl: 'Final', pts: 75 },
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
		<p class="text-sm text-base-content/60 mb-2">
			How predictions, points and prizes work in {info?.name ?? 'FIFA World Cup 2026'}. Read the
			short version below — the long version is in the comments of every Sunday morning text
			thread you've ever been part of.
		</p>
		<p class="text-sm text-base-content/80 mb-4">
			Get all your picks in before the deadline shown — that's the only timer you need to watch.
		</p>
		<div class="grid grid-cols-2 gap-3">
			<div class="stat-card">
				<p class="stat-title">Entry fee</p>
				<p class="stat-value text-2xl">{info ? fmtCurrency(info.entry_fee) : '—'}</p>
				<p class="text-xs text-base-content/40 mt-1">per entry</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Predictions lock</p>
				<p class="text-sm font-semibold mt-2">{info ? fmtDate(info.phase1_deadline) : '—'}</p>
				{#if info?.phase1_deadline}
					<div class="mt-2">
						<CountdownTimer deadline={info.phase1_deadline} compact />
					</div>
				{/if}
			</div>
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

	<!-- 02 — Match scoring -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">02 · Scoring · Match Predictions <span class="text-xs text-base-content/40">· per match</span></h2>
		<p class="text-sm text-base-content/80 mb-4">For each match you predict — group stage or knockout — three things can earn you points. They stack — a perfectly-called exact score that nobody else got hits all three at once.</p>
		<div class="space-y-2">
			<div class="flex items-baseline gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-2xl tracking-wide w-20 text-center shrink-0">5</span>
				<div><div class="font-semibold">Correct outcome</div><div class="text-xs text-base-content/50">Picking the right side (1/X/2). Awarded even if the exact score is wrong.</div></div>
			</div>
			<div class="flex items-baseline gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-2xl tracking-wide w-20 text-center text-success shrink-0">+10</span>
				<div><div class="font-semibold">Exact score bonus</div><div class="text-xs text-base-content/50">Stacks on top of the outcome — 15 pts total if you nail the result.</div></div>
			</div>
			<div class="flex items-baseline gap-4 p-3 rounded-lg bg-base-300/30">
				<span class="font-display text-2xl tracking-wide w-20 text-center text-accent shrink-0">+10</span>
				<div>
					<div class="font-semibold">Rarity bonus <span class="ml-1 text-xs font-normal text-base-content/55">(up to)</span></div>
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

		<!-- TEMPORARY (v2.172.x, rarity paused): remove this callout in the
		     same release that flips scoring.mode back to "logarithmic".
		     See memory/CLAUDE.md note + config/worldcup2026.yml comment. -->
		<div
			class="mt-4 flex items-start gap-2.5 rounded-lg border border-warning/40 bg-warning/15 px-4 py-3"
			role="status"
		>
			<span class="text-base leading-none">⏸</span>
			<p class="text-sm leading-relaxed text-base-content/85">
				<b class="text-warning-text">The rarity bonus is temporarily paused</b>
				while all entries are verified and fees collected. Matches currently score base
				points only. Once the pool is confirmed, the rarity bonus switches on and is
				applied <b class="text-warning-text">retroactively to every completed game</b> —
				no points are lost.
			</p>
		</div>

		<!-- Rarity bonus worked example: novice intro → narrow table → nerd footnote. -->
		<p class="text-sm text-base-content/80 mt-4 mb-3 leading-relaxed">
			<b class="text-base-content">How the rarity bonus works.</b>
			After a match, we count how many of the {rarityPredictorCount} predictors got the outcome right. The fewer correct calls, the bigger your bonus — capped at <b class="text-accent">+10</b>. The table below shows the bands for a {rarityPredictorCount}-predictor pool; the bands scale automatically with the actual pool size when scoring runs.
		</p>
		<div class="rounded-lg border border-base-300/60 overflow-hidden">
			<div class="flex items-baseline gap-4 bg-base-300/60 px-3 py-2 text-[10px] uppercase tracking-widest text-base-content/70">
				<span class="w-48 shrink-0">Friends who got it right</span>
				<span class="font-bold w-12 text-right shrink-0">Bonus</span>
			</div>
			{#each rarityRows as band (band.countLabel)}
				<div
					class="flex items-baseline gap-4 px-3 py-2 border-t border-base-300/40 {band.bonus === RARITY_CAP
						? 'bg-accent/10'
						: ''} {band.bonus === 0 ? 'opacity-60' : ''}"
				>
					<span class="text-sm text-base-content/80 tabular-nums w-48 shrink-0">
						{band.countLabel} of {rarityPredictorCount}
					</span>
					<span
						class="font-display text-xl leading-none tabular-nums w-12 text-right shrink-0 {band.bonus === RARITY_CAP
							? 'text-error'
							: band.bonus === 0
							? 'text-base-content/40'
							: 'text-accent'}"
					>
						{band.bonus > 0 ? `+${band.bonus}` : '—'}
					</span>
				</div>
			{/each}
		</div>
		<p class="text-xs text-base-content/55 mt-3 leading-relaxed">
			<b class="text-base-content/70">For the nerds.</b>
			Derived from Shannon surprisal — the same logarithmic scoring rule used in forecasting tournaments. The bonus is
			<code class="font-mono text-[11px] bg-base-300/40 px-1.5 py-0.5 rounded text-base-content/70">R = min(10, round(α · log₂(1 / 2f)))</code>
			where <i>f</i> is the fraction of predictors who got it right (so <i>f</i> = 3 ⁄ 100 in the top band above), and α ≈ 2.56 is calibrated so a uniquely correct call out of ~30 predictors hits the +10 cap.
		</p>
	</section>

	<!-- 03 — Bracket scoring -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">03 · Scoring · Bracket Advancements <span class="text-xs text-base-content/40">· per team-stage pick · knockout only</span></h2>
		<p class="text-sm text-base-content/80 mb-4">Your bracket awards points for each team you correctly predict to reach a stage — cumulative through the knockout rounds. Picking <b>Argentina</b> as champion who beat <b>France</b> in the final, for example, awards you the Winner points <i>plus</i> the Final points for Argentina, plus their SF / QF / R16 / R32 stage points.</p>
		<div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
			{#each BRACKET_STAGES as s (s.lbl)}
				<div class="stat-card {s.winner ? 'border-accent/50' : ''}">
					<p class="stat-title">{s.lbl}</p>
					<p class="stat-value text-2xl {s.winner ? 'text-accent' : ''}">{s.pts}</p>
				</div>
			{/each}
		</div>
	</section>

	<!-- 04 — Bonus questions -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">04 · Bonus Questions <span class="text-xs text-base-content/40">· {bonusQuestions.length || 4} questions · lock with the deadline</span></h2>
		<p class="text-sm text-base-content/80 mb-4">A small set of pre-tournament wagers on side-stories beyond the bracket. Submit your picks before the deadline; the admin reveals each correct answer as it resolves (group-stage questions at the end of the group stage; knockout questions once the tournament progresses far enough). If multiple teams qualify — e.g. two teams tied on goals — anyone who picked either gets the points.</p>
		{#each ['group_stage', 'top_flop', 'awards'] as cat (cat)}
			{@const qs = bonusByCategory[cat] ?? []}
			{#if qs.length > 0}
				<h3 class="text-sm font-display uppercase tracking-wide mt-4 mb-2">{CATEGORY_LABEL[cat]}</h3>
				<div class="space-y-1.5">
					{#each qs as q (q.id)}
						<div class="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-base-300/30">
							<span class="text-sm">{q.label}</span>
							<span class="badge badge-accent">+{BONUS_POINTS[q.category] ?? 20}</span>
						</div>
					{/each}
				</div>
			{/if}
		{/each}
		{#if bonusQuestions.length === 0}
			<p class="text-xs text-base-content/50 mt-2">Loading bonus questions…</p>
		{/if}
	</section>

	<!-- 05 — Buy-in & pool -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">05 · Buy-in & Pool <span class="text-xs text-base-content/40">· cash, paid pre-tournament</span></h2>
		<p class="text-sm text-base-content/80 mb-4">Entry to the competition costs <b>{info ? fmtCurrency(info.entry_fee) : 'tbd'}</b> per entry, payable to the admin before the deadline. Anyone who hasn't paid by the deadline can still play, but isn't eligible for the prize pool. The admin tracks paid status in the admin panel.</p>
		<div class="grid grid-cols-3 gap-3">
			<div class="stat-card">
				<p class="stat-title">Entry fee</p>
				<p class="stat-value text-2xl">{info ? fmtCurrency(info.entry_fee) : '—'}</p>
				<p class="text-xs text-base-content/40 mt-1">per entry</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Players paid</p>
				<p class="stat-value text-2xl">—</p>
				<p class="text-xs text-base-content/40 mt-1">Updated after the deadline</p>
			</div>
			<div class="stat-card">
				<p class="stat-title">Prize pool</p>
				<p class="stat-value text-2xl">—</p>
				<p class="text-xs text-base-content/40 mt-1">Updated after the deadline</p>
			</div>
		</div>
		<p class="text-sm text-base-content/80 mt-4">The prize fund is typically split as follows: <b>65%</b> to the overall winner, <b>20%</b> to the group-stage winner, and the rest to a charity chosen by the organisers.</p>
	</section>

	<!-- 06 — Fine print -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">06 · The Fine Print <span class="text-xs text-base-content/40">· read once · then never again</span></h2>
		<div class="space-y-3 text-sm text-base-content/80">
			<div><b class="text-base-content">One deadline · all entries lock together.</b> Every prediction — group-stage scores, knockout bracket, and bonus questions — must be in before the deadline shown in the hero. After that, nothing can change.</div>
			<div><b class="text-base-content">Blind pool.</b> You can't see anyone else's picks until the deadline. Once everyone's locked in, the pool is open and rarity bonuses can be computed.</div>
			<div><b class="text-base-content">Score cap · 15 goals per side.</b> The wizard caps any single team's score at 15. Yes, even when picking the 7-1 you saw in 2014.</div>
			<div><b class="text-base-content">Knockout bracket gate.</b> The knockout sub-section of the wizard only opens once all 72 group-stage matches have been predicted — it needs your predicted standings to seed R32, so it can't work earlier.</div>
			<div><b class="text-base-content">Disputes.</b> If a fixture's score is corrected after the fact (e.g. a goal disallowed in post-match review), the admin can manually update the result via the admin panel and the leaderboard recomputes on the next request.</div>
			<div><b class="text-base-content">Have fun.</b> This is a friend competition, not Vegas. Trash talk is encouraged. Lording an 18-place lead over your group chat is exactly the point.</div>
		</div>
	</section>
</div>

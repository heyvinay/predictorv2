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

	/** Worked-example sample size for the rarity-bonus table. Pulled from
	 *  the live /api/competition/info (`eligible_entries` — the actual
	 *  scoring denominator, NOT `total_players` which counts users). One
	 *  user can hold multiple entries, so the rarity bonus divides by the
	 *  entry count, not the user count. Falls back to 100 before the API
	 *  responds so the table renders with sensible numbers on first paint. */
	const RARITY_PRED_FALLBACK = 100;
	$: rarityPredictorCount = info?.eligible_entries ?? RARITY_PRED_FALLBACK;

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
						scoring rule used in forecasting tournaments); the table below
						shows exactly how the bands fall against our confirmed
						{rarityPredictorCount}-entry pool.
					</div>
				</div>
			</div>
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
			where <i>f</i> is the fraction of predictors who got it right (e.g. <i>f</i> = 1 ⁄ {rarityPredictorCount} for a uniquely-correct call against the confirmed {rarityPredictorCount}-entry pool), and α ≈ 2.56 is the calibration that produces the bands above — the <b class="text-base-content/70">+10 cap</b> is reached for any correct call within the top band ({rarityRows[0]?.countLabel ?? '1'} of {rarityPredictorCount} entries).
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
		<p class="text-sm text-base-content/80 mt-4">Together we collected <b>over €900</b>, with the prize fund split as follows:</p>
		<ul class="mt-3 space-y-2 text-sm">
			<li class="flex items-center justify-between gap-3 rounded-lg bg-base-300/30 px-3 py-2">
				<span class="text-base-content/85">🥇 Overall Winner <span class="text-xs text-base-content/55">(after the Finals)</span></span>
				<b class="font-display text-base text-primary">€595</b>
			</li>
			<li class="flex items-center justify-between gap-3 rounded-lg bg-base-300/30 px-3 py-2">
				<span class="text-base-content/85">🏅 Group Stage Winner</span>
				<b class="font-display text-base text-primary">€183</b>
			</li>
			<li class="flex items-center justify-between gap-3 rounded-lg bg-base-300/30 px-3 py-2">
				<span class="text-base-content/85">❤️ Soup Kitchen Donation</span>
				<b class="font-display text-base text-primary">€137</b>
			</li>
		</ul>
		<div class="mt-3 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5 text-sm text-base-content/85 leading-relaxed">
			A huge thank you to <b>Atlas Insurance</b>, who have generously topped up the Soup Kitchen donation, bringing the <b>total charitable contribution to €650</b>.
		</div>
		<p class="text-sm text-base-content/80 mt-4"><b>Ties are shared.</b> If two or more entries are tied for the lead at the end of the group stage, the group-stage cash is split equally between them; the same applies at the end of the tournament for the overall cash prize.</p>
		<p class="text-sm text-base-content/80 mt-3"><b>Side prize — official Adidas Trionda match ball.</b> Awarded at the end of the tournament to the <b>runner-up</b> on total points. <b>Any entry that won or shared the group-stage cash is not eligible</b> — if such an entry is also the runner-up, the ball moves to the next eligible entry below. If multiple eligible entries are tied at that rank, the ball goes to the one with more <b>group-stage points</b>; if still tied, the winner is drawn by lots.</p>
	</section>

	<!-- 06 — Provisional standings & finalization -->
	<section id="finalization" class="stadium-card no-glow p-5 scroll-mt-20">
		<h2 class="text-lg font-display tracking-wide mb-3">
			06 · Provisional Standings
			<span class="text-xs text-base-content/40">· how the leaderboard becomes official</span>
		</h2>
		<div class="space-y-3 text-sm text-base-content/80">
			<p>
				The leaderboard you see during the tournament is <b class="text-warning-text">provisional</b>.
				Points are scored automatically as match results land — fast, but not infallible.
				Three classes of error can show up briefly:
			</p>
			<ul class="ml-4 list-disc space-y-1.5 text-[13px] marker:text-base-content/40">
				<li><b>Algorithm bugs we haven't caught.</b> This is software.</li>
				<li>
					<b>Wrong scores from the upstream feed.</b> Live data providers occasionally
					flap a match's status or score; the admin tools can correct any individual
					fixture and the standings recompute on the next refresh.
				</li>
				<li>
					<b>Unforeseen edge cases.</b> Disputed goals, abandoned matches, late
					replacements — anything the rules above haven't explicitly covered.
				</li>
			</ul>
			<p>
				<b class="text-base-content">Final standings — and any payouts — are confirmed by
					manual review after all games conclude</b>, before anything is paid out. If you
				spot something that looks wrong before then, reply to any of the tournament emails
				or use the Help &amp; Support button — corrections cost us nothing once we know.
			</p>
			<p class="text-xs text-base-content/55">
				The "Provisional" pill on the leaderboard always links back here.
			</p>
		</div>
	</section>

	<!-- 07 — Fine print -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">07 · The Fine Print <span class="text-xs text-base-content/40">· read once · then never again</span></h2>
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

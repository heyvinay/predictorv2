<script lang="ts">
	/**
	 * Insights view (spec §6) — "for the data nerds".
	 *
	 * 9 of the spec's 14 cards compute from data already on the client
	 * (leaderboard rows + fixtures + scoring rules). The other 5 (herd &
	 * mavericks, heartbreak, biggest hauls, hot hand, pick twins) need
	 * every entry's per-fixture picks server-side — gated behind
	 * INSIGHTS_EXTENDED until a backend insights endpoint exists
	 * (pre-authorized by ACCEPTANCE M4: ship behind a flag, don't block).
	 */
	import { onDestroy, onMount } from 'svelte';
	import type { Fixture } from '$types';
	import type { BonusMeta } from '$api/bonus';
	import { getBonusHitRates, getChampionMarketOdds } from '$lib/api/leaderboard';
	import type { BonusHitRate, LbEntryV4 } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import { startLivePoll } from '$lib/utils/livePoll';
	import {
		ceilingOf,
		deriveStage,
		dnaOf,
		multiEntryUserIds,
		remainingMatchPoints,
		rowDisplayName
	} from '$lib/utils/leaderboardV4';
	import { groupGoalsSuperlatives } from '$lib/utils/goalsSuperlatives';
	import { knockoutBonusCandidates } from '$lib/utils/knockoutBonusCandidates';
	import DnaBar from './DnaBar.svelte';
	import FlagCode from './FlagCode.svelte';
	import InsightCard from './InsightCard.svelte';
	import YouTag from './YouTag.svelte';

	export let rows: LbEntryV4[];
	export let rules: ScoringRules | null;
	export let userId: string | null | undefined;
	export let fixtures: Fixture[];
	/** FIFA top_n cutoff + team list driving bonus questions 3 (Dark
	 *  Horse) and 4 (Bottlers). Null until the page load completes. */
	export let bonusMeta: BonusMeta | null = null;

	// 5 cards needing all-entries per-fixture data — not yet served.
	const INSIGHTS_EXTENDED = false;

	// Pool-wide "% who got it right" per bonus question (Bonus Points card).
	// The only piece of that card not derivable from `rows`, so it's
	// self-fetched here. Best-effort: a failure hides just the stat, never
	// the card. Keyed by question_id; unresolved questions are absent.
	let hitRateByQid: Record<string, BonusHitRate> = {};

	// Live Polymarket championship odds for the "Who picked whom" card,
	// keyed by internal team name (joined server-side). Gated behind
	// win_probability_enabled — a 403 leaves this empty and the market
	// column simply doesn't render, while the pool-pick bars (from `rows`,
	// no gate) always do. Live-polled since market prices move mid-match.
	let marketOddsByTeam: Record<string, number> = {};
	let stopOddsPoll: (() => void) | undefined;

	async function refreshMarketOdds() {
		try {
			const res = await getChampionMarketOdds();
			marketOddsByTeam = Object.fromEntries(res.odds.map((o) => [o.team, o.market_odds]));
		} catch {
			marketOddsByTeam = {};
		}
	}

	onMount(async () => {
		try {
			const res = await getBonusHitRates();
			hitRateByQid = Object.fromEntries(res.questions.map((q) => [q.question_id, q]));
		} catch {
			hitRateByQid = {};
		}
		// Initial fetch (startLivePoll intentionally doesn't tick on start),
		// then poll every 60s — matches the leaderboard's own poll against
		// the same backend cache TTL; visibility-aware (pauses when hidden).
		await refreshMarketOdds();
		stopOddsPoll = startLivePoll(refreshMarketOdds, 60_000);
	});

	onDestroy(() => stopOddsPoll?.());

	$: isOwn = (r: LbEntryV4) => r.user_id === userId;
	// Same display-name rule as the standings table — consistency matters.
	$: multiOwners = multiEntryUserIds(rows);
	$: leaderTotal = rows.length ? Math.max(...rows.map((r) => r.total_points)) : 1;
	// Market-odds column shows only when the gated endpoint returned data
	// (flag on / admin) — otherwise the champion card is pool-picks only.
	$: hasMarketOdds = Object.keys(marketOddsByTeam).length > 0;

	// ── 1 · Points DNA: top 8 + own entries ──
	$: dnaRows = (() => {
		const top = rows.slice(0, 8);
		const extras = rows.filter((r) => isOwn(r) && !top.includes(r));
		return [...top, ...extras];
	})();

	// ── 2 · Champion distribution ──
	type ChampRow = { team: string; n: number; alive: boolean; yours: boolean };
	$: champRows = (() => {
		const byTeam = new Map<string, ChampRow>();
		for (const r of rows) {
			if (!r.champion_pick) continue;
			const cur = byTeam.get(r.champion_pick) ?? {
				team: r.champion_pick,
				n: 0,
				alive: r.champion_alive ?? true,
				yours: false
			};
			cur.n += 1;
			cur.alive = r.champion_alive ?? true;
			cur.yours = cur.yours || isOwn(r);
			byTeam.set(r.champion_pick, cur);
		}
		return [...byTeam.values()].sort((a, b) => b.n - a.n);
	})();
	$: champMax = champRows.length ? champRows[0].n : 1;
	$: aliveChampCount = rows.filter((r) => r.champion_alive && r.champion_pick).length;

	// ── 3 · What-if: each still-alive champion scenario ──
	$: winnerVal = rules?.advancement?.winner ?? 100;
	type WhatIfRow = {
		team: string;
		topName: string;
		topIsOwn: boolean;
		topPts: number;
		newLeader: boolean;
		yourBest: string;
	};
	$: leaderId = rows[0]?.entry_id;
	// Lineup-based stage — the what-if card is placeholder-only until
	// the knockout bracket holds real teams.
	$: lbStage = deriveStage(fixtures);
	$: whatIfRows = champRows
		.filter((c) => c.alive)
		.slice(0, 6)
		.map((c): WhatIfRow => {
			const proj = rows
				.map((r) => ({
					r,
					p:
						r.total_points +
						(r.champion_pick === c.team && (r.breakdown?.winner_points ?? 0) === 0
							? winnerVal
							: 0)
				}))
				.sort((a, b) => b.p - a.p || a.r.position - b.r.position);
			const top = proj[0];
			const own = proj.filter((x) => isOwn(x.r)).sort((a, b) => b.p - a.p)[0];
			return {
				team: c.team,
				topName: rowDisplayName(top.r, multiOwners),
				topIsOwn: isOwn(top.r),
				topPts: top.p,
				newLeader: top.r.entry_id !== leaderId,
				yourBest: own ? `${rowDisplayName(own.r, multiOwners).slice(0, 18)} ${own.p}` : '—'
			};
		});

	// ── 4 · Points still on the table ──
	$: shared = rules ? remainingMatchPoints(fixtures, rules) : 0;
	type CeilRow = { r: LbEntryV4; ceil: number };
	$: ceilRows = (() => {
		if (!rules) return [] as CeilRow[];
		const all = rows.map((r): CeilRow => ({ r, ceil: ceilingOf(r, rules, shared) }));
		const top = [...all].sort((a, b) => b.ceil - a.ceil).slice(0, 8);
		const own = all.filter((x) => isOwn(x.r) && !top.includes(x));
		return [...top, ...own];
	})();
	$: ceilMax = ceilRows.length ? Math.max(...ceilRows.map((x) => x.ceil)) : 1;
	$: finalVal = rules?.advancement?.final ?? 75;

	// ── 5 · Tournament superlatives ──
	//
	// Each criterion typically has multiple teams tied (especially early
	// on, when "most goals" might be 5 teams at 2 goals each). We render
	// ALL ties as flag pills, capped at 5 with a "+N more" footnote so
	// the card doesn't blow up in the opening days. Pills are sorted
	// alphabetically inside each tied group for stable ordering.
	const SUPERLATIVE_LIMIT = 5;
	$: groupStageComplete = (() => {
		const gx = fixtures.filter((f) => f.stage === 'group');
		return gx.length > 0 && gx.every((f) => f.status === 'finished');
	})();
	type Superlative = {
		qid: string;
		lbl: string;
		teams: string[];
		shown: string[];
		extra: number;
		val: string;
		note: string;
	};
	$: superlatives = (() => {
		const out: Superlative[] = [];

		const push = (
			qid: string,
			lbl: string,
			teams: string[],
			val: string,
			note: string
		): void => {
			if (teams.length === 0) return;
			out.push({
				qid,
				lbl,
				teams,
				shown: teams.slice(0, SUPERLATIVE_LIMIT),
				extra: Math.max(0, teams.length - SUPERLATIVE_LIMIT),
				val,
				note
			});
		};

		const { mostScored, mostConceded } = groupGoalsSuperlatives(fixtures);
		if (mostScored.keys.length > 0) {
			push(
				'most_goals_scored_group',
				'Most goals · group phase',
				mostScored.keys,
				`${mostScored.n} scored`,
				'highest-scoring attack so far'
			);
			push(
				'most_goals_conceded_group',
				'Most conceded · group phase',
				mostConceded.keys,
				`${mostConceded.n} conceded`,
				'leakiest defence so far'
			);
		}

		// ── Bonus Q3 / Q4 (group stage must be complete to seed candidates).
		// Shared derivation with the Winner tab's Q3/Q4 bonus cards —
		// see knockoutBonusCandidates.ts for the mechanics.
		const kb = knockoutBonusCandidates(fixtures, bonusMeta);
		if (kb.darkHorse) {
			push(
				'dark_horse',
				`Dark horse · outside FIFA top ${kb.darkHorse.topN}`,
				kb.darkHorse.candidates,
				kb.darkHorse.valLabel,
				kb.darkHorse.note
			);
		}
		if (kb.bottlers) {
			push(
				'flop',
				`Bottlers · inside FIFA top ${kb.bottlers.topN}`,
				kb.bottlers.candidates,
				kb.bottlers.valLabel,
				kb.bottlers.note
			);
		}
		return out;
	})();

	// ── 7 · Contrarian index ──
	$: contrarians = rows
		.map((r) => ({
			r,
			share: r.total_points > 0 ? (r.breakdown?.hybrid_bonus_points ?? 0) / r.total_points : 0
		}))
		.sort((a, b) => b.share - a.share)
		.slice(0, 5);

	// ── 8 · Exact-score snipers ──
	$: snipers = [...rows].sort((a, b) => b.exact_scores - a.exact_scores).slice(0, 5);

	// ── 9 · Movers (daily snapshots) ──
	$: climbing = rows
		.filter((r) => (r.daily_movement ?? 0) > 0)
		.sort((a, b) => (b.daily_movement ?? 0) - (a.daily_movement ?? 0))
		.slice(0, 3);
	$: sliding = rows
		.filter((r) => (r.daily_movement ?? 0) < 0)
		.sort((a, b) => (a.daily_movement ?? 0) - (b.daily_movement ?? 0))
		.slice(0, 3);

	const MINI_ROW =
		'grid items-center gap-2.5 rounded-lg px-1.5 py-1 grid-cols-[22px_1fr_auto_44px]';
	const YOURS_ROW = 'bg-primary/[0.07] shadow-[inset_2px_0_0_theme(colors.primary)]';
</script>

<div class="grid grid-cols-1 gap-4 min-[860px]:grid-cols-2">
	<!-- 1 · Points DNA (wide) -->
	<InsightCard
		title="Points DNA"
		sub="Where each entry's points come from — top 8 plus your entries"
		wide
	>
		<div class="mb-3 flex flex-wrap gap-3.5">
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-success"></span>Exact</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-amber-400"></span>Result</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-[repeating-linear-gradient(135deg,#D4AF37_0_2px,#7C5E1D_2px_4px)]"></span>Rarity</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span
					class="h-2.5 w-8 rounded bg-[linear-gradient(90deg,#93C5FD,#60A5FA,#3B82F6,#2563EB,#1D4ED8,#1E3A8A)]"
				></span>Bracket: R32 → Winner</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-[#8B5CF6]"></span>Bonus</span
			>
		</div>
		<div class="flex flex-col gap-2">
			{#each dnaRows as r (r.entry_id)}
				<div
					class="grid grid-cols-[34px_220px_1fr_40px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(r)
						? YOURS_ROW
						: ''}"
				>
					<span class="font-display text-[11px] font-extrabold text-base-content/55"
						>#{r.position}</span
					>
					<span class="flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold">
						<span class="max-w-[220px] truncate">{rowDisplayName(r, multiOwners)}</span>
						{#if isOwn(r)}<YouTag />{/if}
					</span>
					<span class="block" style="width:{(r.total_points / leaderTotal) * 100}%">
						<DnaBar split={dnaOf(r.breakdown)} />
					</span>
					<b class="text-right font-display text-[13px] font-extrabold">{r.total_points}</b>
				</div>
			{/each}
		</div>
	</InsightCard>

	<!-- 2 · Champion picks -->
	<InsightCard
		title="Who picked whom for champion"
		sub={hasMarketOdds
			? `${rows.length} entries · gold bars are the pool's picks, blue is the live Polymarket title market`
			: `${rows.length} entries · greyed teams are already out`}
	>
		<div class="flex flex-col gap-2">
			{#each champRows as c (c.team)}
				<div
					class="grid items-center gap-2.5 {hasMarketOdds
						? 'grid-cols-[minmax(96px,auto)_1fr_30px_auto]'
						: 'grid-cols-[minmax(110px,auto)_1fr_30px]'}"
				>
					<span class="flex items-center gap-1.5 text-xs font-semibold {c.alive ? '' : 'text-base-content/55'}">
						<FlagCode team={c.team} alive={c.alive} size="sm" />
						{#if !c.alive}<span class="text-[8.5px] font-extrabold tracking-[0.12em] text-error"
								>OUT</span
							>{/if}
						{#if c.yours}<YouTag />{/if}
					</span>
					<span class="h-2 overflow-hidden rounded-full bg-base-300/40">
						<span
							class="block h-full rounded-full {c.alive ? 'bg-primary' : 'bg-base-content/25'}"
							style="width:{(c.n / champMax) * 100}%"
						></span>
					</span>
					<b class="text-right font-display text-[13px] font-extrabold">{c.n}</b>
					{#if hasMarketOdds}
						<span class="justify-self-end whitespace-nowrap font-mono text-[10.5px] font-semibold text-[#3B82F6]">
							{#if marketOddsByTeam[c.team] != null}
								{Math.round(marketOddsByTeam[c.team] * 100)}%<span
									class="ml-0.5 text-[7.5px] font-bold uppercase tracking-wide text-base-content/40">mkt</span
								>
							{:else}
								<span class="text-base-content/25">—</span>
							{/if}
						</span>
					{/if}
				</div>
			{:else}
				<p class="text-xs text-base-content/40">No champion picks recorded.</p>
			{/each}
		</div>
		<svelte:fragment slot="foot">
			{aliveChampCount} of {rows.length} entries still have a live champion pick.{#if hasMarketOdds}
				Market odds via Polymarket, refreshed live.{/if}
		</svelte:fragment>
	</InsightCard>

	<!-- 3 · What-if. Group stage: every projection reads "champion pick
	     + winner bonus = new leader", which is noise — the card stays as
	     a placeholder until the bracket is real (lineup-based stage
	     derivation, same rule as the Final column). -->
	<InsightCard
		title="If they lift the trophy…"
		sub="Who tops the pool under each remaining champion · +{winnerVal} for the right pick"
	>
		{#if lbStage !== 'knockout'}
			<div class="flex flex-col items-start gap-1.5 py-2">
				<span
					class="rounded-badge bg-base-300/50 px-2 py-0.5 text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/60"
					>Unlocks in the knockouts</span
				>
				<p class="text-xs leading-relaxed text-base-content/55">
					Once the bracket is set, this card shows who'd top the pool under each
					remaining champion. During the groups every scenario just adds the winner
					bonus — not much of a story yet.
				</p>
			</div>
		{:else}
		<div class="flex flex-col gap-2">
			{#each whatIfRows as w (w.team)}
				<div
					class="grid grid-cols-[80px_1fr] items-center gap-2.5 rounded-lg px-1.5 py-1 {w.topIsOwn
						? YOURS_ROW
						: ''}"
				>
					<FlagCode team={w.team} size="sm" />
					<span class="flex flex-wrap items-center gap-1.5 text-xs text-base-content/70">
						<b class="text-base-content">{w.topName}</b>
						{#if w.topIsOwn}<YouTag />{/if}
						takes it ·
						<span class="font-display font-extrabold text-base-content">{w.topPts} pts</span>
						{#if w.newLeader}
							<span
								class="rounded-full bg-primary/20 px-1.5 py-0.5 text-[8.5px] font-extrabold uppercase tracking-[0.1em] text-primary"
								>new leader</span
							>
						{/if}
					</span>
				</div>
			{:else}
				<p class="text-xs text-base-content/40">No live champion scenarios.</p>
			{/each}
		</div>
		{/if}
		<svelte:fragment slot="foot">
			{#if lbStage !== 'knockout'}
				Live from the Round of 32 — when champion scenarios start to mean something.
			{:else}
				Simplified projection — champion bonus only; finalist and remaining match points not
				included.
			{/if}
		</svelte:fragment>
	</InsightCard>

	<!-- 4 · Points still on the table (wide) -->
	<InsightCard
		title="Points still on the table"
		sub="Current score plus the maximum each entry can still win — the title race isn't over"
		wide
	>
		<div class="flex flex-col gap-2">
			{#each ceilRows as cr (cr.r.entry_id)}
				<div
					class="grid grid-cols-[34px_220px_1fr_90px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(
						cr.r
					)
						? YOURS_ROW
						: ''}"
				>
					<span class="font-display text-[11px] font-extrabold text-base-content/55"
						>#{cr.r.position}</span
					>
					<span class="flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold">
						<span class="max-w-[220px] truncate">{rowDisplayName(cr.r, multiOwners)}</span>
						{#if isOwn(cr.r)}<YouTag />{/if}
					</span>
					<span class="flex h-2.5 overflow-hidden rounded-full bg-base-300/40">
						<span
							class="h-full {isOwn(cr.r) ? 'bg-primary' : 'bg-base-content/40'}"
							style="width:{(cr.r.total_points / ceilMax) * 100}%"
						></span>
						<span
							class="h-full bg-[repeating-linear-gradient(135deg,theme(colors.primary/35%)_0_4px,transparent_4px_8px)]"
							style="width:{((cr.ceil - cr.r.total_points) / ceilMax) * 100}%"
						></span>
					</span>
					<b class="text-right font-display text-[12.5px] font-extrabold">
						{cr.r.total_points}
						<span class="text-[11px] font-bold text-base-content/55">→ {cr.ceil}</span>
					</b>
				</div>
			{/each}
		</div>
		<svelte:fragment slot="foot">
			Solid = banked · striped = still winnable (+{winnerVal} champion · +{finalVal} per live
			finalist · +{shared} remaining fixtures, equal for all).
		</svelte:fragment>
	</InsightCard>

	<!-- 5 · Bonus Points -->
	<InsightCard
		title="Bonus Points"
		sub="The 4 bonus questions — resolved answers and how many of the pool called each one"
	>
		<div class="flex flex-col gap-3.5">
			{#each superlatives as s (s.lbl)}
				<div class="flex flex-col gap-1.5">
					<span class="flex items-baseline gap-2 flex-wrap">
						<span
							class="text-[9.5px] font-extrabold uppercase tracking-[0.1em] text-base-content/55"
							>{s.lbl}</span
						>
						<b class="font-display text-[13px] font-extrabold text-primary">{s.val}</b>
						{#if hitRateByQid[s.qid]}
							<span class="text-[11px] font-semibold text-base-content/45">
								· {Math.round(hitRateByQid[s.qid].hit_rate * 100)}% of the pool called it
							</span>
						{/if}
					</span>
					{#if s.shown.length > 0}
						<div class="flex flex-wrap items-center gap-1.5">
							{#each s.shown as team (team)}
								<span
									class="inline-flex items-center gap-1.5 rounded-full bg-base-300/30 px-2 py-1"
								>
									<FlagCode {team} size="sm" />
								</span>
							{/each}
							{#if s.extra > 0}
								<span class="text-[11px] text-base-content/55">+{s.extra} more</span>
							{/if}
						</div>
					{/if}
					<span class="text-[11px] text-base-content/55">{s.note}</span>
				</div>
			{:else}
				<p class="text-xs text-base-content/40">
					Bonus-question results appear once the first matches finish.
				</p>
			{/each}
			{#if !groupStageComplete}
				<p
					class="mt-1 border-t border-base-300/45 pt-3 text-[11px] text-base-content/55"
				>
					Bonus questions <b class="font-display font-extrabold">3</b> &amp;
					<b class="font-display font-extrabold">4</b> unlock once the group
					stage finishes.
				</p>
			{/if}
		</div>
	</InsightCard>

	<!-- 7 · Contrarian index — hidden while the rarity bonus is paused
	     (mode "fixed"): every entry's rarity share is 0, so the ranking
	     is meaningless. Self-restores at flip-back. -->
	{#if rules?.mode === 'logarithmic'}
	<InsightCard
		title="Contrarian index"
		sub="Share of points earned from rarity bonuses — who profits when favourites fall"
	>
		<div class="flex flex-col gap-1.5">
			{#each contrarians as c, i (c.r.entry_id)}
				<div class="{MINI_ROW} {isOwn(c.r) ? YOURS_ROW : ''}">
					<span class="font-display text-[11px] font-extrabold text-base-content/55">{i + 1}</span>
					<span class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs font-semibold">
						<span class="truncate">{rowDisplayName(c.r, multiOwners)}</span>
						{#if isOwn(c.r)}<YouTag />{/if}
					</span>
					<span class="h-[7px] w-[90px] overflow-hidden rounded-full bg-base-300/40">
						<span
							class="block h-full rounded-full bg-primary"
							style="width:{Math.min(c.share * 400, 100)}%"
						></span>
					</span>
					<b class="text-right font-display text-[13px] font-extrabold text-primary"
						>{Math.round(c.share * 100)}%</b
					>
				</div>
			{/each}
		</div>
		<svelte:fragment slot="foot">
			Rarity pays when you back outcomes the pool didn't see coming.
		</svelte:fragment>
	</InsightCard>
	{/if}

	<!-- 8 · Exact-score snipers -->
	<InsightCard
		title="Exact-score snipers"
		sub="Most perfect scorelines called — base +{(rules?.match?.correct_outcome ?? 5) +
			(rules?.match?.exact_score ?? 10)} a piece"
	>
		<div class="flex flex-col gap-1.5">
			{#each snipers as s, i (s.entry_id)}
				<div class="{MINI_ROW} {isOwn(s) ? YOURS_ROW : ''}">
					<span class="font-display text-[11px] font-extrabold text-base-content/55">{i + 1}</span>
					<span class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs font-semibold">
						<span class="truncate">{rowDisplayName(s, multiOwners)}</span>
						{#if isOwn(s)}<YouTag />{/if}
					</span>
					<span class="inline-flex gap-[3px]">
						{#each Array(Math.min(s.exact_scores, 12)) as _}
							<span class="h-[7px] w-[7px] rounded-full bg-success/85"></span>
						{/each}
					</span>
					<b class="text-right font-display text-[13px] font-extrabold text-success"
						>{s.exact_scores}</b
					>
				</div>
			{/each}
		</div>
		<svelte:fragment slot="foot">
			One exact score is worth three correct results — snipers climb fast.
		</svelte:fragment>
	</InsightCard>

	<!-- 9 · Movers -->
	<InsightCard title="Movers · since yesterday" sub="Daily snapshot vs the live table">
		{#if climbing.length === 0 && sliding.length === 0}
			<p class="text-xs text-base-content/40">
				No movement yet — ranks settle after the next scoring day.
			</p>
		{:else}
			<div class="grid grid-cols-2 gap-4">
				<div>
					<div class="mb-2 text-[10px] font-extrabold uppercase tracking-[0.12em] text-success">
						▲ Climbing
					</div>
					{#each climbing as e (e.entry_id)}
						<div class="grid grid-cols-[1fr_40px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(e) ? YOURS_ROW : ''}">
							<span class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs font-semibold">
								<span class="truncate">{rowDisplayName(e, multiOwners)}</span>
								{#if isOwn(e)}<YouTag />{/if}
							</span>
							<b class="text-right font-display text-[13px] font-extrabold text-success"
								>+{e.daily_movement}</b
							>
						</div>
					{/each}
				</div>
				<div>
					<div class="mb-2 text-[10px] font-extrabold uppercase tracking-[0.12em] text-error">
						▼ Sliding
					</div>
					{#each sliding as e (e.entry_id)}
						<div class="grid grid-cols-[1fr_40px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(e) ? YOURS_ROW : ''}">
							<span class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs font-semibold">
								<span class="truncate">{rowDisplayName(e, multiOwners)}</span>
								{#if isOwn(e)}<YouTag />{/if}
							</span>
							<b class="text-right font-display text-[13px] font-extrabold text-error"
								>{e.daily_movement}</b
							>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</InsightCard>

	{#if INSIGHTS_EXTENDED}
		<!-- Herd & mavericks · Heartbreak · Biggest hauls · Hot hand · Pick
		     twins — need per-entry per-fixture data for the whole pool;
		     unlocked once a backend insights endpoint serves it. -->
	{/if}
</div>

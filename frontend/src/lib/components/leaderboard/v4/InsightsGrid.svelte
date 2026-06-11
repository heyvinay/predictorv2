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
	import type { Fixture } from '$types';
	import type { BonusMeta } from '$api/bonus';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import {
		ceilingOf,
		deriveStage,
		dnaOf,
		isRealTeam,
		multiEntryUserIds,
		remainingMatchPoints,
		rowDisplayName,
		seededByStage
	} from '$lib/utils/leaderboardV4';
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

	$: isOwn = (r: LbEntryV4) => r.user_id === userId;
	// Same display-name rule as the standings table — consistency matters.
	$: multiOwners = multiEntryUserIds(rows);
	$: leaderTotal = rows.length ? Math.max(...rows.map((r) => r.total_points)) : 1;

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
		lbl: string;
		teams: string[];
		shown: string[];
		extra: number;
		val: string;
		note: string;
	};
	function topTiedBy<K>(map: Map<K, number>): { keys: K[]; n: number } {
		if (map.size === 0) return { keys: [], n: 0 };
		const n = Math.max(...map.values());
		const keys = [...map.entries()]
			.filter(([, v]) => v === n)
			.map(([k]) => k)
			.sort((a, b) => String(a).localeCompare(String(b)));
		return { keys, n };
	}

	$: superlatives = (() => {
		const out: Superlative[] = [];
		const gf = new Map<string, number>();
		const ga = new Map<string, number>();
		for (const f of fixtures) {
			if (f.stage !== 'group' || f.status !== 'finished' || !f.score) continue;
			gf.set(f.home_team, (gf.get(f.home_team) ?? 0) + f.score.home_score);
			gf.set(f.away_team, (gf.get(f.away_team) ?? 0) + f.score.away_score);
			ga.set(f.home_team, (ga.get(f.home_team) ?? 0) + f.score.away_score);
			ga.set(f.away_team, (ga.get(f.away_team) ?? 0) + f.score.home_score);
		}

		const push = (
			lbl: string,
			teams: string[],
			val: string,
			note: string
		): void => {
			if (teams.length === 0) return;
			out.push({
				lbl,
				teams,
				shown: teams.slice(0, SUPERLATIVE_LIMIT),
				extra: Math.max(0, teams.length - SUPERLATIVE_LIMIT),
				val,
				note
			});
		};

		if (gf.size > 0) {
			const scored = topTiedBy(gf);
			push(
				'Most goals · group phase',
				scored.keys,
				`${scored.n} scored`,
				'highest-scoring attack so far'
			);
			const conceded = topTiedBy(ga);
			push(
				'Most conceded · group phase',
				conceded.keys,
				`${conceded.n} conceded`,
				'leakiest defence so far'
			);
		}

		// ── Bonus Q3 / Q4 (group stage must be complete to seed candidates).
		//
		// These map directly to the bonus questions every entry answered:
		//   Q3 Dark Horse — team OUTSIDE FIFA top N progressing furthest.
		//   Q4 Bottlers   — team INSIDE FIFA top N eliminated earliest
		//                   (including not making the knockout stage).
		// Both become meaningful once the group stage finishes: Q4's
		// candidates seed from top-N sides that didn't qualify (or all
		// top-N sides if every favourite qualified — they're tied earliest
		// until a KO match knocks one out). Q3's candidates seed from
		// outside-top-N sides that did qualify (all tied for "furthest"
		// at R32 until KO matches narrow the field).
		const groupFixtures = fixtures.filter((f) => f.stage === 'group');
		const groupStageComplete =
			groupFixtures.length > 0 &&
			groupFixtures.every((f) => f.status === 'finished');

		if (groupStageComplete && bonusMeta) {
			const topN = new Set(bonusMeta.fifa_top_teams);
			// Teams seeded into ANY knockout fixture = qualified from groups.
			const seeded = seededByStage(fixtures);
			const qualified = new Set<string>();
			for (const set of seeded.values()) for (const t of set) qualified.add(t);

			const allGroupTeams = new Set<string>();
			for (const f of groupFixtures) {
				if (isRealTeam(f.home_team)) allGroupTeams.add(f.home_team);
				if (isRealTeam(f.away_team)) allGroupTeams.add(f.away_team);
			}

			// Q3: outside-top-N teams that progressed. Once the tournament
			// runs further, this narrows to whoever's still alive deepest.
			const eliminated = new Set<string>();
			for (const f of fixtures) {
				if (
					f.stage !== 'group' &&
					f.status === 'finished' &&
					f.score &&
					isRealTeam(f.home_team) &&
					isRealTeam(f.away_team)
				) {
					if (f.score.outcome === '1') eliminated.add(f.away_team);
					else if (f.score.outcome === '2') eliminated.add(f.home_team);
				}
			}
			const darkHorseCandidates = [...allGroupTeams]
				.filter((t) => !topN.has(t) && qualified.has(t) && !eliminated.has(t))
				.sort((a, b) => a.localeCompare(b));
			push(
				`Dark horse · outside FIFA top ${bonusMeta.top_n}`,
				darkHorseCandidates,
				darkHorseCandidates.length === 1 ? 'still standing' : 'still in contention',
				'Bonus Q3 — outsider running furthest'
			);

			// Q4: top-N teams eliminated earliest. After group stage that's
			// "didn't qualify"; once KO is running, also top-N KO losers
			// from the earliest round to have any (the question rewards
			// the EARLIEST exit, so eliminating from the latest survivors
			// downward is wrong — pick the lowest stage in which any top-N
			// side has been knocked out).
			const STAGE_ORDER = [
				'group',
				'round_of_32',
				'round_of_16',
				'quarter_final',
				'semi_final',
				'final'
			];
			const topNNotQualified = [...topN].filter(
				(t) => allGroupTeams.has(t) && !qualified.has(t)
			);
			let bottlerCandidates: string[];
			let bottlerNote: string;
			if (topNNotQualified.length > 0) {
				bottlerCandidates = topNNotQualified.sort((a, b) => a.localeCompare(b));
				bottlerNote = 'Bonus Q4 — top FIFA side failed to qualify';
			} else {
				// Every top-N side qualified — find the earliest KO round
				// any top-N team lost in, list everyone tied at that depth.
				let earliest: string | null = null;
				const koLosers = new Map<string, string>(); // team → stage of loss
				for (const f of fixtures) {
					if (
						f.stage === 'group' ||
						f.status !== 'finished' ||
						!f.score ||
						!isRealTeam(f.home_team) ||
						!isRealTeam(f.away_team)
					)
						continue;
					const loser =
						f.score.outcome === '1'
							? f.away_team
							: f.score.outcome === '2'
							? f.home_team
							: null;
					if (loser && topN.has(loser)) {
						koLosers.set(loser, f.stage);
						if (
							earliest === null ||
							STAGE_ORDER.indexOf(f.stage) < STAGE_ORDER.indexOf(earliest)
						) {
							earliest = f.stage;
						}
					}
				}
				bottlerCandidates =
					earliest === null
						? []
						: [...koLosers.entries()]
								.filter(([, s]) => s === earliest)
								.map(([t]) => t)
								.sort((a, b) => a.localeCompare(b));
				if (earliest === null) {
					bottlerNote = 'Bonus Q4 — every top-FIFA side still alive';
				} else {
					const stageLbl = earliest.replace(/_/g, ' ');
					bottlerNote =
						bottlerCandidates.length === 1
							? `Bonus Q4 — top FIFA side out at ${stageLbl}`
							: `Bonus Q4 — top FIFA sides tied · all out at ${stageLbl}`;
				}
			}
			push(
				`Bottlers · inside FIFA top ${bonusMeta.top_n}`,
				bottlerCandidates,
				bottlerCandidates.length === 0
					? 'TBD'
					: bottlerCandidates.length === 1
					? 'eliminated'
					: 'all eliminated',
				bottlerNote
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
				><span class="h-2.5 w-2.5 rounded bg-warning"></span>Result</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-primary"></span>Rarity</span
			>
			<span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-base-content/70"
				><span class="h-2.5 w-2.5 rounded bg-info"></span>Bracket & bonus</span
			>
		</div>
		<div class="flex flex-col gap-2">
			{#each dnaRows as r (r.entry_id)}
				<div
					class="grid grid-cols-[34px_minmax(110px,auto)_1fr_40px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(r)
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
		sub="{rows.length} entries · greyed teams are already out"
	>
		<div class="flex flex-col gap-2">
			{#each champRows as c (c.team)}
				<div class="grid grid-cols-[minmax(110px,auto)_1fr_30px] items-center gap-2.5">
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
				</div>
			{:else}
				<p class="text-xs text-base-content/40">No champion picks recorded.</p>
			{/each}
		</div>
		<svelte:fragment slot="foot">
			{aliveChampCount} of {rows.length} entries still have a live champion pick.
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
					class="grid grid-cols-[34px_minmax(110px,auto)_1fr_90px] items-center gap-2.5 rounded-lg px-1.5 py-1 {isOwn(
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

	<!-- 5 · Tournament superlatives -->
	<InsightCard
		title="Tournament superlatives"
		sub="The stories of the tournament — and the bonus-question candidates"
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
					Superlatives appear once the first matches finish.
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

	<!-- 7 · Contrarian index -->
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

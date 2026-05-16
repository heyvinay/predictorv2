<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fade } from 'svelte/transition';
	import { goto, beforeNavigate } from '$app/navigation';
	import { isAuthenticated, user } from '$stores/auth';
	import {
		fetchMatchPredictions,
		fetchBracketPredictions,
		fetchPhase2BracketPredictions,
		resetPredictions,
		matchPredictions,
		predictionsByFixture,
		unsavedChanges,
		hasUnsavedChanges,
		unsavedChangesCount,
		updateLocalPrediction,
		saveAllPredictions,
		matchPredictionsLoading,
		bracketPrediction,
		unsavedBracketPrediction,
		hasUnsavedBracketChanges,
		saveBracketPredictions,
		phase2BracketPrediction,
		unsavedPhase2BracketPrediction,
		hasUnsavedPhase2BracketChanges
	} from '$stores/predictions';
	import {
		loadEntries,
		refreshEntries,
		activeEntryId,
		activeEntry,
		entrySettings
	} from '$stores/entries';
	import * as entriesApi from '$api/entries';
	import {
		fetchGroupFixtures,
		groupFixtures,
		fetchActualKnockoutFixtures,
		fetchActualStandings,
		actualKnockoutFixtures,
		actualGroupStandingsMap,
		actualStandingsLoading
	} from '$stores/fixtures';
	import {
		isPhase2Active,
		isPhase2BracketLocked,
		isPhase1Locked,
		phase1Countdown,
		phase2Countdown
	} from '$stores/phase';
	import { applyFifaTiebreakers, computeGroupStandingsMapWithWarnings } from '$lib/utils/standings';
	import {
		initPersistence,
		teardownPersistence,
		hydrateFromStorage,
		lastLocalSave
	} from '$stores/unsavedPersistence';
	import { teamCode } from '$lib/utils/teamCodes';
	import type { Fixture, MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';

	import PnPageShell from '$components/panini/PnPageShell.svelte';
	import PnFlag from '$components/panini/PnFlag.svelte';
	import PnKnockoutBracket from '$components/panini/PnKnockoutBracket.svelte';
	import PnEntrySelector from '$components/panini/PnEntrySelector.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Phase + pill selection state
	let activePhase: 'phase1' | 'phase2' = 'phase1';
	let initialPhaseSet = false;
	$: if (!initialPhaseSet && $isPhase2Active !== undefined) {
		activePhase = $isPhase2Active ? 'phase2' : 'phase1';
		initialPhaseSet = true;
	}

	// Section toggle controls the outer mode (Groups / Knockout / Bonus).
	// Group pills are a sub-selection that only appears in the Groups section.
	type Section = 'groups' | 'knockout' | 'bonus';
	let activeSection: Section = 'groups';
	// Active group pill — either a group letter (e.g. 'A') or 'thirdplace'.
	let activeGroupPill: string = '';

	let saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

	// Cross-tab + cross-refresh draft persistence (silent localStorage mirror).
	// fetchesDone gates hydration so we only overlay localStorage drafts AFTER
	// the server baseline is loaded — otherwise the rehydrated drafts would
	// get clobbered by fetchMatchPredictions resetting unsavedChanges.
	let fetchesDone = false;
	let hydrated = false;
	let restorationBanner: {
		matchCount: number;
		bracketPhase1Restored: boolean;
		bracketPhase2Restored: boolean;
	} | null = null;

	// Editing state — set when the user's cursor is inside one of the two
	// score inputs of a match card. Drives the "EDITING" chip on the card
	// and the gold-with-red-shadow styling on the focused input cell.
	// We use focusin/focusout (which bubble) on the parent .pn-mcard so
	// tabbing between the home and away inputs doesn't briefly clear the
	// state — focusout's relatedTarget check confirms whether focus left
	// the card entirely.
	let editingFixtureId: string | null = null;

	function handleMatchCardFocusIn(fixtureId: string, isLocked: boolean): void {
		if (!isLocked) editingFixtureId = fixtureId;
	}

	function handleMatchCardFocusOut(e: FocusEvent): void {
		const card = e.currentTarget as HTMLElement;
		const next = e.relatedTarget as Node | null;
		// Only clear when focus moved entirely outside this card. Tabbing
		// between the home and away inputs keeps the state intact.
		if (!next || !card.contains(next)) editingFixtureId = null;
	}

	// Mobile-only dropdown state for the group picker. On desktop the
	// pill grid is shown directly; on mobile (< 800px) we collapse to
	// a single dropdown with prev/next arrows on either side.
	let groupDropdownOpen = false;

	// Reactive details about whichever group is currently active. Used by
	// the mobile dropdown trigger so it can show the right label, progress
	// counter, and done/tied/special styling without per-render @const blocks.
	$: currentGroupObj = $groupFixtures.find((g) => g.group === activeGroupPill);
	$: currentGp = currentGroupObj ? groupProgress(currentGroupObj) : null;
	$: currentIsComplete = !!(currentGp && currentGp.total > 0 && currentGp.done === currentGp.total);
	$: currentHasTie = groupStandingsWarnings.some((w) => w.group === activeGroupPill);

	function selectGroup(g: string) {
		activeGroupPill = g;
		groupDropdownOpen = false;
	}

	function prevGroup() {
		const list = $groupFixtures.map((g) => g.group);
		if (list.length === 0) return;
		if (activeGroupPill === 'thirdplace') {
			activeGroupPill = list[list.length - 1];
			return;
		}
		const idx = list.indexOf(activeGroupPill);
		// Wrap: leftmost group → 3rd Place
		activeGroupPill = idx <= 0 ? 'thirdplace' : list[idx - 1];
	}

	function nextGroup() {
		const list = $groupFixtures.map((g) => g.group);
		if (list.length === 0) return;
		if (activeGroupPill === 'thirdplace') {
			activeGroupPill = list[0];
			return;
		}
		const idx = list.indexOf(activeGroupPill);
		// Wrap: rightmost group → 3rd Place
		activeGroupPill = idx >= list.length - 1 ? 'thirdplace' : list[idx + 1];
	}

	// Svelte action: invoke `callback` when a mousedown lands outside `node`.
	// Used to close the mobile group dropdown when the user taps elsewhere.
	function clickOutside(node: HTMLElement, callback: () => void) {
		function handle(e: MouseEvent) {
			if (!node.contains(e.target as Node)) callback();
		}
		document.addEventListener('mousedown', handle);
		return {
			destroy() {
				document.removeEventListener('mousedown', handle);
			}
		};
	}

	onMount(async () => {
		if ($isAuthenticated && $user) {
			// Group fixtures + entries can load in parallel — neither depends
			// on each other. Match/bracket predictions wait for the active
			// entry id (resolved by loadEntries) and are issued by the
			// `$: if ($activeEntryId && …)` block below.
			const tasks: Promise<unknown>[] = [fetchGroupFixtures()];
			if ($user.competition_id) {
				tasks.push(loadEntries($user.id, $user.competition_id));
			}
			if ($isPhase2Active) {
				tasks.push(fetchActualKnockoutFixtures(), fetchActualStandings());
			}
			await Promise.all(tasks);
		}
		window.addEventListener('beforeunload', handleBeforeUnload);
	});

	// Re-fetch predictions whenever the active entry changes. Covers both
	// the initial transition from null → first entry (after loadEntries
	// resolves) and any subsequent user-driven switch via the selector.
	let lastActiveEntryId: string | null = null;
	$: if ($isAuthenticated && $activeEntryId && $activeEntryId !== lastActiveEntryId) {
		const prev = lastActiveEntryId;
		lastActiveEntryId = $activeEntryId;
		// Reset in-memory state so stale rows from the previous entry don't
		// flash in before the refetch lands.
		resetPredictions();
		if (prev && $user) {
			teardownPersistence($user.id, prev);
		}
		// Allow the hydration block below to fire fresh against the new entry.
		hydrated = false;
		fetchesDone = false;
		const phase2Was = $isPhase2Active;
		void (async () => {
			await Promise.all([
				fetchMatchPredictions(),
				fetchBracketPredictions(),
				...(phase2Was ? [fetchPhase2BracketPredictions()] : [])
			]);
			fetchesDone = true;
		})();
	}

	// Hydrate drafts from localStorage + start the persistence subscription
	// once user is loaded AND active entry is known AND initial fetches are
	// done AND we have group fixtures to dedupe locked matches against. Runs
	// at most once per (user, entry) pair via the `hydrated` guard, which is
	// reset by the entry-change effect above.
	$: if (
		$user &&
		$activeEntryId &&
		fetchesDone &&
		!hydrated &&
		$groupFixtures.length > 0
	) {
		hydrated = true;
		initPersistence($user.id, $activeEntryId);
		const r = hydrateFromStorage(
			$user.id,
			$activeEntryId,
			$groupFixtures,
			$isPhase1Locked,
			$isPhase2BracketLocked
		);
		if (r) {
			restorationBanner = r;
			// Auto-dismiss after 5s. The user can still click × to dismiss
			// it sooner; if they do, restorationBanner is already null when
			// this timeout fires so the assignment is a harmless no-op.
			setTimeout(() => {
				restorationBanner = null;
			}, 5000);
		}
	}

	// ---- Entry selector handlers -----------------------------------------
	async function handleEntryCreate(): Promise<void> {
		try {
			await entriesApi.createEntry();
			await refreshEntries();
		} catch (e) {
			console.error('Create entry failed', e);
		}
	}

	async function handleEntryRename(): Promise<void> {
		const current = $activeEntry;
		if (!current) return;
		const next = window.prompt('Entry name', current.display_name);
		if (!next || next.trim() === '' || next.trim() === current.display_name) return;
		try {
			await entriesApi.renameEntry(current.id, { display_name: next.trim() });
			await refreshEntries();
		} catch (e) {
			console.error('Rename failed', e);
		}
	}

	async function handleEntryDuplicate(): Promise<void> {
		const current = $activeEntry;
		if (!current) return;
		try {
			const created = await entriesApi.duplicateEntry(current.id);
			await refreshEntries();
			// Switch to the new entry so the wizard immediately reflects it.
			const { setActiveEntry } = await import('$stores/entries');
			setActiveEntry(created.id);
		} catch (e) {
			console.error('Duplicate failed', e);
		}
	}

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		}
	});

	// Default the active group pill to the first group once fixtures load
	$: if (!activeGroupPill && $groupFixtures.length > 0) {
		activeGroupPill = $groupFixtures[0].group;
	}

	// ---- Derived: standings, progress, predictions -----------------------
	$: livePredictionMap = (() => {
		const map = new Map<string, MatchPrediction>();
		for (const p of $matchPredictions) map.set(p.fixture_id, p);
		for (const [id, scores] of Object.entries($unsavedChanges)) {
			const existing = map.get(id);
			if (existing) map.set(id, { ...existing, ...scores });
			else
				map.set(id, {
					id: '',
					entry_id: $activeEntryId ?? '',
					fixture_id: id,
					home_score: scores.home_score,
					away_score: scores.away_score,
					phase: 'phase_1',
					locked_at: null,
					created_at: '',
					updated_at: '',
					is_locked: false
				});
		}
		return map;
	})();
	$: standingsResult = computeGroupStandingsMapWithWarnings($groupFixtures, livePredictionMap);
	$: standingsMap = standingsResult.standingsMap;
	$: groupStandingsWarnings = standingsResult.warnings;

	// Per-group progress: count of fixtures that have a saved or unsaved pick.
	// REACTIVE lambda (not plain function) so the call site
	// `{@const gp = groupProgress(g)}` re-evaluates when livePredictionMap
	// updates. See the same pattern on predictionState / scoreValue earlier
	// in this file — Svelte doesn't trace into function bodies for template
	// reactivity, so a plain function declaration here would freeze the
	// counter on first render.
	$: groupProgress = (g: { group: string; fixtures: Fixture[] }) => {
		let done = 0;
		for (const f of g.fixtures) {
			if (livePredictionMap.has(f.id)) done++;
		}
		return { done, total: g.fixtures.length };
	};

	// Phase 1 knockout bracket is gated on completing every group prediction.
	// Phase 2 uses real standings so doesn't need the gate.
	$: phase1BracketGated =
		activePhase === 'phase1' &&
		!(
			phaseProgress.total > 0 &&
			phaseProgress.done === phaseProgress.total
		);

	$: phaseProgress = (() => {
		let done = 0;
		let total = 0;
		for (const g of $groupFixtures) {
			const p = groupProgress(g);
			done += p.done;
			total += p.total;
		}
		const pct = total > 0 ? Math.round((done / total) * 100) : 0;
		return { done, total, pct };
	})();

	// True only when every fixture in every group has a saved or draft pick.
	// Used to gate the third-place tie-warning banner — ties between
	// third-placed teams are only meaningful once all 12 third-place stats
	// are final, since the ranking depends on cross-group comparison.
	$: allGroupsComplete = $groupFixtures.length > 0 && $groupFixtures.every((g) => {
		const p = groupProgress(g);
		return p.total > 0 && p.done === p.total;
	});

	// ---- Selected group's fixtures ---------------------------------------
	$: selectedGroup =
		activeGroupPill && activeGroupPill !== 'thirdplace'
			? $groupFixtures.find((g) => g.group === activeGroupPill) ?? null
			: null;

	// ---- Third-place qualifying standings (top 8 of 12 advance to R32) ----
	// Uses applyFifaTiebreakers so any tie that survives points→GD→GF and
	// can't be resolved cross-group (H2H is N/A across groups) emits a
	// TieWarning. We surface the warnings in a banner so the user can
	// adjust scores if they want a specific team to advance.
	$: thirdPlaceResult = (() => {
		const thirds = [];
		for (const [group, std] of Object.entries(standingsMap)) {
			if (std[2]) thirds.push({ ...std[2], group });
		}
		return applyFifaTiebreakers(thirds, [], new Map(), 'third_place_qualifying');
	})();
	$: thirdPlaceStandings = thirdPlaceResult.sorted;
	$: thirdPlaceWarnings = thirdPlaceResult.warnings;

	// Maximum goals allowed in a single match's score input. Enforced both in
	// the handler and via clampScoreInput on every keystroke so the user
	// sees the cap immediately — typing "16" instantly becomes "15".
	const MAX_GOALS = 15;

	function clampScoreInput(el: HTMLInputElement): void {
		const n = parseInt(el.value || '0', 10);
		if (Number.isNaN(n) || n < 0) {
			el.value = '0';
		} else if (n > MAX_GOALS) {
			el.value = String(MAX_GOALS);
		}
	}

	// ---- Score input handlers --------------------------------------------
	function handleScoreInput(fixtureId: string, side: 'home' | 'away', raw: string) {
		const value = Math.max(0, Math.min(MAX_GOALS, parseInt(raw || '0', 10) || 0));
		const current =
			$unsavedChanges[fixtureId] ??
			(() => {
				const p = $predictionsByFixture.get(fixtureId);
				return p ? { home_score: p.home_score, away_score: p.away_score } : { home_score: 0, away_score: 0 };
			})();
		const next =
			side === 'home'
				? { home_score: value, away_score: current.away_score }
				: { home_score: current.home_score, away_score: value };
		updateLocalPrediction(fixtureId, next.home_score, next.away_score);
	}

	// Per-fixture state + score values, computed reactively so the UI updates
	// without a page refresh when stores change.
	//
	// Note: the previous implementation was non-reactive function calls
	// (`scoreValue(f.id, side)`, `predictionState(f)`). Svelte doesn't follow
	// store reads INSIDE a function body, so those expressions in the template
	// never re-evaluated when $unsavedChanges or $predictionsByFixture changed.
	// Result: saving did update the stores, but the per-card input value, the
	// .empty class on the cell, and the per-group progress counter all stayed
	// stale until a full page refresh. Migrating to reactive Maps fixes all
	// three symptoms at once.
	type FixtureState = 'locked' | 'saved' | 'draft' | 'empty';

	$: predictionStateMap = (() => {
		const map = new Map<string, FixtureState>();
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) {
				let s: FixtureState;
				if (f.is_locked) s = 'locked';
				else if ($unsavedChanges[f.id]) s = 'draft';
				else if ($predictionsByFixture.get(f.id)) s = 'saved';
				else s = 'empty';
				map.set(f.id, s);
			}
		}
		return map;
	})();

	$: scoreValueMap = (() => {
		const map = new Map<string, { home: string; away: string }>();
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) {
				const u = $unsavedChanges[f.id];
				if (u) {
					map.set(f.id, { home: String(u.home_score), away: String(u.away_score) });
					continue;
				}
				const p = $predictionsByFixture.get(f.id);
				if (p) {
					map.set(f.id, { home: String(p.home_score), away: String(p.away_score) });
					continue;
				}
				map.set(f.id, { home: '', away: '' });
			}
		}
		return map;
	})();

	// Reactive lambdas (not plain `function` declarations) so the call-site
	// expression `{@const state = predictionState(f)}` is reactive: when
	// predictionStateMap updates, the `$:` block here reassigns
	// predictionState to a new function reference, which Svelte's compiler
	// tracks as a dependency of the call site. Plain function declarations
	// would be referentially stable and the compiler would never re-evaluate
	// the call.
	$: predictionState = (f: Fixture): FixtureState =>
		predictionStateMap.get(f.id) ?? (f.is_locked ? 'locked' : 'empty');

	$: scoreValue = (fixtureId: string, side: 'home' | 'away'): string => {
		const entry = scoreValueMap.get(fixtureId);
		return entry ? entry[side] : '';
	};

	// ---- Bracket (Phase 1) ------------------------------------------------
	let bracketComponent: PnKnockoutBracket;
	$: displayBracket = $unsavedBracketPrediction || $bracketPrediction;

	function bracketToPredictions(b: BracketPrediction): TeamAdvancementPrediction[] {
		const out: TeamAdvancementPrediction[] = [];
		const push = (stage: string, teams: (string | undefined)[] | undefined) => {
			if (!teams) return;
			for (const t of teams) if (t) out.push({ team: t, stage, group_position: null });
		};
		push('round_of_32', b.round_of_32);
		push('round_of_16', b.round_of_16);
		push('quarter_finals', b.quarter_finals);
		push('semi_finals', b.semi_finals);
		push('final', b.final);
		if (b.winner) out.push({ team: b.winner, stage: 'winner', group_position: null });
		return out;
	}

	let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}
	async function handleSaveBracket() {
		const b = $unsavedBracketPrediction;
		if (!b) return;
		bracketSaveStatus = 'saving';
		const ok = await saveBracketPredictions(bracketToPredictions(b));
		bracketSaveStatus = ok ? 'saved' : 'error';
		if (ok) {
			unsavedBracketPrediction.set(null);
			setTimeout(() => (bracketSaveStatus = 'idle'), 2000);
		}
	}

	// ---- Phase 2 wiring ---------------------------------------------------
	let phase2BracketComponent: PnKnockoutBracket;
	let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	$: phase2DisplayBracket = $unsavedPhase2BracketPrediction || $phase2BracketPrediction;
	$: hasPhase2BracketSelections = !!(
		phase2DisplayBracket &&
		(phase2DisplayBracket.round_of_16?.some((t) => t) ||
			phase2DisplayBracket.quarter_finals?.some((t) => t) ||
			phase2DisplayBracket.semi_finals?.some((t) => t) ||
			phase2DisplayBracket.final?.some((t) => t) ||
			phase2DisplayBracket.winner)
	);
	function handlePhase2BracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedPhase2BracketPrediction.set(event.detail);
	}
	async function handleSavePhase2Bracket() {
		const b = $unsavedPhase2BracketPrediction;
		if (!b) return;
		phase2BracketSaveStatus = 'saving';
		const preds = bracketToPredictions(b).filter((p) => p.stage !== 'round_of_32');
		const ok = await saveBracketPredictions(preds);
		phase2BracketSaveStatus = ok ? 'saved' : 'error';
		if (ok) {
			unsavedPhase2BracketPrediction.set(null);
			setTimeout(() => (phase2BracketSaveStatus = 'idle'), 2000);
		}
	}
	function handleClearPhase2Bracket() {
		if (confirm('Clear all Phase 2 knockout selections?')) {
			phase2BracketComponent?.clearAllSelections();
		}
	}

	// ---- Unified save -----------------------------------------------------
	$: hasAnyUnsaved = $hasUnsavedChanges || $hasUnsavedBracketChanges || $hasUnsavedPhase2BracketChanges;
	beforeNavigate(({ cancel, type }) => {
		if (!hasAnyUnsaved) return;
		if (type === 'leave') return;
		if (!confirm("You have unsaved predictions. Leave anyway? Drafts persist locally.")) cancel();
	});
	function handleBeforeUnload(e: BeforeUnloadEvent) {
		if (!hasAnyUnsaved) return;
		e.preventDefault();
		e.returnValue = '';
	}

	async function handleSaveAll() {
		saveStatus = 'saving';
		const ok = await saveAllPredictions();
		saveStatus = ok ? 'saved' : 'error';
		if (ok) setTimeout(() => (saveStatus = 'idle'), 2000);
	}

	// ---- Bonus questions (real backend) ----------------------------------

	let bonusQuestions: import('$api/bonus').BonusQuestion[] = [];
	let bonusAnswers: Map<string, string> = new Map(); // question_id → answer
	let bonusInitial: Map<string, string> = new Map(); // for change tracking
	let bonusSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

	$: hasUnsavedBonus = (() => {
		if (bonusQuestions.length === 0) return false;
		if (bonusAnswers.size !== bonusInitial.size) return true;
		for (const [k, v] of bonusAnswers) {
			if (bonusInitial.get(k) !== v) return true;
		}
		return false;
	})();

	async function loadBonus() {
		const [qs, preds] = await Promise.all([
			(await import('$api/bonus')).getBonusQuestions(),
			(await import('$api/bonus')).getMyBonusPredictions()
		]);
		bonusQuestions = qs;
		const map = new Map<string, string>();
		for (const p of preds) map.set(p.question_id, p.answer);
		bonusAnswers = map;
		bonusInitial = new Map(map);
	}

	async function handleSaveBonus() {
		bonusSaveStatus = 'saving';
		try {
			const { saveBonusPredictions } = await import('$api/bonus');
			const preds = Array.from(bonusAnswers.entries()).map(([question_id, answer]) => ({
				question_id,
				answer
			}));
			const saved = await saveBonusPredictions(preds);
			// Reset baseline to whatever the backend returned.
			const fresh = new Map<string, string>();
			for (const p of saved) fresh.set(p.question_id, p.answer);
			bonusAnswers = fresh;
			bonusInitial = new Map(fresh);
			bonusSaveStatus = 'saved';
			setTimeout(() => (bonusSaveStatus = 'idle'), 2000);
		} catch (_e) {
			bonusSaveStatus = 'error';
		}
	}

	// Reactive lambda (same pattern as groupProgress / predictionState above):
	// the function reference must be reactive so `{@const answer = bonusAnswer(bq.id)}`
	// in the template re-evaluates when bonusAnswers is reassigned.
	$: bonusAnswer = (qid: string): string => bonusAnswers.get(qid) ?? '';

	function formatLocalTime(d: Date): string {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	function setBonusAnswer(qid: string, value: string) {
		const next = new Map(bonusAnswers);
		if (value) next.set(qid, value);
		else next.delete(qid);
		bonusAnswers = next;
	}

	// All 48 teams for the team-input dropdown, derived from group fixtures.
	$: allTeams = (() => {
		const set = new Set<string>();
		for (const g of $groupFixtures) {
			for (const f of g.fixtures) {
				if (f.home_team && f.home_team !== 'TBD') set.add(f.home_team);
				if (f.away_team && f.away_team !== 'TBD') set.add(f.away_team);
			}
		}
		return Array.from(set).sort();
	})();

	// Group questions by category for layout
	$: bonusByCategory = (() => {
		const groups: Record<string, typeof bonusQuestions> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const q of bonusQuestions) {
			(groups[q.category] ?? (groups[q.category] = [])).push(q);
		}
		return groups;
	})();

	const CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		top_flop: 'Top / Flop',
		awards: 'Awards'
	};

	// Load bonus questions + saved picks on mount (gated on auth via the
	// reactive $isAuthenticated check below).
	$: if ($isAuthenticated && bonusQuestions.length === 0) {
		loadBonus().catch(() => {});
	}
</script>

<svelte:head>
	<title>Predictions — Predictor</title>
</svelte:head>

{#if $isAuthenticated}
	<PnPageShell>
		{#if restorationBanner}
			<div class="pn-restore-banner" transition:fade={{ duration: 400 }}>
				<div class="content">
					<span class="icon">✦</span>
					<div class="text">
						<b>Drafts restored from your last session.</b>
						{#if restorationBanner.matchCount > 0}
							{restorationBanner.matchCount} unsaved match
							{restorationBanner.matchCount === 1 ? 'pick' : 'picks'}{#if restorationBanner.bracketPhase1Restored || restorationBanner.bracketPhase2Restored},{/if}
						{/if}
						{#if restorationBanner.bracketPhase1Restored}
							Phase I bracket{#if restorationBanner.bracketPhase2Restored},{/if}
						{/if}
						{#if restorationBanner.bracketPhase2Restored}
							Phase II bracket
						{/if}
						— remember to press Save when you're done.
					</div>
				</div>
				<button class="dismiss" aria-label="Dismiss" on:click={() => (restorationBanner = null)}>×</button>
			</div>
		{/if}
		<!-- Hero / progress / phase toggle -->
		<section class="pn-wiz-hero">
			<div class="title-block">
				<div class="l">
					{activePhase === 'phase1' ? 'Phase I · Group Stage' : 'Phase II · Knockout'}
				</div>
				<div class="ttl"><em>Predict</em></div>
			</div>
			<div class="progress-stack">
				<div class="big-num" aria-hidden="true">
					<b>{phaseProgress.done}</b><span class="slash">/{phaseProgress.total}</span>
				</div>
				<div class="bar-and-labels">
					<div class="l">
						<span>Matches predicted</span>
						<span>{phaseProgress.pct}%</span>
					</div>
					<div class="bar"><div class="bar-fill" style="width: {phaseProgress.pct}%;"></div></div>
					<div class="l">
						<span>
							{#if activePhase === 'phase1'}
								{#if $isPhase1Locked}Locked{:else}Locks in {$phase1Countdown ?? '—'}{/if}
							{:else}
								{#if $isPhase2BracketLocked}Locked{:else}Locks in {$phase2Countdown ?? '—'}{/if}
							{/if}
						</span>
						<span>{$unsavedChangesCount} unsaved</span>
					</div>
				</div>
			</div>
			<div class="toggle-stack">
				<div class="entry-row">
					<PnEntrySelector
						on:create={handleEntryCreate}
						on:duplicate={handleEntryDuplicate}
						on:rename={handleEntryRename}
					/>
				</div>
				{#if $isPhase2Active}
					<div class="phase-toggle">
						<button class:on={activePhase === 'phase1'} on:click={() => (activePhase = 'phase1')}>Phase I</button>
						<button class:on={activePhase === 'phase2'} on:click={() => (activePhase = 'phase2')}>Phase II</button>
					</div>
				{/if}
				<div class="phase-toggle">
					<button class:on={activeSection === 'groups'} on:click={() => (activeSection = 'groups')}>Groups</button>
					<button
						class:on={activeSection === 'knockout'}
						class:gated={phase1BracketGated}
						on:click={() => (activeSection = 'knockout')}
						title={phase1BracketGated ? 'Complete all group predictions to unlock' : ''}
					>Knockout</button>
					<button class:on={activeSection === 'bonus'} on:click={() => (activeSection = 'bonus')}>Bonus</button>
				</div>
			</div>
		</section>

		<!-- Phase 1 wizard -->
		{#if activePhase === 'phase1'}
			<!-- Group pills (only when the Groups section is selected) -->
			{#if activeSection === 'groups'}
				<section class="pn-wiz-nav">
					<!-- Desktop layout: 12 groups in a divisor-of-12 grid +
					     3rd Place spanning the full height on the right.
					     Hidden on mobile via CSS media query. -->
					<div class="pn-wiz-nav-desktop">
						<div class="groups-grid">
							{#each $groupFixtures as g (g.group)}
								{@const gp = groupProgress(g)}
								{@const isComplete = gp.total > 0 && gp.done === gp.total}
								{@const hasTie = groupStandingsWarnings.some((w) => w.group === g.group)}
								<button
									class="pn-wiz-gp"
									class:active={activeGroupPill === g.group}
									class:done={isComplete && !hasTie}
									class:tied={isComplete && hasTie}
									on:click={() => (activeGroupPill = g.group)}
								>
									Group {g.group}
									<span class="gp-prog">{gp.done}/{gp.total}</span>
								</button>
							{/each}
						</div>
						<button
							class="pn-wiz-gp special"
							class:active={activeGroupPill === 'thirdplace'}
							on:click={() => (activeGroupPill = 'thirdplace')}
						>
							3rd<br />Place
						</button>
					</div>

					<!-- Mobile layout: prev/next arrows wrap a Panini-styled
					     dropdown picker. 3rd Place is a separate full-width
					     button below. Hidden on desktop via CSS media query. -->
					<div class="pn-wiz-nav-mobile">
						<div class="picker-row">
							<button
								class="arrow"
								on:click={prevGroup}
								aria-label="Previous group"
							>◀</button>
							<div class="dropdown" use:clickOutside={() => (groupDropdownOpen = false)}>
								<button
									class="trigger"
									class:done={currentIsComplete && !currentHasTie}
									class:tied={currentIsComplete && currentHasTie}
									class:open={groupDropdownOpen}
									class:special={activeGroupPill === 'thirdplace'}
									on:click={() => (groupDropdownOpen = !groupDropdownOpen)}
								>
									<span class="lbl">
										{activeGroupPill === 'thirdplace' ? '3rd Place' : `Group ${activeGroupPill || 'A'}`}
									</span>
									{#if currentGp}
										<span class="prog">{currentGp.done}/{currentGp.total}</span>
									{/if}
									<span class="chev">▾</span>
								</button>
								{#if groupDropdownOpen}
									<ul class="menu" transition:fade={{ duration: 120 }}>
										{#each $groupFixtures as g (g.group)}
											{@const gp = groupProgress(g)}
											{@const isComplete = gp.total > 0 && gp.done === gp.total}
											{@const hasTie = groupStandingsWarnings.some((w) => w.group === g.group)}
											<li>
												<button
													class:active={activeGroupPill === g.group}
													class:done={isComplete && !hasTie}
													class:tied={isComplete && hasTie}
													on:click={() => selectGroup(g.group)}
												>
													<span class="lbl">Group {g.group}</span>
													<span class="prog">{gp.done}/{gp.total}</span>
												</button>
											</li>
										{/each}
									</ul>
								{/if}
							</div>
							<button
								class="arrow"
								on:click={nextGroup}
								aria-label="Next group"
							>▶</button>
						</div>
						<button
							class="pn-wiz-gp special wide"
							class:active={activeGroupPill === 'thirdplace'}
							on:click={() => (activeGroupPill = 'thirdplace')}
						>
							3rd Place
						</button>
					</div>
				</section>
			{/if}

			<!-- Group view -->
			{#if activeSection === 'groups' && activeGroupPill === 'thirdplace'}
				<section class="pn-wiz-group">
					{#if allGroupsComplete && thirdPlaceWarnings.length > 0}
						<div class="pn-tie-warn">
							<h4>⚠ Tied teams · alphabetical fallback in effect</h4>
							{#each thirdPlaceWarnings as w (w.tiedTeams.join('-'))}
								<p>
									<span class="teams">{w.tiedTeams.join(', ')}</span>
									are tied on points, goal difference and goals-for. Third-place teams
									come from different groups so head-to-head isn't applicable — they're
									currently ranked alphabetically. Adjust your predicted scores if you want
									a different team to qualify.
								</p>
							{/each}
						</div>
					{/if}
					<div class="pn-stnd">
						<div class="h">
							<span>Third-place standings · top 8 advance to R32</span>
							<span class="live">LIVE</span>
						</div>
						<table class="pn-stnd-table">
							<thead>
								<tr>
									<th></th>
									<th class="c">Grp</th>
									<th>Team</th>
									<th class="c">P</th>
									<th class="c">W</th>
									<th class="c">D</th>
									<th class="c">L</th>
									<th class="c">GF</th>
									<th class="c">GA</th>
									<th class="c">GD</th>
									<th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each thirdPlaceStandings as t, i (t.team)}
									<tr class:qualifies={i < 8}>
										<td>
											<span class="pos" class:adv={i < 8} class:out={i >= 8}>{i + 1}</span>
										</td>
										<td class="grp">{t.group}</td>
										<td>
											<span class="team">
												<PnFlag code={teamCode(t.team)} w={20} h={14} />
												<span class="nm-text">{t.team}</span>
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat">{t.goalsFor}</td>
										<td class="stat">{t.goalsAgainst}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{:else}
									<tr><td colspan="11" style="padding: 24px; text-align: center; font-family: var(--mono); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">No third-place standings yet — fill in some group predictions</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; margin-top: 10px;">
						★ Top 8 third-placed teams (gold rows) qualify for the Round of 32 under FIFA 2026 format
					</p>
				</section>
			{:else if activeSection === 'groups' && selectedGroup}
				{@const group = selectedGroup}
				{@const standings = standingsMap[group.group] ?? []}
				{@const groupWarnings = groupStandingsWarnings.filter((w) => w.group === group.group)}
				{@const groupGp = groupProgress(group)}
				{@const groupComplete = groupGp.total > 0 && groupGp.done === groupGp.total}
				<section class="pn-wiz-group">
					{#if groupComplete && groupWarnings.length > 0}
						<div class="pn-tie-warn">
							<h4>⚠ Tied teams in Group {group.group} · alphabetical fallback in effect</h4>
							{#each groupWarnings as w (w.tiedTeams.join('-'))}
								<p>
									<span class="teams">{w.tiedTeams.join(', ')}</span>
									are tied on points, goal difference, goals-for, and head-to-head — they're
									currently ranked alphabetically. Adjust your predicted scores if you want
									a different ordering.
								</p>
							{/each}
						</div>
					{/if}
					<div class="pn-stnd-col">
					<div class="pn-stnd">
						<div class="h">
							<span>Group {group.group} · Predicted Standings</span>
							<span class="live">LIVE</span>
						</div>
						<table class="pn-stnd-table">
							<thead>
								<tr>
									<th></th>
									<th>Team</th>
									<th class="c">P</th>
									<th class="c">W</th>
									<th class="c">D</th>
									<th class="c">L</th>
									<th class="c">GF</th>
									<th class="c">GA</th>
									<th class="c">GD</th>
									<th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each standings as t, i (t.team)}
									<tr>
										<td>
											<span class="pos" class:adv={i < 2} class:maybe={i === 2} class:out={i >= 3}>{i + 1}</span>
										</td>
										<td>
											<span class="team">
												<PnFlag code={teamCode(t.team)} w={20} h={14} />
												<span class="nm-text">{t.team}</span>
											</span>
										</td>
										<td class="stat">{t.played}</td>
										<td class="stat">{t.won}</td>
										<td class="stat">{t.drawn}</td>
										<td class="stat">{t.lost}</td>
										<td class="stat">{t.goalsFor}</td>
										<td class="stat">{t.goalsAgainst}</td>
										<td class="stat gd" class:pos={t.goalDifference >= 0} class:neg={t.goalDifference < 0}>
											{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
										</td>
										<td>{t.points}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="pn-stnd-legend">
						<span><span class="pip green"></span>Advances (top 2)</span>
						<span><span class="pip gold"></span>Best 3rd match</span>
						<span><span class="pip grey"></span>Out</span>
					</div>
					</div><!-- /pn-stnd-col -->

					<!-- Matches -->
					<div class="pn-wiz-matches">
						{#each group.fixtures as f (f.id)}
							{@const state = predictionState(f)}
							<div
								class="pn-mcard"
								class:locked={state === 'locked'}
								class:empty={state === 'empty'}
								class:editing={editingFixtureId === f.id}
								on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
								on:focusout={handleMatchCardFocusOut}
							>
								{#if editingFixtureId === f.id}
									<span class="editing-tag">Editing</span>
								{/if}
								<div class="meta">
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
								</div>
								<div class="row">
									<div class="team" title={f.home_team}>
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.home_team)}</span>
									</div>
									<div class="pn-score">
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r" title={f.away_team}>
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.away_team)}</span>
									</div>
								</div>
								<div class="save-row">
									{#if state === 'locked'}
										<span class="save-tag locked">Locked</span>
										<span>No edits</span>
									{:else if state === 'draft'}
										<span class="save-tag draft">Draft</span>
										<span>Click Save Phase I to commit</span>
									{:else if state === 'saved'}
										<span class="save-tag saved">✓ Saved</span>
										<span>Submitted</span>
									{:else}
										<span class="save-tag empty">— Empty</span>
										<span>Enter a score to predict</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</section>
			{:else if activeSection === 'knockout'}
				{#if phase1BracketGated}
					{@const pct = phaseProgress.total > 0 ? Math.round((phaseProgress.done / phaseProgress.total) * 100) : 0}
					<section class="pn-locked">
						<div class="lock-icon">
							<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
								<rect x="5" y="11" width="14" height="10" rx="1" fill="currentColor" />
								<path d="M8 11V7a4 4 0 018 0v4" fill="none" />
							</svg>
						</div>
						<h2>Knockout bracket <em>locked</em></h2>
						<p class="l">
							Predict every group-stage match before opening the bracket. The bracket uses your predicted group standings to seed the Round of 32 — it can't be filled in until those are settled.
						</p>
						<div class="lock-progress">
							<div class="v">{phaseProgress.done}<span class="of">/{phaseProgress.total}</span></div>
							<div class="label">matches predicted · {pct}%</div>
							<div class="bar"><div class="bar-fill" style="width: {pct}%;"></div></div>
						</div>
						<button class="pn-btn gold" type="button" on:click={() => (activeSection = 'groups')}>← Back to Groups</button>
					</section>
				{:else}
					<PnKnockoutBracket
						bind:this={bracketComponent}
						prediction={displayBracket}
						groupStandings={standingsMap}
						locked={$isPhase1Locked}
						phase="phase_1"
						on:update={handleBracketUpdate}
					/>
					<div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px; margin-bottom: 22px;">
						{#if $hasUnsavedBracketChanges}
							<button class="pn-btn gold" on:click={handleSaveBracket} disabled={bracketSaveStatus === 'saving'}>
								{bracketSaveStatus === 'saving' ? 'Saving…' : bracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
							</button>
						{/if}
					</div>
				{/if}
			{:else if activeSection === 'bonus'}
				{#each Object.entries(bonusByCategory) as [cat, qs] (cat)}
					{#if qs.length > 0}
						<div class="pn-banner" style="margin-top: 18px;">
							<span class="n">{cat === 'group_stage' ? '06' : cat === 'top_flop' ? '07' : '08'}</span>
							<h2>{CATEGORY_LABEL[cat]}</h2>
							<span class="end">{qs.length} question{qs.length === 1 ? '' : 's'}</span>
						</div>
						<section class="pn-bonus-row">
							{#each qs as bq (bq.id)}
								{@const answer = bonusAnswer(bq.id)}
								<div class="pn-bonus">
									<div class="l"><span class="pip"></span>{CATEGORY_LABEL[cat]}</div>
									<div class="q">{bq.label}</div>
									{#if bq.input_type === 'team'}
										<select
											class="answer"
											class:empty={!answer}
											value={answer}
											on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}
											style="cursor: pointer;"
										>
											<option value="">— Select a team —</option>
											{#each allTeams as t (t)}
												<option value={t}>{t}</option>
											{/each}
										</select>
									{:else}
										<input
											type="text"
											class="answer"
											class:empty={!answer}
											value={answer}
											on:input={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}
											placeholder="Type a player name…"
										/>
									{/if}
									<div class="pts-pill">+{bq.points} pts</div>
								</div>
							{/each}
						</section>
					{/if}
				{/each}

				<div style="display: flex; justify-content: flex-end; gap: 10px; margin: 14px 0 22px; align-items: center;">
					<span style="font-family: var(--mono); font-size: 10px; letter-spacing: 0.10em; text-transform: uppercase; color: var(--ink-3);">
						{bonusAnswers.size} of {bonusQuestions.length} answered
					</span>
					<button
						class="pn-btn gold"
						on:click={handleSaveBonus}
						disabled={!hasUnsavedBonus || bonusSaveStatus === 'saving'}
					>
						{bonusSaveStatus === 'saving'
							? 'Saving…'
							: bonusSaveStatus === 'saved'
								? '✓ Saved'
								: bonusSaveStatus === 'error'
									? '× Error — retry'
									: 'Save bonus picks'}
					</button>
				</div>
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase;">
					★ Bonus picks lock with Phase I · admin will reveal correct answers as the tournament resolves
				</p>
			{/if}

			<!-- Sticky save bar -->
			<section class="pn-wiz-foot">
				<div class="stats">
					{#if $unsavedChangesCount === 0 && !$hasUnsavedBracketChanges}
						All changes saved
					{:else}
						{#if $unsavedChangesCount > 0}
							<b>{$unsavedChangesCount}</b> match {$unsavedChangesCount === 1 ? 'pick' : 'picks'} unsaved
						{/if}
						{#if $unsavedChangesCount > 0 && $hasUnsavedBracketChanges}
							<span class="sep">·</span>
						{/if}
						{#if $hasUnsavedBracketChanges}
							bracket has unsaved changes
						{/if}
					{/if}
				</div>
				{#if $lastLocalSave}
					<span class="saved-tag">Saved locally · {formatLocalTime($lastLocalSave)}</span>
				{/if}
				<button
					class="submit-btn"
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}
				>
					{#if saveStatus === 'saving'}Saving…
					{:else if saveStatus === 'saved'}✓ Saved
					{:else if saveStatus === 'error'}× Error — retry
					{:else}Save Phase I ({$unsavedChangesCount}){/if}
				</button>
			</section>
		{/if}

		<!-- Phase 2 — Panini bracket + knockout match score cards -->
		{#if activePhase === 'phase2'}
			{#if $actualStandingsLoading}
				<p style="font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.08em; text-transform: uppercase; padding: 16px;">Loading Phase II data…</p>
			{:else}
				<PnKnockoutBracket
					bind:this={phase2BracketComponent}
					prediction={phase2DisplayBracket}
					groupStandings={$actualGroupStandingsMap}
					locked={$isPhase2BracketLocked}
					phase="phase_2"
					hideR32
					on:update={handlePhase2BracketUpdate}
				/>
				<div style="display: flex; gap: 12px; justify-content: flex-end; margin-top: 12px; margin-bottom: 22px;">
					{#if $hasUnsavedPhase2BracketChanges}
						<button class="pn-btn gold" on:click={handleSavePhase2Bracket} disabled={phase2BracketSaveStatus === 'saving'}>
							{phase2BracketSaveStatus === 'saving' ? 'Saving…' : phase2BracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
						</button>
					{/if}
				</div>

				<!-- Knockout fixture score predictions (Phase 2 only) -->
				<section class="pn-wiz-group">
					<h2 style="font-family: var(--display); font-size: 22px; text-transform: uppercase; margin: 0 0 12px;">
						Knockout <em style="color: var(--red); font-style: normal;">scores</em>
					</h2>
					<div class="pn-wiz-matches">
						{#each $actualKnockoutFixtures as f (f.id)}
							{@const state = predictionState(f)}
							<div
								class="pn-mcard"
								class:locked={state === 'locked'}
								class:empty={state === 'empty'}
								class:editing={editingFixtureId === f.id}
								on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
								on:focusout={handleMatchCardFocusOut}
							>
								{#if editingFixtureId === f.id}
									<span class="editing-tag">Editing</span>
								{/if}
								<div class="meta">
									<span>{new Date(f.kickoff).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {new Date(f.kickoff).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
								</div>
								<div class="row">
									<div class="team" title={f.home_team}>
										<PnFlag code={teamCode(f.home_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.home_team)}</span>
									</div>
									<div class="pn-score">
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'home')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'home', e.currentTarget.value);
											}}
											aria-label="{f.home_team} score"
										/>
										<span class="dash">–</span>
										<input
											type="number"
											class="pn-score-cell"
											class:empty={state === 'empty'}
											min="0"
											max={MAX_GOALS}
											inputmode="numeric"
											disabled={f.is_locked}
											value={scoreValue(f.id, 'away')}
											on:input={(e) => {
												clampScoreInput(e.currentTarget);
												handleScoreInput(f.id, 'away', e.currentTarget.value);
											}}
											aria-label="{f.away_team} score"
										/>
									</div>
									<div class="team r" title={f.away_team}>
										<PnFlag code={teamCode(f.away_team)} w={28} h={20} />
										<span class="nm">{teamCode(f.away_team)}</span>
									</div>
								</div>
								<div class="save-row">
									{#if state === 'locked'}
										<span class="save-tag locked">Locked</span>
										<span>No edits</span>
									{:else if state === 'draft'}
										<span class="save-tag draft">Draft</span>
										<span>Save below to commit</span>
									{:else if state === 'saved'}
										<span class="save-tag saved">✓ Saved</span>
										<span>Submitted</span>
									{:else}
										<span class="save-tag empty">— Empty</span>
										<span>Enter a score to predict</span>
									{/if}
								</div>
							</div>
						{:else}
							<div style="padding: 16px; font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.08em;">
								No knockout fixtures yet — Phase II starts once groups conclude.
							</div>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Sticky save bar for phase 2 match score picks -->
			<section class="pn-wiz-foot">
				<div class="stats">
					{#if $unsavedChangesCount === 0}
						All changes saved
					{:else}
						<b>{$unsavedChangesCount}</b> match {$unsavedChangesCount === 1 ? 'pick' : 'picks'} unsaved
					{/if}
				</div>
				{#if $lastLocalSave}
					<span class="saved-tag">Saved locally · {formatLocalTime($lastLocalSave)}</span>
				{/if}
				<button
					class="submit-btn"
					class:success={saveStatus === 'saved'}
					class:error={saveStatus === 'error'}
					on:click={handleSaveAll}
					disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}
				>
					{#if saveStatus === 'saving'}Saving…
					{:else if saveStatus === 'saved'}✓ Saved
					{:else if saveStatus === 'error'}× Error — retry
					{:else}Save Phase II ({$unsavedChangesCount}){/if}
				</button>
			</section>
		{/if}
	</PnPageShell>
{/if}

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
		entries,
		activeEntryId,
		activeEntry,
		entrySettings
	} from '$stores/entries';
	import * as entriesApi from '$api/entries';
	import { canSubmit, canEdit } from '$lib/types/entry';
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
		phase2Countdown,
		phase1Deadline
	} from '$stores/phase';
	import { applyFifaTiebreakers, computeGroupStandingsMapWithWarnings } from '$lib/utils/standings';
	import {
		initPersistence,
		teardownPersistence,
		hydrateFromStorage,
		lastLocalSave
	} from '$stores/unsavedPersistence';
	import { teamCode } from '$lib/utils/teamCodes';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { Fixture, MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';

	import KnockoutBracket from '$components/bracket/KnockoutBracket.svelte';
	import EntrySelector from '$components/EntrySelector.svelte';
	import SheetStatusDots from '$components/predictions/SheetStatusDots.svelte';
	import CountdownTimer from '$components/predictions/CountdownTimer.svelte';
	import SheetSelector from '$components/predictions/SheetSelector.svelte';
	import ConfirmModal from '$components/predictions/ConfirmModal.svelte';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	// Phase + pill selection state. Phase 2 is dormant in the simplified
	// lifecycle — the wizard always operates on Phase 1. The `activePhase`
	// variable stays so the Phase 2 conditional branches in the markup
	// dead-code at runtime without a structural rewrite (preserves the
	// Phase 2 surface for a future revival per plan i-want-to-simplify-
	// bright-wolf.md).
	// Typed as string (not literal) so TypeScript doesn't narrow the
	// Phase 2 conditional branches to never-true. The Phase I/II toggle
	// markup is preserved as dead code (gated on $isPhase2Active which
	// stays false while Phase 2 is dormant).
	let activePhase: string = 'phase1';

	// Section toggle controls the outer mode (Groups / Knockout / Bonus).
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
	// score inputs of a match card. We use focusin/focusout (which bubble) on
	// the parent card so tabbing between inputs doesn't briefly clear it.
	let editingFixtureId: string | null = null;

	function handleMatchCardFocusIn(fixtureId: string, isLocked: boolean): void {
		if (!isLocked) editingFixtureId = fixtureId;
	}

	function handleMatchCardFocusOut(e: FocusEvent): void {
		const card = e.currentTarget as HTMLElement;
		const next = e.relatedTarget as Node | null;
		if (!next || !card.contains(next)) editingFixtureId = null;
	}

	onMount(async () => {
		if ($isAuthenticated) {
			const tasks: Promise<unknown>[] = [fetchGroupFixtures()];
			if ($isPhase2Active) {
				tasks.push(fetchActualKnockoutFixtures(), fetchActualStandings());
			}
			await Promise.all(tasks);
		}
		window.addEventListener('beforeunload', handleBeforeUnload);
	});

	// Load entries as soon as $user.id resolves. Using $: not onMount because
	// initAuth() / fetchUser() can complete AFTER this page's onMount.
	let entriesLoadStarted = false;
	$: if ($isAuthenticated && $user?.id && !entriesLoadStarted) {
		entriesLoadStarted = true;
		void loadEntries($user.id);
	}

	// Re-fetch predictions whenever the active entry changes.
	let lastActiveEntryId: string | null = null;
	$: if ($isAuthenticated && $activeEntryId && $activeEntryId !== lastActiveEntryId) {
		const prev = lastActiveEntryId;
		lastActiveEntryId = $activeEntryId;
		resetPredictions();
		if (prev && $user) {
			teardownPersistence($user.id, prev);
		}
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

	// Hydrate drafts from localStorage + start the persistence subscription.
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

	// Variant for the new SheetSelector — it dispatches `rename` with the
	// specific entry id (any row can be renamed, not just the active one).
	// Keeps the legacy zero-arg handler above unchanged for EntrySelector.
	async function handleSheetRename(event: CustomEvent<{ entryId: string }>): Promise<void> {
		const target = $entries.find((e) => e.id === event.detail.entryId);
		if (!target) return;
		const next = window.prompt('Sheet name', target.display_name);
		if (!next || next.trim() === '' || next.trim() === target.display_name) return;
		try {
			await entriesApi.renameEntry(target.id, { display_name: next.trim() });
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
			const { setActiveEntry } = await import('$stores/entries');
			setActiveEntry(created.id);
		} catch (e) {
			console.error('Duplicate failed', e);
		}
	}

	// ---- Entry-lifecycle handlers (Mark Ready / Submit / Reopen / Withdraw)
	let lifecycleBusy: false | 'submit' | 'edit' = false;
	let lifecycleError: string | null = null;

	$: currentPhaseEnum = (activePhase === 'phase2' ? 'phase_2' : 'phase_1') as
		import('$types').PredictionPhase;

	// Pull the competition's phase1_deadline from the phase store so the
	// Submit / Edit buttons hide once the competition has started.
	$: submitVisible =
		!!$activeEntry &&
		canSubmit($activeEntry, currentPhaseEnum, $phase1Deadline ?? null);
	$: editVisible =
		!!$activeEntry &&
		canEdit($activeEntry, currentPhaseEnum, $phase1Deadline ?? null);

	// ConfirmModal state — one boolean per modal usage on this page.
	// Lock modal = "Submit" confirmation; Unlock modal = "Edit" / revert.
	let lockModalOpen = false;
	let unlockModalOpen = false;

	function handleSubmit(): void {
		if (!$activeEntry) return;
		lifecycleError = null;
		lockModalOpen = true;
	}

	async function confirmSubmit(): Promise<void> {
		lockModalOpen = false;
		const current = $activeEntry;
		if (!current) return;
		lifecycleBusy = 'submit';
		lifecycleError = null;
		try {
			await entriesApi.submitEntry(current.id);
			await refreshEntries();
		} catch (e) {
			lifecycleError = e instanceof Error ? e.message : 'Failed to submit';
		} finally {
			lifecycleBusy = false;
		}
	}

	function handleEdit(): void {
		if (!$activeEntry) return;
		lifecycleError = null;
		unlockModalOpen = true;
	}

	async function confirmEdit(): Promise<void> {
		unlockModalOpen = false;
		const current = $activeEntry;
		if (!current) return;
		lifecycleBusy = 'edit';
		lifecycleError = null;
		try {
			await entriesApi.editEntry(current.id);
			await refreshEntries();
		} catch (e) {
			lifecycleError = e instanceof Error ? e.message : 'Failed to revert to draft';
		} finally {
			lifecycleBusy = false;
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

	// ---- Group selector navigation (prev / next / keyboard) --------------
	// Ordered pill list: A, B, …, L, then 'thirdplace'. Loops at the ends.
	$: pillOrder = [...$groupFixtures.map((g) => g.group), 'thirdplace'];

	function stepGroup(delta: number) {
		if (pillOrder.length === 0) return;
		const idx = pillOrder.indexOf(activeGroupPill);
		const next = (idx + delta + pillOrder.length) % pillOrder.length;
		activeGroupPill = pillOrder[next];
	}

	function isTypingInInput(el: EventTarget | null): boolean {
		if (!(el instanceof HTMLElement)) return false;
		const tag = el.tagName;
		return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
	}

	function handleSelectorKeydown(e: KeyboardEvent) {
		// Only steal arrow keys when the user isn't editing a score.
		if (activeSection !== 'groups') return;
		if (isTypingInInput(e.target)) return;
		if (e.key === 'ArrowLeft') { e.preventDefault(); stepGroup(-1); }
		else if (e.key === 'ArrowRight') { e.preventDefault(); stepGroup(1); }
	}

	// ---- Derived: focused-header info for the active selection -----------
	$: focusedInfo = (() => {
		if (activeGroupPill === 'thirdplace') {
			const filled = thirdPlaceStandings?.length ?? 0;
			return {
				badge: '3rd',
				title: '3RD PLACE',
				caption: 'Top 8 third-placed teams advance',
				meta: filled > 0 ? `${filled} of 12 ranked` : 'Fill group predictions to rank thirds'
			};
		}
		const g = selectedGroup;
		if (!g) return null;
		const gp = groupProgress(g);
		const std = standingsMap[g.group] ?? [];
		const leader = std[0]?.team;
		const anyPicks = gp.done > 0;
		const tied = groupStandingsWarnings.some((w) => w.group === g.group);
		const metaParts: string[] = [];
		if (anyPicks && leader) metaParts.push(`${leader} leads`);
		if (tied && gp.done === gp.total) metaParts.push('tied — needs a tiebreaker');
		return {
			badge: g.group,
			title: `GROUP ${g.group}`,
			caption: `${gp.done} of ${gp.total} predicted`,
			meta: metaParts.length > 0 ? metaParts.join(' · ') : 'No matches predicted yet'
		};
	})();

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
	$: groupProgress = (g: { group: string; fixtures: Fixture[] }) => {
		let done = 0;
		for (const f of g.fixtures) {
			if (livePredictionMap.has(f.id)) done++;
		}
		return { done, total: g.fixtures.length };
	};

	// Phase 1 knockout bracket is gated on completing every group prediction.
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
	$: thirdPlaceResult = (() => {
		const thirds = [];
		for (const [group, std] of Object.entries(standingsMap)) {
			if (std[2]) thirds.push({ ...std[2], group });
		}
		return applyFifaTiebreakers(thirds, [], new Map(), 'third_place_qualifying');
	})();
	$: thirdPlaceStandings = thirdPlaceResult.sorted;
	$: thirdPlaceWarnings = thirdPlaceResult.warnings;

	// Maximum goals allowed in a single match's score input.
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

	$: predictionState = (f: Fixture): FixtureState =>
		predictionStateMap.get(f.id) ?? (f.is_locked ? 'locked' : 'empty');

	$: scoreValue = (fixtureId: string, side: 'home' | 'away'): string => {
		const entry = scoreValueMap.get(fixtureId);
		return entry ? entry[side] : '';
	};

	// ---- Bracket (Phase 1) ------------------------------------------------
	let bracketComponent: KnockoutBracket;
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
	let phase2BracketComponent: KnockoutBracket;
	let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	$: phase2DisplayBracket = $unsavedPhase2BracketPrediction || $phase2BracketPrediction;
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

	$: if ($isAuthenticated && bonusQuestions.length === 0) {
		loadBonus().catch(() => {});
	}

	function fmtCard(iso: string): string {
		const d = new Date(iso);
		return (
			d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) +
			' · ' +
			d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
		);
	}

	// Compact countdown for the match-card lock chip: "21d 21h", "2h 30m",
	// "5m 30s" or "locked". `secs` is `time_until_lock` from FixtureRead.
	function fmtCountdown(secs: number | null | undefined): string {
		if (secs == null || secs <= 0) return 'locked';
		const d = Math.floor(secs / 86400);
		const h = Math.floor((secs % 86400) / 3600);
		const m = Math.floor((secs % 3600) / 60);
		const s = secs % 60;
		if (d > 0) return `${d}d ${h}h`;
		if (h > 0) return `${h}h ${m}m`;
		if (m > 0) return `${m}m ${s}s`;
		return `${s}s`;
	}
</script>

<svelte:head>
	<title>Predictions - Predictor v2</title>
</svelte:head>

<!-- Group-selector arrow-key navigation. The handler self-guards on
     activeSection !== 'groups' and on typing-in-input, so it's a no-op
     for the knockout / bonus / Phase 2 sections and while editing scores. -->
<svelte:window on:keydown={handleSelectorKeydown} />

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		{#if restorationBanner}
			<div class="alert bg-info/10 border border-info/30 text-sm mb-4" transition:fade={{ duration: 400 }}>
				<span>✦</span>
				<span>
					<b>Drafts restored from your last session.</b>
					{#if restorationBanner.matchCount > 0}{restorationBanner.matchCount} unsaved match {restorationBanner.matchCount === 1 ? 'pick' : 'picks'}{/if}
					{#if restorationBanner.bracketPhase1Restored} · Phase I bracket{/if}
					{#if restorationBanner.bracketPhase2Restored} · Phase II bracket{/if}
					— remember to press Save when you're done.
				</span>
				<button class="btn btn-ghost btn-xs" on:click={() => (restorationBanner = null)}>×</button>
			</div>
		{/if}

		<!-- Hero: title + progress + entry selector + toggles -->
		<div class="stadium-card no-glow p-5 mb-6">
			<div class="flex items-start justify-between flex-wrap gap-4">
				<div>
					<p class="text-xs uppercase tracking-wider text-base-content/50">
						Group Stage · Knockout · Bonus
					</p>
					<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Predict</h1>
				</div>
				<div class="flex items-center gap-4">
					<div class="text-right">
						<div class="font-display text-3xl tracking-wide leading-none">
							{phaseProgress.done}<span class="text-base text-base-content/40">/{phaseProgress.total}</span>
						</div>
						<div class="text-xs text-base-content/50">{phaseProgress.pct}% predicted</div>
					</div>
					<SheetStatusDots />
				</div>
			</div>

			<!-- Live countdown badge (DDd HH:MM:SS; hides past deadline; red <6h) -->
			<div class="mt-3">
				<CountdownTimer deadline={$phase1Deadline} />
			</div>

			<!-- Progress bar -->
			<div class="mt-3">
				<div class="w-full h-2 rounded-full bg-base-300/60 overflow-hidden">
					<div class="h-full bg-primary transition-all" style="width: {phaseProgress.pct}%;"></div>
				</div>
				<div class="flex justify-between text-xs text-base-content/50 mt-1">
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

			<!-- Entry selector + lifecycle -->
			<div class="flex items-center gap-3 flex-wrap mt-4">
				<SheetSelector
					activeProgress={{ done: phaseProgress.done, total: phaseProgress.total }}
					on:create={handleEntryCreate}
					on:rename={handleSheetRename}
				/>
				{#if lifecycleError}
					<span class="text-error text-xs">{lifecycleError}</span>
				{/if}
				{#if submitVisible}
					<button class="btn btn-sm btn-primary" type="button" on:click={handleSubmit} disabled={lifecycleBusy !== false}>
						{lifecycleBusy === 'submit' ? 'Submitting…' : 'Submit'}
					</button>
				{/if}
				{#if editVisible}
					<button class="btn btn-sm btn-outline" type="button" on:click={handleEdit} disabled={lifecycleBusy !== false} title="Revert to draft so you can change your picks">
						{lifecycleBusy === 'edit' ? 'Reverting…' : 'Edit'}
					</button>
				{/if}
			</div>

			<!-- Phase + section toggles -->
			<div class="flex items-center gap-3 flex-wrap mt-4">
				{#if $isPhase2Active}
					<div class="tabs tabs-boxed bg-base-300/40">
						<button class="tab {activePhase === 'phase1' ? 'tab-active' : ''}" on:click={() => (activePhase = 'phase1')}>Phase I</button>
						<button class="tab {activePhase === 'phase2' ? 'tab-active' : ''}" on:click={() => (activePhase = 'phase2')}>Phase II</button>
					</div>
				{/if}
				{#if activePhase === 'phase1'}
					<div class="tabs tabs-boxed bg-base-300/40">
						<button class="tab {activeSection === 'groups' ? 'tab-active' : ''}" on:click={() => (activeSection = 'groups')}>Groups</button>
						<button
							class="tab {activeSection === 'knockout' ? 'tab-active' : ''} {phase1BracketGated ? 'opacity-50' : ''}"
							on:click={() => (activeSection = 'knockout')}
							title={phase1BracketGated ? 'Complete all group predictions to unlock' : ''}
						>Knockout</button>
						<button class="tab {activeSection === 'bonus' ? 'tab-active' : ''}" on:click={() => (activeSection = 'bonus')}>Bonus</button>
					</div>
				{/if}
			</div>
		</div>

		<!-- ============================== PHASE 1 ============================== -->
		{#if activePhase === 'phase1'}
			<!-- Group selector: focused hero header + compact pill strip -->
			{#if activeSection === 'groups'}
				<div class="group-selector mb-6">
					<!-- Focused hero -->
					<div class="group-selector-hero">
						<button
							class="group-stepper-btn"
							type="button"
							aria-label="Previous group"
							on:click={() => stepGroup(-1)}
						>
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" /></svg>
							<span>Prev</span>
						</button>

						<div class="group-focus-info">
							<div class="group-focus-badge {activeGroupPill === 'thirdplace' ? 'is-thirdplace' : ''}">
								<span>{focusedInfo?.badge ?? '—'}</span>
							</div>
							<div class="group-focus-text">
								<div class="text-[10px] uppercase tracking-[0.22em] text-base-content/45 mb-0.5">
									{focusedInfo?.caption ?? ''}
								</div>
								<h2 class="font-display text-2xl sm:text-3xl tracking-widest leading-none">
									{focusedInfo?.title ?? ''}
								</h2>
								<div class="text-xs text-base-content/55 mt-1.5 truncate">
									{focusedInfo?.meta ?? ''}
								</div>
							</div>
						</div>

						<button
							class="group-stepper-btn"
							type="button"
							aria-label="Next group"
							on:click={() => stepGroup(1)}
						>
							<span>Next</span>
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
						</button>
					</div>

					<!-- Compact mini-pill strip — all 12 groups + 3rd place -->
					<div class="group-pill-strip">
						{#each $groupFixtures as g (g.group)}
							{@const gp = groupProgress(g)}
							{@const isActive = activeGroupPill === g.group}
							{@const isComplete = gp.total > 0 && gp.done === gp.total}
							{@const hasTie = groupStandingsWarnings.some((w) => w.group === g.group)}
							{@const pct = gp.total > 0 ? Math.round((gp.done / gp.total) * 100) : 0}
							<button
								class="group-mini-pill {isActive ? 'is-active' : ''} {isComplete && hasTie ? 'is-tied' : isComplete ? 'is-complete' : ''}"
								type="button"
								on:click={() => (activeGroupPill = g.group)}
								title="Group {g.group} · {gp.done}/{gp.total}{hasTie && isComplete ? ' · tied' : ''}"
								aria-label="Group {g.group}, {gp.done} of {gp.total} predicted"
							>
								<span class="letter">{g.group}</span>
								<span class="progress-bar"><span class="progress-fill" style="width: {pct}%"></span></span>
							</button>
						{/each}
						<button
							class="group-mini-pill is-thirdplace {activeGroupPill === 'thirdplace' ? 'is-active' : ''}"
							type="button"
							on:click={() => (activeGroupPill = 'thirdplace')}
							title="3rd Place qualifying"
							aria-label="Third place qualifying view"
						>
							<span class="letter">3rd</span>
						</button>
					</div>
				</div>
			{/if}

			<!-- Third place view -->
			{#if activeSection === 'groups' && activeGroupPill === 'thirdplace'}
				<div class="stadium-card no-glow p-4 sm:p-5">
					{#if allGroupsComplete && thirdPlaceWarnings.length > 0}
						<div class="alert alert-warning text-sm mb-4">
							<div>
								<h4 class="font-semibold">⚠ Tied teams · alphabetical fallback in effect</h4>
								{#each thirdPlaceWarnings as w (w.tiedTeams.join('-'))}
									<p class="text-xs mt-1">{w.tiedTeams.join(', ')} are tied on points, GD and GF. Third-place teams come from different groups so head-to-head isn't applicable — currently ranked alphabetically. Adjust scores to change qualification.</p>
								{/each}
							</div>
						</div>
					{/if}
					<h2 class="text-lg font-display tracking-wide mb-3">Third-place standings · top 8 advance to R32</h2>
					<div class="group-standings">
						<table class="standings-table">
							<thead>
								<tr><th></th><th class="text-center">Grp</th><th class="text-left">Team</th><th class="text-center">P</th><th class="text-center">W</th><th class="text-center">D</th><th class="text-center">L</th><th class="text-center">GF</th><th class="text-center">GA</th><th class="text-center">GD</th><th>Pts</th></tr>
							</thead>
							<tbody>
								{#each thirdPlaceStandings as t, i (t.team)}
									<tr class="standing-row {i < 8 ? 'bg-success/5' : ''}">
										<td><span class="position-indicator {i < 8 ? '!bg-success/20 !text-success' : ''}">{i + 1}</span></td>
										<td class="text-center text-xs">{t.group}</td>
										<td>
											<span class="flex items-center gap-2">
												{#if hasFlag(t.team)}<img src={getFlagUrl(t.team, 'sm')} alt="" class="team-flag" />{/if}
												<span class="team-name-table">{t.team}</span>
											</span>
										</td>
										<td class="text-center">{t.played}</td>
										<td class="text-center">{t.won}</td>
										<td class="text-center">{t.drawn}</td>
										<td class="text-center">{t.lost}</td>
										<td class="text-center">{t.goalsFor}</td>
										<td class="text-center">{t.goalsAgainst}</td>
										<td class="text-center gd-cell {t.goalDifference >= 0 ? 'positive' : 'negative'}">{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}</td>
										<td><span class="points-badge">{t.points}</span></td>
									</tr>
								{:else}
									<tr><td colspan="11" class="text-center py-6 text-base-content/40">No third-place standings yet — fill in some group predictions</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="text-xs text-base-content/50 mt-3 uppercase tracking-wider">★ Top 8 third-placed teams qualify for the Round of 32 under FIFA 2026 format</p>
				</div>
			{:else if activeSection === 'groups' && selectedGroup}
				{@const group = selectedGroup}
				{@const standings = standingsMap[group.group] ?? []}
				{@const groupWarnings = groupStandingsWarnings.filter((w) => w.group === group.group)}
				{@const groupGp = groupProgress(group)}
				{@const groupComplete = groupGp.total > 0 && groupGp.done === groupGp.total}

				{#if groupComplete && groupWarnings.length > 0}
					<div class="alert alert-warning text-sm mb-5">
						<div>
							<h4 class="font-semibold">⚠ Tied teams in Group {group.group}</h4>
							{#each groupWarnings as w (w.tiedTeams.join('-'))}
								<p class="text-xs mt-1">{w.tiedTeams.join(', ')} are tied on points, GD, GF and head-to-head — currently ranked alphabetically. Adjust scores to change the ordering.</p>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Predicted Standings (full width) -->
				<section class="mb-8">
					<h3 class="section-label">
						<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19V6h6v13M5 19v-7h4v7M15 19v-3h4v3" /></svg>
						Predicted Standings
					</h3>
					<div class="standings-card">
						<table class="standings-table-v2">
							<thead>
								<tr>
									<th class="w-10 text-left pl-4">#</th>
									<th class="text-left">Team</th>
									<th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each standings as t, i (t.team)}
									{@const pos = i < 2 ? 'advance' : i === 2 ? 'thirdplace' : 'out'}
									<tr class="standing-row-v2 pos-{pos}">
										<td class="rank-cell"><span class="rank-pill pos-{pos}">{i + 1}</span></td>
										<td class="team-cell">
											<div class="team-content">
												{#if hasFlag(t.team)}<img src={getFlagUrl(t.team, 'sm')} alt="" class="team-flag" />{/if}
												<span class="team-name">{t.team}</span>
											</div>
										</td>
										<td class="num">{t.played}</td>
										<td class="num"><span class={t.won > 0 ? 'text-success' : 'text-base-content/40'}>{t.won}</span></td>
										<td class="num">{t.drawn}</td>
										<td class="num"><span class={t.lost > 0 ? 'text-error' : 'text-base-content/40'}>{t.lost}</span></td>
										<td class="num">{t.goalsFor}</td>
										<td class="num">{t.goalsAgainst}</td>
										<td class="num"><span class={t.goalDifference > 0 ? 'text-success' : t.goalDifference < 0 ? 'text-error' : 'text-base-content/60'}>{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}</span></td>
										<td class="text-center"><span class="pts-badge">{t.points}</span></td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="flex gap-4 text-xs text-base-content/50 mt-3">
						<span class="flex items-center gap-1.5"><span class="w-0.5 h-3 bg-success rounded"></span>Advances (top 2)</span>
						<span class="flex items-center gap-1.5"><span class="w-0.5 h-3 bg-warning rounded"></span>Best 3rd</span>
						<span class="flex items-center gap-1.5"><span class="w-0.5 h-3 bg-error rounded"></span>Out</span>
					</div>
				</section>

				<!-- Match Predictions (responsive grid) -->
				<section>
					<h3 class="section-label">
						<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
						Match Predictions
					</h3>
					<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
						{#each group.fixtures as f (f.id)}
							{@const state = predictionState(f)}
							{@const countdown = fmtCountdown(f.time_until_lock)}
							<div
								class="match-card-v2 {state === 'locked' ? 'is-locked' : ''} {editingFixtureId === f.id ? 'is-editing' : ''}"
								on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
								on:focusout={handleMatchCardFocusOut}
							>
								<div class="match-card-header">
									<div class="flex items-center gap-2 text-xs text-base-content/50">
										<span>{fmtCard(f.kickoff)}</span>
										<span class="group-tag">Group {group.group}</span>
									</div>
									<span class="countdown-chip {countdown === 'locked' ? 'is-locked' : ''}">{countdown}</span>
								</div>

								<div class="match-card-body">
									<!-- Home team -->
									<div class="team-block" title={f.home_team}>
										{#if hasFlag(f.home_team)}<img src={getFlagUrl(f.home_team, 'sm')} alt="" class="flag" />{/if}
										<div class="team-label">{f.home_team}</div>
									</div>
									<!-- Score inputs with vs -->
									<div class="score-row">
										<input type="number" class="score-box" class:opacity-50={state === 'empty'} min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'home')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'home', e.currentTarget.value); }} aria-label="{f.home_team} score" />
										<span class="vs-pill">vs</span>
										<input type="number" class="score-box" class:opacity-50={state === 'empty'} min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'away')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'away', e.currentTarget.value); }} aria-label="{f.away_team} score" />
									</div>
									<!-- Away team -->
									<div class="team-block" title={f.away_team}>
										{#if hasFlag(f.away_team)}<img src={getFlagUrl(f.away_team, 'sm')} alt="" class="flag" />{/if}
										<div class="team-label">{f.away_team}</div>
									</div>
								</div>

								<div class="match-card-footer">
									{#if state === 'locked'}<span class="badge badge-sm badge-ghost">Locked</span>
									{:else if state === 'draft'}<span class="badge badge-sm badge-warning">Draft</span><span class="text-base-content/40 text-xs">Save to commit</span>
									{:else if state === 'saved'}<span class="badge badge-sm badge-success">✓ Saved</span>
									{:else}<span class="badge badge-sm badge-ghost">Empty</span><span class="text-base-content/40 text-xs">Enter a score</span>{/if}
									{#if editingFixtureId === f.id}<span class="text-primary text-xs ml-auto">editing</span>{/if}
								</div>
							</div>
						{/each}
					</div>
				</section>
			{:else if activeSection === 'knockout'}
				{#if phase1BracketGated}
					<div class="stadium-card no-glow p-8 text-center max-w-xl mx-auto">
						<div class="text-4xl mb-2">🔒</div>
						<h2 class="text-2xl font-display tracking-wide mb-2">Knockout bracket locked</h2>
						<p class="text-sm text-base-content/60 mb-4">Predict every group-stage match before opening the bracket. It seeds the Round of 32 from your predicted standings.</p>
						<div class="font-display text-3xl tracking-wide">{phaseProgress.done}<span class="text-base text-base-content/40">/{phaseProgress.total}</span></div>
						<div class="text-xs text-base-content/50 mb-3">matches predicted · {phaseProgress.pct}%</div>
						<div class="w-full h-2 rounded-full bg-base-300/60 overflow-hidden mb-4"><div class="h-full bg-primary" style="width: {phaseProgress.pct}%;"></div></div>
						<button class="btn btn-primary btn-sm" type="button" on:click={() => (activeSection = 'groups')}>← Back to Groups</button>
					</div>
				{:else}
					<KnockoutBracket
						bind:this={bracketComponent}
						prediction={displayBracket}
						groupStandings={standingsMap}
						locked={$isPhase1Locked}
						phase="phase_1"
						on:update={handleBracketUpdate}
					/>
					<div class="flex gap-3 justify-end mt-3">
						{#if $hasUnsavedBracketChanges}
							<button class="btn btn-primary btn-sm" on:click={handleSaveBracket} disabled={bracketSaveStatus === 'saving'}>
								{bracketSaveStatus === 'saving' ? 'Saving…' : bracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
							</button>
						{/if}
					</div>
				{/if}
			{:else if activeSection === 'bonus'}
				{#each Object.entries(bonusByCategory) as [cat, qs] (cat)}
					{#if qs.length > 0}
						<h2 class="text-lg font-display tracking-wide mt-5 mb-3">{CATEGORY_LABEL[cat]} <span class="text-sm text-base-content/40">· {qs.length} question{qs.length === 1 ? '' : 's'}</span></h2>
						<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
							{#each qs as bq (bq.id)}
								{@const answer = bonusAnswer(bq.id)}
								<div class="stadium-card no-glow p-4">
									<div class="text-sm font-medium mb-2">{bq.label}</div>
									{#if bq.input_type === 'team'}
										<select class="select select-bordered select-sm w-full" value={answer} on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}>
											<option value="">— Select a team —</option>
											{#each allTeams as t (t)}<option value={t}>{t}</option>{/each}
										</select>
									{:else}
										<input type="text" class="input input-bordered input-sm w-full" value={answer} on:input={(e) => setBonusAnswer(bq.id, e.currentTarget.value)} placeholder="Type a player name…" />
									{/if}
									<div class="text-xs text-accent mt-2">+{bq.points} pts</div>
								</div>
							{/each}
						</div>
					{/if}
				{/each}

				<div class="flex justify-end items-center gap-3 mt-4">
					<span class="text-xs text-base-content/50">{bonusAnswers.size} of {bonusQuestions.length} answered</span>
					<button class="btn btn-primary btn-sm" on:click={handleSaveBonus} disabled={!hasUnsavedBonus || bonusSaveStatus === 'saving'}>
						{bonusSaveStatus === 'saving' ? 'Saving…' : bonusSaveStatus === 'saved' ? '✓ Saved' : bonusSaveStatus === 'error' ? '× Error — retry' : 'Save bonus picks'}
					</button>
				</div>
				<p class="text-xs text-base-content/50 mt-3 uppercase tracking-wider">★ Bonus picks lock with Phase I · admin reveals correct answers as the tournament resolves</p>
			{/if}

			<!-- Save bar (Phase I) -->
			<div class="sticky bottom-0 mt-6 -mx-4 px-4 py-3 bg-base-200/95 backdrop-blur-md border-t border-base-300 flex items-center gap-3 flex-wrap">
				<div class="text-sm flex-1">
					{#if $unsavedChangesCount === 0 && !$hasUnsavedBracketChanges}
						All changes saved
					{:else}
						{#if $unsavedChangesCount > 0}<b>{$unsavedChangesCount}</b> match {$unsavedChangesCount === 1 ? 'pick' : 'picks'} unsaved{/if}
						{#if $unsavedChangesCount > 0 && $hasUnsavedBracketChanges} · {/if}
						{#if $hasUnsavedBracketChanges}bracket has unsaved changes{/if}
					{/if}
				</div>
				{#if $lastLocalSave}<span class="text-xs text-base-content/40">Saved locally · {formatLocalTime($lastLocalSave)}</span>{/if}
				<button class="btn btn-primary {saveStatus === 'error' ? 'btn-error' : ''}" on:click={handleSaveAll} disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}>
					{#if saveStatus === 'saving'}Saving…{:else if saveStatus === 'saved'}✓ Saved{:else if saveStatus === 'error'}× Error — retry{:else}Save Phase I ({$unsavedChangesCount}){/if}
				</button>
			</div>
		{/if}

		<!-- ============================== PHASE 2 ============================== -->
		{#if activePhase === 'phase2'}
			{#if $actualStandingsLoading}
				<p class="text-sm text-base-content/50 p-4">Loading Phase II data…</p>
			{:else}
				<KnockoutBracket
					bind:this={phase2BracketComponent}
					prediction={phase2DisplayBracket}
					groupStandings={$actualGroupStandingsMap}
					locked={$isPhase2BracketLocked}
					phase="phase_2"
					on:update={handlePhase2BracketUpdate}
				/>
				<div class="flex gap-3 justify-end mt-3 mb-5">
					{#if $hasUnsavedPhase2BracketChanges}
						<button class="btn btn-primary btn-sm" on:click={handleSavePhase2Bracket} disabled={phase2BracketSaveStatus === 'saving'}>
							{phase2BracketSaveStatus === 'saving' ? 'Saving…' : phase2BracketSaveStatus === 'saved' ? '✓ Saved' : 'Save bracket'}
						</button>
					{/if}
				</div>

				<!-- Knockout fixture score predictions (Phase 2 only) -->
				<h2 class="text-lg font-display tracking-wide mb-3">Knockout <span class="text-primary">scores</span></h2>
				<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
					{#each $actualKnockoutFixtures as f (f.id)}
						{@const state = predictionState(f)}
						<div
							class="match-card {state === 'locked' ? 'locked' : ''} {editingFixtureId === f.id ? 'ring-2 ring-primary' : ''}"
							on:focusin={() => handleMatchCardFocusIn(f.id, f.is_locked)}
							on:focusout={handleMatchCardFocusOut}
						>
							<div class="text-xs text-base-content/40 mb-2">{fmtCard(f.kickoff)}</div>
							<div class="flex items-center justify-between gap-2">
								<div class="flex items-center gap-2 flex-1 min-w-0" title={f.home_team}>
									{#if hasFlag(f.home_team)}<img src={getFlagUrl(f.home_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
									<span class="team-name">{teamCode(f.home_team)}</span>
								</div>
								<div class="flex items-center gap-1 shrink-0">
									<input type="number" class="score-input" min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'home')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'home', e.currentTarget.value); }} aria-label="{f.home_team} score" />
									<span class="text-base-content/40">–</span>
									<input type="number" class="score-input" min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'away')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'away', e.currentTarget.value); }} aria-label="{f.away_team} score" />
								</div>
								<div class="flex items-center gap-2 flex-1 min-w-0 justify-end" title={f.away_team}>
									<span class="team-name">{teamCode(f.away_team)}</span>
									{#if hasFlag(f.away_team)}<img src={getFlagUrl(f.away_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" />{/if}
								</div>
							</div>
							<div class="flex items-center gap-2 mt-2 text-xs">
								{#if state === 'locked'}<span class="badge badge-sm badge-ghost">Locked</span>
								{:else if state === 'draft'}<span class="badge badge-sm badge-warning">Draft</span>
								{:else if state === 'saved'}<span class="badge badge-sm badge-success">✓ Saved</span>
								{:else}<span class="badge badge-sm badge-ghost">Empty</span>{/if}
							</div>
						</div>
					{:else}
						<p class="text-sm text-base-content/40 p-4">No knockout fixtures yet — Phase II starts once groups conclude.</p>
					{/each}
				</div>

				<!-- Save bar (Phase II) -->
				<div class="sticky bottom-0 mt-6 -mx-4 px-4 py-3 bg-base-200/95 backdrop-blur-md border-t border-base-300 flex items-center gap-3 flex-wrap">
					<div class="text-sm flex-1">
						{#if $unsavedChangesCount === 0}All changes saved{:else}<b>{$unsavedChangesCount}</b> match {$unsavedChangesCount === 1 ? 'pick' : 'picks'} unsaved{/if}
					</div>
					{#if $lastLocalSave}<span class="text-xs text-base-content/40">Saved locally · {formatLocalTime($lastLocalSave)}</span>{/if}
					<button class="btn btn-primary {saveStatus === 'error' ? 'btn-error' : ''}" on:click={handleSaveAll} disabled={!$hasUnsavedChanges || saveStatus === 'saving' || $matchPredictionsLoading}>
						{#if saveStatus === 'saving'}Saving…{:else if saveStatus === 'saved'}✓ Saved{:else if saveStatus === 'error'}× Error — retry{:else}Save Phase II ({$unsavedChangesCount}){/if}
					</button>
				</div>
			{/if}
		{/if}

		<!-- ConfirmModal instances (one per lifecycle action). Fixed-positioned,
		     so their DOM location is purely organizational. -->
		<ConfirmModal
			open={lockModalOpen}
			icon="🔒"
			title="Lock in your predictions?"
			message={$activeEntry
				? `"${$activeEntry.display_name}" becomes official and qualifies for scoring. You can still tap Edit to revert until the competition starts.`
				: ''}
			confirmLabel="Lock In"
			confirmVariant="success"
			onConfirm={confirmSubmit}
			onCancel={() => (lockModalOpen = false)}
		/>

		<ConfirmModal
			open={unlockModalOpen}
			icon="✏️"
			title="Revert to draft?"
			message={$activeEntry
				? `"${$activeEntry.display_name}" goes back to draft. Your predictions stay as they are — you'll just need to tap Lock In again before the competition starts.`
				: ''}
			confirmLabel="Revert"
			confirmVariant="warning"
			onConfirm={confirmEdit}
			onCancel={() => (unlockModalOpen = false)}
		/>
	</div>
{/if}

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fade, fly, slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { goto, beforeNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { updateProfile } from '$api/auth';
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
		editableEntries,
		activeEntryId,
		activeEntry,
		setActiveEntry,
		entrySettings
	} from '$stores/entries';
	import * as entriesApi from '$api/entries';
	import { canSubmit, canEdit, isPhaseEditable, computeDisplayStatus } from '$lib/types/entry';
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
	import { predictionToBracketState } from '$lib/utils/bracketResolver';
	import {
		ROUND_OF_32,
		ROUND_OF_16,
		QUARTER_FINALS,
		SEMI_FINALS,
		FINAL
	} from '$lib/config/bracketConfig';
	import {
		initPersistence,
		teardownPersistence,
		hydrateFromStorage,
		lastLocalSave
	} from '$stores/unsavedPersistence';
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { Fixture, MatchPrediction, BracketPrediction, TeamAdvancementPrediction } from '$types';

	import KnockoutBracket from '$components/bracket/KnockoutBracket.svelte';
	import EntrySelector from '$components/EntrySelector.svelte';
	import ConfirmModal from '$components/predictions/ConfirmModal.svelte';
	import ErrorModal from '$components/predictions/ErrorModal.svelte';
	import LifecycleConflictModal from '$components/predictions/LifecycleConflictModal.svelte';
	import CompletenessModal from '$components/predictions/CompletenessModal.svelte';
	import MultiTabConfirmModal from '$components/predictions/MultiTabConfirmModal.svelte';
	import { ApiResponseError } from '$api/client';
	import { track } from '$lib/analytics';
	import {
		registerTabPresence,
		unregisterTabPresence,
		otherTabCount
	} from '$lib/utils/tabPresence';
	import GroupAccordion from '$components/predictions/GroupAccordion.svelte';
	import WizardStepper from '$components/predictions/WizardStepper.svelte';
	import SubmitSummary from '$components/predictions/SubmitSummary.svelte';
	import StatusBanner from '$components/predictions/StatusBanner.svelte';
	import BottomActionBar from '$components/predictions/BottomActionBar.svelte';
	import SmartFillModal from '$components/predictions/SmartFillModal.svelte';
	import PrintPreviewModal from '$components/predictions/PrintPreviewModal.svelte';
	import StandingsPanel from '$components/predictions/StandingsPanel.svelte';
	import { standingsPanelOpen } from '$stores/uiPreferences';
	import { wizardSectionLabel } from '$stores/wizardCrumb';
	import { smartFillScoreline, smartFillBracket } from '$lib/utils/smartFill';
	import {
		bonusBorderClass as bonusBorderClassFn,
		countAnsweredQuestions,
		filterTeamsInTopN,
		filterTeamsOutsideTopN,
		validateBonusAnswer
	} from '$lib/utils/bonusLogic';
	import { getOdds, getCacheInfo } from '$lib/utils/oddsCache';
	import { oddsScoreline } from '$lib/utils/oddsScoreline';
	import { tick } from 'svelte';

	// returnTo round-trip (R7): if an unauth user lands on this deep-link
	// URL (e.g. from the submission-confirmation email), preserve the path
	// through /login → magic-link → /auth/callback so they end up here
	// instead of the dashboard.
	$: if (!$isAuthenticated) {
		const returnTo = $page.url.pathname + $page.url.search;
		goto(`/login?returnTo=${encodeURIComponent(returnTo)}`);
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

	// Wizard step — Groups → Knockout → Bonus → Submit. `activeSection`
	// is the legacy variable name; kept identical so all downstream code
	// (which references `activeSection === 'groups'` etc.) doesn't churn.
	// The new `'submit'` step is wired into the same control flow below.
	type Step = 'groups' | 'knockout' | 'bonus' | 'submit';
	// Kept as `Section` alias for in-file readability where the variable
	// still semantically means "section of the page being shown".
	type Section = Step;
	let activeSection: Section = 'groups';
	// Visited-set: tracks which steps the user has navigated to. The
	// wizard stepper consults this to decide whether a step is "locked"
	// (not yet reachable) vs "visited but incomplete" (warning ring).
	// Visiting a step is idempotent; we never remove from the set.
	let visitedSteps: Set<Step> = new Set(['groups']);
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
		if ($page.url.searchParams.get('print') === '1') {
			printPreviewOpen = true;
		}
	});

	// Sync the active entry with the URL param. The entries store is
	// hydrated by routes/entries/+layout.ts before this page mounts, but
	// we still guard against an empty store (e.g. dev HMR) and against
	// URLs that point at an entry the user doesn't own — the latter
	// redirects silently to the list.
	$: entryParam = $page.params.entryId;

	// Always re-fetch the entries list on entry-detail mount before
	// activating the URL's entry. A stale `$entries` store can still
	// contain an entry the admin disabled in another tab — without this
	// refresh, the entry-match block below would happily accept the stale
	// row and render the wizard. After re-fetch the backend filter
	// (v2.154.2) drops disabled entries, so a since-disabled URL falls
	// through to the redirect. Also closes the saved-deep-link case
	// (e.g. clicking a submission-confirmation email link after admin
	// has disabled the entry).
	let refreshStarted = false;
	let refreshDone = false;
	$: if ($isAuthenticated && $user?.id && !refreshStarted) {
		refreshStarted = true;
		void (async () => {
			if ($entries.length === 0) {
				await loadEntries($user!.id);
			} else {
				await refreshEntries();
			}
			refreshDone = true;
		})();
	}

	// Gated on `refreshDone` so we never activate a stale entry id.
	// Without the gate this block would fire against the pre-refresh
	// store and briefly start the predictions fetch for a disabled
	// entry (which the backend 403s but only after a visible flash).
	$: if (refreshDone && entryParam) {
		if ($entries.some((e) => e.id === entryParam)) {
			if ($activeEntryId !== entryParam) setActiveEntry(entryParam);
		} else {
			void goto('/entries', { replaceState: true });
		}
	}

	// Re-fetch predictions whenever the active entry changes.
	let lastActiveEntryId: string | null = null;
	$: if ($isAuthenticated && $activeEntryId && $activeEntryId !== lastActiveEntryId) {
		const prev = lastActiveEntryId;
		lastActiveEntryId = $activeEntryId;
		resetPredictions();
		if (prev && $user) {
			teardownPersistence($user.id, prev);
			unregisterTabPresence($user.id, prev);
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
		registerTabPresence($user.id, $activeEntryId);
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
	// handleEntryCreate was removed when SheetSelector was lifted out of the
	// wizard hero. Entry creation now happens elsewhere (the /entries list
	// page or a future re-introduced dropdown). handleEntryRename and
	// handleEntryDuplicate below remain pending a janitor pass — they were
	// wired to the legacy EntrySelector (still imported but unused).

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
			const { setActiveEntry } = await import('$stores/entries');
			setActiveEntry(created.id);
		} catch (e) {
			console.error('Duplicate failed', e);
		}
	}

	// ---- Entry-lifecycle handlers (Mark Ready / Submit / Reopen / Withdraw)
	let lifecycleBusy: false | 'submit' | 'edit' = false;

	// ---- Error modals (replace the old inline `lifecycleError` string) ----
	// All save / lifecycle failures route through `routeSaveError`, which
	// either opens the LifecycleConflictModal (HTTP 409 with "is in status"
	// — entry was submitted in another tab) or the generic ErrorModal.
	let errorModalOpen = false;
	let errorModalTitle = "Couldn't save your edits";
	let errorModalMessage = '';
	let errorModalDetails: string | null = null;
	let lifecycleConflictOpen = false;
	let lifecycleConflictStatus = 'SUBMITTED';
	let lifecycleConflictCanReopen = true;
	// Captured at the moment of conflict so the LifecycleConflictModal's
	// Reopen action can re-run the same save after editEntry succeeds.
	let pendingRetry: (() => Promise<unknown>) | null = null;

	function routeSaveError(e: unknown, retry?: () => Promise<unknown>): void {
		const isLifecycle =
			e instanceof ApiResponseError &&
			e.status === 409 &&
			typeof e.detail === 'string' &&
			e.detail.includes('is in status');
		if (isLifecycle) {
			const phaseRow = $activeEntry?.phases?.find((p) => p.phase === currentPhaseEnum);
			lifecycleConflictStatus = phaseRow?.status ?? 'SUBMITTED';
			lifecycleConflictCanReopen = !!(
				$activeEntry && canEdit($activeEntry, currentPhaseEnum, $phase1Deadline ?? null)
			);
			pendingRetry = retry ?? null;
			lifecycleConflictOpen = true;
			return;
		}
		errorModalTitle = "Couldn't save your edits";
		errorModalMessage =
			e instanceof Error ? e.message : 'Save failed for an unknown reason.';
		errorModalDetails =
			e instanceof ApiResponseError ? `HTTP ${e.status} — ${e.detail}` : null;
		errorModalOpen = true;
	}

	async function handleLifecycleDiscard(): Promise<void> {
		lifecycleConflictOpen = false;
		pendingRetry = null;
		// Drop in-memory unsaved state; resetPredictions clears every
		// unsaved store, which makes the persistence subscriber write an
		// empty envelope and effectively wipe this tab's sessionStorage
		// draft for the active entry.
		resetPredictions();
		await refreshEntries();
	}

	async function handleLifecycleReopen(): Promise<void> {
		const current = $activeEntry;
		if (!current) {
			lifecycleConflictOpen = false;
			pendingRetry = null;
			return;
		}
		const retry = pendingRetry;
		try {
			await entriesApi.editEntry(current.id);
			await refreshEntries();
			lifecycleConflictOpen = false;
			pendingRetry = null;
			if (retry) await retry();
		} catch (e) {
			// Swallow no-op transition (entry already in DRAFT — race with
			// another tab/device that already reopened it). The user's
			// intent is satisfied; refresh, continue the retry chain, and
			// exit silently. Tweak 4b in plan file. The retry callback is
			// usually `confirmEdit`, which has its own draft→draft swallow,
			// so the chain naturally self-resolves.
			if (
				e instanceof ApiResponseError &&
				e.status === 409 &&
				typeof e.detail === 'string' &&
				e.detail.includes('Transition draft → draft')
			) {
				await refreshEntries();
				lifecycleConflictOpen = false;
				const r = pendingRetry;
				pendingRetry = null;
				if (r) await r();
				return;
			}
			lifecycleConflictOpen = false;
			pendingRetry = null;
			routeSaveError(e);
		}
	}

	function handleLifecycleCancel(): void {
		lifecycleConflictOpen = false;
		pendingRetry = null;
	}

	function handleErrorDismiss(): void {
		errorModalOpen = false;
	}

	// ---- CompletenessModal — fires from handleContinueStep when a
	// section is (or whose dependent section has become) incomplete.
	let completenessOpen = false;
	let completenessTitle = 'Section is incomplete';
	let completenessMissing: string[] = [];
	let completenessGoToLabel = 'Go fix it';
	let completenessGoToTarget: Section | null = null;

	function openCompletenessModal(opts: {
		title: string;
		missing: string[];
		goToLabel: string;
		goToTarget: Section | null;
	}): void {
		completenessTitle = opts.title;
		completenessMissing = opts.missing;
		completenessGoToLabel = opts.goToLabel;
		completenessGoToTarget = opts.goToTarget;
		completenessOpen = true;
	}

	function handleCompletenessGoTo(): void {
		completenessOpen = false;
		if (completenessGoToTarget) setStep(completenessGoToTarget);
	}

	function handleCompletenessCancel(): void {
		completenessOpen = false;
	}

	// ---- Same-browser tab-presence warning ----------------------------
	// `otherTabCount` is a readable store wired in onMount/onDestroy via
	// register/unregisterTabPresence. When >0, a soft banner appears and
	// every save action runs through `confirmMultiTabIfNeeded()` which
	// resolves the promise via the modal's button clicks. Same-browser
	// only — cross-device collisions stay in LifecycleConflictModal's lane.
	let multiTabConfirmOpen = false;
	let multiTabConfirmResolve: ((value: boolean) => void) | null = null;
	let multiTabBannerDismissed = false;
	let lastSeenTabCount = 0;
	// Reset the banner-dismissed flag whenever the count changes — a new
	// tab joining (or one leaving) is fresh information worth re-surfacing.
	$: if ($otherTabCount !== lastSeenTabCount) {
		multiTabBannerDismissed = false;
		lastSeenTabCount = $otherTabCount;
	}

	function confirmMultiTabIfNeeded(): Promise<boolean> {
		if ($otherTabCount === 0) return Promise.resolve(true);
		return new Promise<boolean>((resolve) => {
			multiTabConfirmResolve = resolve;
			multiTabConfirmOpen = true;
		});
	}

	function handleMultiTabConfirm(): void {
		multiTabConfirmOpen = false;
		multiTabConfirmResolve?.(true);
		multiTabConfirmResolve = null;
	}

	function handleMultiTabCancel(): void {
		multiTabConfirmOpen = false;
		multiTabConfirmResolve?.(false);
		multiTabConfirmResolve = null;
	}

	function dismissMultiTabBanner(): void {
		multiTabBannerDismissed = true;
	}

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
	// Discard modal = "Discard unsaved changes" from BottomActionBar.
	// Submit modal is now the dual-mode PrintPreviewModal (see plan R3);
	// `lockModalOpen` was retired in round 2. `unlockModalOpen` still drives
	// the revert-to-draft ConfirmModal.
	let unlockModalOpen = false;
	let discardModalOpen = false;

	function openDiscardDialog() {
		discardModalOpen = true;
	}

	async function confirmDiscard() {
		discardModalOpen = false;
		// Revert in-memory unsaved state and re-fetch the server snapshot
		// so the user is reset to exactly what's persisted.
		resetPredictions();
		const tasks: Promise<unknown>[] = [
			fetchMatchPredictions(),
			fetchBracketPredictions()
		];
		if ($isPhase2Active) tasks.push(fetchPhase2BracketPredictions());
		try {
			await Promise.all(tasks);
		} catch (e) {
			console.error('Discard refetch failed', e);
		}
	}

	// Multiple GroupAccordions can be open simultaneously. Opening a
	// group also pushes `activeGroupPill` to the right-hand StandingsPanel
	// so the panel mirrors the user's most-recent editing focus.
	//
	// State model: track *user collapses* (the rare action) rather than
	// *user expansions* (the default state). `userCollapses` starts empty
	// → everything is expanded by default, no async init needed. Derived
	// `openGroups` keeps the existing `.has(letter)` consumer API stable.
	let userCollapses: Set<string> = new Set();
	function toggleGroupAccordion(letter: string): void {
		if (userCollapses.has(letter)) {
			// Was collapsed; expand now.
			userCollapses.delete(letter);
			activeGroupPill = letter;
		} else {
			// Was expanded; collapse now.
			userCollapses.add(letter);
		}
		userCollapses = userCollapses; // trigger reactivity
	}

	// Expand-all toggle. When every group + thirdplace is open we treat
	// it as the "overview" mode, which switches the right-hand
	// StandingsPanel into its 'all' branch (a vertical stack of every
	// group's standings + the third-place table at the bottom) and opens
	// the drawer at narrow viewports.
	$: allGroupKeys = [
		...$groupFixtures.filter((g) => g.group !== 'thirdplace').map((g) => g.group),
		'thirdplace'
	];
	// Derived openGroups: a key is open iff the user hasn't collapsed it.
	// Reading-side API stays a Set (consumers do `.has(letter)`); writing
	// happens via toggleGroupAccordion / toggleExpandAll mutating userCollapses.
	$: openGroups = new Set(allGroupKeys.filter((k) => !userCollapses.has(k)));
	$: allExpanded = allGroupKeys.length > 0 && userCollapses.size === 0;

	function toggleExpandAll(): void {
		if (allExpanded) {
			// Collapse all — mark every key as user-collapsed.
			userCollapses = new Set(allGroupKeys);
			activeGroupPill = $groupFixtures[0]?.group ?? 'A';
			standingsPanelOpen.set(false);
		} else {
			// Expand all — clear every user collapse.
			userCollapses = new Set();
			activeGroupPill = 'all';
			standingsPanelOpen.set(true);
		}
	}

	// Mobile/tablet standings-drawer helpers. The drawer is rendered
	// alongside the desktop docked panel (different responsive visibility
	// classes); both gated on the same `standingsPanelOpen` store.
	function openStandingsForGroup(letter: string): void {
		activeGroupPill = letter;
		standingsPanelOpen.set(true);
	}
	function closeStandingsDrawer(): void {
		standingsPanelOpen.set(false);
	}

	// Shared UI-status for the active sheet — used by ProgressSection
	// (fill color) and StatusBanner (variant).
	$: uiStatus = ((): 'draft' | 'locked' | 'scored' | 'missed' => {
		if (!$activeEntry) return 'draft';
		const s = computeDisplayStatus($activeEntry, 'phase_1');
		if (s === 'withdrawn') return 'missed';
		if (s === 'submitted') return $isPhase1Locked ? 'scored' : 'locked';
		return $isPhase1Locked ? 'missed' : 'draft';
	})();

	// Phase 1 is read-only in three states: submitted-pre-deadline ('locked',
	// reversible via the Edit affordance), submitted-post-deadline ('scored',
	// permanent), and missed-the-deadline ('missed', permanent). Only 'draft'
	// stays editable. Used to gate KnockoutBracket and the bonus inputs;
	// groups already gate via isPhaseEditable($activeEntry, 'phase_1').
	$: phase1ReadOnly = uiStatus !== 'draft';

	// Smart Fill modal state.
	let smartFillModalOpen = false;
	let printPreviewOpen = false;

	// Betting Odds support — see frontend/src/lib/utils/oddsCache.ts.
	// Lazy-fetched on first modal open so users who never use Smart Fill
	// don't pay the network cost. oddsCacheInfo===null means "not yet
	// attempted"; the reactive block below kicks the fetch when needed.
	let oddsAvailable = false;
	let oddsCacheInfo: { fetchedAt: string; matchCount: number; remaining: number } | null = null;

	$: if (smartFillModalOpen && oddsCacheInfo === null) {
		void getOdds().then((cache) => {
			if (cache) {
				oddsCacheInfo = getCacheInfo(cache);
				oddsAvailable = true;
			} else {
				oddsAvailable = false; // key unset, network failure, etc.
			}
		});
	}
	// submissionMeta drives the receipt-style header in the recap (R6).
	// `status` reflects the entry-level Phase 1 lens (matches the wizard's
	// own UX surface). `statusAt` is the most relevant timestamp —
	// submitted_at from the Phase 1 row when SUBMITTED, otherwise the
	// entry's updated_at (last save).
	$: submissionMeta = $activeEntry
		? (() => {
				const status = computeDisplayStatus($activeEntry, 'phase_1');
				const phase1 = $activeEntry.phases.find((p) => p.phase === 'phase_1');
				const statusAt =
					status === 'submitted'
						? phase1?.submitted_at ?? $activeEntry.updated_at
						: $activeEntry.updated_at;
				return { status, statusAt };
			})()
		: null;
	$: smartFillBlanksOnly = $groupFixtures
		.flatMap((g) => g.fixtures)
		.filter((f) => !f.is_locked && fixturePrediction(f.id) === null);
	$: smartFillExisting = $groupFixtures
		.flatMap((g) => g.fixtures)
		.filter((f) => !f.is_locked && fixturePrediction(f.id) !== null);

	/**
	 * Run Smart Fill on the current sheet with the checkbox payload from
	 * SmartFillModal.
	 *
	 * - opts.overwrite      → re-fills fixtures that already have a pick
	 * - opts.fillBlanks     → fills fixtures with no current pick
	 * - opts.fillBracket    → after the scoreline pass, recomputes
	 *                         standings and walks the knockout bracket
	 *                         picking the higher-ranked team in each
	 *                         match. Only runs when its enable-gate is
	 *                         satisfied at modal apply time.
	 *
	 * Per-(user, fixture) seeded so the same user gets the same picks on
	 * repeated runs, but different users diverge on tier-edge and
	 * tied matchups.
	 */
	async function runSmartFill(opts: {
		overwrite: boolean;
		fillBlanks: boolean;
		fillBracket: boolean;
		method: 'fifa' | 'odds';
	}): Promise<void> {
		// Telemetry: capture what the user picked before anything else.
		// Fire-and-forget — no await; analytics never blocks UI work.
		// alsoServer: critical conversion event — ad-block-resistant.
		void track('smartfill_applied', opts, { alsoServer: true });
		smartFillModalOpen = false;
		const user = $user;
		if (!user || !$activeEntry) return;

		// 1. Scoreline fill — collect the union of fixtures to touch.
		const targets: typeof smartFillBlanksOnly = [];
		if (opts.fillBlanks) targets.push(...smartFillBlanksOnly);
		if (opts.overwrite) targets.push(...smartFillExisting);

		if (opts.method === 'odds') {
			// Defensive: the modal's Odds radio is disabled when the cache
			// isn't loaded, so this should never be null at this point.
			const cache = await getOdds();
			if (!cache) return;
			for (const f of targets) {
				const result = await oddsScoreline(
					f.home_team,
					f.away_team,
					f.id,
					cache.matches,
					cache.fetchedAt
				);
				if (result) updateLocalPrediction(f.id, result[0], result[1]);
				// Fixtures without matching odds stay blank — silently skipped.
			}
		} else {
			for (const f of targets) {
				const [h, a] = smartFillScoreline(f.home_team, f.away_team, user.id, f.id);
				updateLocalPrediction(f.id, h, a);
			}
		}

		// 2. Bracket fill — only after a tick so standingsMap reactively
		//    recomputes from the just-written predictions. Bracket fill
		//    ALWAYS uses FIFA rankings, regardless of method: odds cover
		//    scorelines only, not knockout permutations.
		if (opts.fillBracket) {
			await tick();
			const bracket = smartFillBracket(standingsMap, user.id);
			unsavedBracketPrediction.set(bracket);
		}
	}

	// Submit flow: SubmitSummary hosts the disclaimer + paid_to + checkbox
	// + Submit button inline (see plan R9). Its `submit` event fires with
	// the trimmed paid_to value, which we persist to the user then submit.
	// The BottomActionBar's Submit button (page-bottom action bar) is a
	// secondary CTA on the Submit step — it scrolls the user up into the
	// inline form rather than bypassing the consent UI.
	function scrollToInlineSubmit(): void {
		const el = document.querySelector('#submit-paid-to');
		if (el && 'scrollIntoView' in el) {
			(el as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' });
			(el as HTMLInputElement).focus();
		}
	}

	// Aggregated missing-list across all three sections. Used by Submit's
	// pre-flight CompletenessModal so the user sees everything they need
	// to fix in one place — not "fix this, click again, fix that."
	function buildAllMissing(): {
		items: string[];
		firstSection: Section | null;
	} {
		const groupsMissing = buildMissingForSection('groups');
		const knockoutMissing = buildMissingForSection('knockout');
		const bonusMissing = buildMissingForSection('bonus');
		const items: string[] = [];
		if (groupsMissing.length > 0) {
			items.push(...groupsMissing.map((m) => `Groups — ${m}`));
		}
		if (knockoutMissing.length > 0) {
			items.push(...knockoutMissing.map((m) => `Knockout — ${m}`));
		}
		if (bonusMissing.length > 0) {
			items.push(...bonusMissing.map((m) => `Bonus — ${m}`));
		}
		const firstSection: Section | null =
			groupsMissing.length > 0
				? 'groups'
				: knockoutMissing.length > 0
					? 'knockout'
					: bonusMissing.length > 0
						? 'bonus'
						: null;
		return { items, firstSection };
	}

	async function confirmSubmit(paidTo: string): Promise<void> {
		const current = $activeEntry;
		if (!current) return;
		lifecycleBusy = 'submit';
		try {
			// 1. Auto-save first so any pending edits are persisted before
			//    we either bail on validation or commit the submit. If save
			//    fails, handleSaveAll's catch opens ErrorModal /
			//    LifecycleConflictModal via routeSaveError; we just abort.
			const saved = await handleSaveAll();
			if (!saved) return;

			// 2. Validate completeness across ALL sections — Groups +
			//    Knockout + Bonus. Catches the "user damaged a previously
			//    complete bracket and clicked Submit anyway" case + any
			//    stale state. The SubmitSummary button is already gated by
			//    `phase1AllComplete`, but this is defense in depth and
			//    surfaces a precise missing-list to the user.
			const { items, firstSection } = buildAllMissing();
			if (items.length > 0) {
				openCompletenessModal({
					title: "You're not ready to submit yet",
					missing: items,
					goToLabel: firstSection
						? `Go to ${firstSection.charAt(0).toUpperCase()}${firstSection.slice(1)}`
						: 'OK',
					goToTarget: firstSection
				});
				return;
			}

			// 3. Persist paid_to on the user first so the backend gate
			//    (entries_service.submit_entry) sees it.
			if (paidTo && paidTo !== ($user?.paid_to ?? '')) {
				const updated = await updateProfile({ paid_to: paidTo });
				user.set(updated);
			}

			// 4. Submit. routeSaveError handles HTTP 409 (already
			//    submitted in another tab) → LifecycleConflictModal.
			await entriesApi.submitEntry(current.id);
			await refreshEntries();
		} catch (e) {
			routeSaveError(e, () => confirmSubmit(paidTo));
		} finally {
			lifecycleBusy = false;
		}
	}

	function handleEdit(): void {
		if (!$activeEntry) return;
		unlockModalOpen = true;
	}

	async function confirmEdit(): Promise<void> {
		const current = $activeEntry;
		if (!current) return;
		// Set lifecycleBusy BEFORE closing the modal so the ConfirmModal's
		// `disabled={lifecycleBusy === 'edit'}` prop kicks in before the
		// user's next click can land. Modal closes in finally — either
		// after editEntry succeeds, or after the swallow-on-409 returns,
		// or after a real error has been routed.
		lifecycleBusy = 'edit';
		try {
			await entriesApi.editEntry(current.id);
			await refreshEntries();
		} catch (e) {
			// No-op transition: server says the entry is already in the
			// desired (DRAFT) state. The user clicked Unlock and the entry
			// IS unlocked — refresh and exit silently. Tweak 4b in
			// stay-in-plan-mode-dynamic-adleman.md. Specific substring
			// match — only the backend transition formatter generates
			// "Transition X → Y is not allowed", and DRAFT → DRAFT is its
			// unique no-op case.
			if (
				e instanceof ApiResponseError &&
				e.status === 409 &&
				typeof e.detail === 'string' &&
				e.detail.includes('Transition draft → draft')
			) {
				await refreshEntries();
				return;
			}
			routeSaveError(e, () => confirmEdit());
		} finally {
			lifecycleBusy = false;
			unlockModalOpen = false;
		}
	}

	/**
	 * Create a new entry from the locked-state CTA on the submission card.
	 *
	 * Routes through the entries-list page's new-entry modal so the user
	 * has an explicit naming + cancel opportunity (Tweak 2c in
	 * stay-in-plan-mode-dynamic-adleman.md). The principle "no
	 * intermediate stop at /entries [after Create]" is preserved — the
	 * modal's Create button (handleCreate in entries/+page.svelte, see
	 * Tweak 2a) navigates straight to the new entry's wizard. /entries
	 * only "sticks" if the user explicitly clicks Cancel in the modal,
	 * at which point staying on the list with a fresh status is the
	 * correct destination.
	 *
	 * Gated by `canCreateNewEntry` in the parent's prop so the CTA only
	 * renders when there's room under `max_entries_per_user`.
	 */
	async function handleNewEntry(): Promise<void> {
		if (!$user) return;
		// Refresh so the list (the Cancel destination) reflects the
		// just-submitted entry's status when the user lands there.
		await refreshEntries();
		await goto('/entries?new=1');
	}

	// Compute whether the user has room to create another entry under the
	// competition's max_entries_per_user cap. Used to gate the "+ New Entry"
	// CTA on the SubmitSummary locked card. Defaults to false until both
	// editableEntries and entrySettings have loaded.
	$: canCreateNewEntry =
		!!$entrySettings &&
		$editableEntries.length < $entrySettings.max_entries_per_user;

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		}
		// Clear the breadcrumb section crumb so it doesn't persist to the
		// next route's topbar.
		wizardSectionLabel.set(null);
		// Drop this tab from the same-browser presence map for the
		// currently-active entry. tabPresence's own beforeunload handler
		// also runs, but onDestroy fires for SPA route changes (where
		// beforeunload would NOT fire) — both paths must clean up.
		if ($user && lastActiveEntryId) {
			unregisterTabPresence($user.id, lastActiveEntryId);
		}
	});

	// Default the active group pill to 'all' so the right-hand StandingsPanel
	// opens in the stacked-all-groups view, matching the default-expanded
	// accordion state (userCollapses starts empty). Per-group focus then
	// happens only when the user clicks into a specific group.
	$: if (!activeGroupPill && $groupFixtures.length > 0) {
		activeGroupPill = 'all';
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
		// Escape closes the standings drawer whenever it's open — separate
		// from the arrow-key handling because we want Esc to work even
		// when the user is in another section / typing.
		if (e.key === 'Escape' && $standingsPanelOpen) {
			closeStandingsDrawer();
			return;
		}
		// Only steal arrow keys when the user isn't editing a score.
		if (activeSection !== 'groups') return;
		if (isTypingInInput(e.target)) return;
		if (e.key === 'ArrowLeft') { e.preventDefault(); stepGroup(-1); }
		else if (e.key === 'ArrowRight') { e.preventDefault(); stepGroup(1); }
	}

	// ---- Derived: focused-header info for the active selection -----------
	$: focusedInfo = (() => {
		if (activeGroupPill === 'all') {
			const completedGroups = $groupFixtures.filter((gg) => {
				if (gg.group === 'thirdplace') return false;
				const gpx = groupProgress(gg);
				return gpx.total > 0 && gpx.done === gpx.total;
			}).length;
			const totalGroups = $groupFixtures.filter((gg) => gg.group !== 'thirdplace').length;
			return {
				badge: 'ALL',
				title: 'ALL GROUPS',
				caption: 'Overview of every group',
				meta:
					totalGroups > 0
						? `${completedGroups} of ${totalGroups} groups complete`
						: ''
			};
		}
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

	// Counts of what's still missing across the three submit gates.
	// Used to compute canSubmit + a friendly tooltip for the disabled state.
	$: missingFixtureCount = (() => {
		let missing = 0;
		for (const g of $groupFixtures) {
			if (g.group === 'thirdplace') continue;
			const p = groupProgress(g);
			missing += p.total - p.done;
		}
		return missing;
	})();

	$: bracketIsComplete = (() => {
		const b = $unsavedBracketPrediction || $bracketPrediction;
		if (!b) return false;
		if (!b.winner || b.winner.length === 0) return false;
		if (!standingsMap || Object.keys(standingsMap).length === 0) return false;
		// Validate the WINNER CHAIN, not just team arrays. The prediction
		// shape only stores advancing teams; arrays can stay "full" with
		// stale teams from a previous bracket version after the user
		// changes an upstream pick (setMatchWinner's cascade only walks
		// one level). predictionToBracketState walks forward set-by-set
		// and only marks a match's winner when its homeTeam/awayTeam is
		// found in the next round's set — so broken chains show up as
		// matches with winner=null.
		try {
			const state = predictionToBracketState(b, standingsMap);
			// Every match except 103 (the third-place playoff — losers'
			// match, doesn't gate submission) must have a winner.
			return Object.values(state.matchResults)
				.filter((m) => m.matchNumber !== 103)
				.every((m) => typeof m.winner === 'string' && m.winner.length > 0);
		} catch {
			return false;
		}
	})();

	$: missingBracketPicks = bracketIsComplete ? 0 : 1; // boolean-ish; tooltip just says "bracket"

	$: missingBonusCount = (() => {
		// bonusQuestions.length is the canonical total. Count questions
		// that have no answer or an empty answer.
		let missing = 0;
		for (const q of bonusQuestions) {
			const a = bonusAnswers.get(q.id);
			if (!a || a.trim() === '') missing++;
		}
		return missing;
	})();

	$: phase1AllComplete =
		allGroupsComplete && bracketIsComplete && missingBonusCount === 0;

	// ── Wizard model ─────────────────────────────────────────────────────
	// Derived array fed to <WizardStepper>. Each step's `complete` flag
	// reuses an existing derivation above — no parallel state machine.
	// `locked` opens up once the user has visited the step (we never trap
	// them on a future step) OR the previous step is complete.
	const STEP_ORDER: Step[] = ['groups', 'knockout', 'bonus', 'submit'];

	$: wizardSteps = [
		{
			id: 'groups' as Step,
			label: 'Groups',
			complete: allGroupsComplete,
			locked: false,
			visited: visitedSteps.has('groups')
		},
		{
			id: 'knockout' as Step,
			label: 'Knockout',
			complete: bracketIsComplete,
			locked: !allGroupsComplete && !visitedSteps.has('knockout'),
			visited: visitedSteps.has('knockout')
		},
		{
			id: 'bonus' as Step,
			label: 'Bonus',
			complete: missingBonusCount === 0,
			// Bonus is independent of Groups and Knockout — users can
			// answer bonus questions at any time, before or after
			// touching the bracket.
			locked: false,
			visited: visitedSteps.has('bonus')
		},
		{
			id: 'submit' as Step,
			label: 'Submit',
			complete: uiStatus === 'locked' || uiStatus === 'scored',
			locked: !phase1AllComplete && !visitedSteps.has('submit'),
			visited: visitedSteps.has('submit')
		}
	];

	// Helpers for the BottomActionBar — current step's neighbours + label.
	$: currentStepIdx = STEP_ORDER.indexOf(activeSection);
	$: prevStepId = currentStepIdx > 0 ? STEP_ORDER[currentStepIdx - 1] : null;
	$: nextStepId = currentStepIdx >= 0 && currentStepIdx < STEP_ORDER.length - 1 ? STEP_ORDER[currentStepIdx + 1] : null;
	$: prevStepLabel = prevStepId ? wizardSteps.find((s) => s.id === prevStepId)?.label ?? '' : '';
	$: nextStepLabel = nextStepId ? wizardSteps.find((s) => s.id === nextStepId)?.label ?? '' : '';
	$: canContinue = (wizardSteps.find((s) => s.id === activeSection)?.complete ?? false);

	function setStep(step: Step) {
		// Locked-step jumps shouldn't reach here — the stepper guards them
		// — but defensively guard anyway in case some other caller invokes
		// setStep directly.
		const target = wizardSteps.find((s) => s.id === step);
		if (target?.locked) return;
		activeSection = step;
		visitedSteps = new Set([...visitedSteps, step]); // trigger reactivity
	}

	// Publish the active section's label to the layout breadcrumb. Reset on
	// destroy (below) so the crumb doesn't leak into other routes' chrome.
	$: wizardSectionLabel.set(wizardSteps.find((s) => s.id === activeSection)?.label ?? null);

	function handleStepNavigate(e: CustomEvent<{ step: string }>) {
		setStep(e.detail.step as Step);
	}
	function handleBackStep() {
		if (prevStepId) setStep(prevStepId);
	}
	function buildMissingForSection(section: Section): string[] {
		// Compose a focused missing-list for CompletenessModal based on
		// the section we're leaving. Each branch reuses existing reactives
		// to avoid drift from the wizardSteps[i].complete source of truth.
		switch (section) {
			case 'groups': {
				const out: string[] = [];
				if (missingFixtureCount > 0) {
					out.push(
						`${missingFixtureCount} fixture score${missingFixtureCount === 1 ? '' : 's'} unfilled`
					);
				}
				return out;
			}
			case 'knockout': {
				const b = $unsavedBracketPrediction || $bracketPrediction;
				if (!b) return ['Bracket has not been started yet'];
				if (!standingsMap || Object.keys(standingsMap).length === 0) {
					return ['Groups must be completed before the bracket can be validated'];
				}
				// Same approach as `bracketIsComplete` — count matches in
				// the reconstructed state that lack a winner. This catches
				// stale-team entries that the raw prediction arrays would
				// otherwise count as "filled."
				let state;
				try {
					state = predictionToBracketState(b, standingsMap);
				} catch {
					return ['Bracket has not been started yet'];
				}
				const missingIn = (matches: { matchNumber: number }[]) =>
					matches.filter((m) => !state.matchResults[m.matchNumber]?.winner).length;
				const r32 = missingIn(ROUND_OF_32);
				const r16 = missingIn(ROUND_OF_16);
				const qf = missingIn(QUARTER_FINALS);
				const sf = missingIn(SEMI_FINALS);
				const finMissing = missingIn([FINAL]);
				const out: string[] = [];
				if (r32 > 0)
					out.push(`Round of 32: ${r32} match${r32 === 1 ? '' : 'es'} need winners`);
				if (r16 > 0)
					out.push(`Round of 16: ${r16} match${r16 === 1 ? '' : 'es'} need winners`);
				if (qf > 0)
					out.push(`Quarter-finals: ${qf} match${qf === 1 ? '' : 'es'} need winners`);
				if (sf > 0)
					out.push(`Semi-finals: ${sf} match${sf === 1 ? '' : 'es'} need winners`);
				if (finMissing > 0) out.push('Final: winner not picked');
				if (!b.winner) out.push('Tournament winner not picked');
				return out;
			}
			case 'bonus': {
				if (missingBonusCount === 0) return [];
				return [
					`${missingBonusCount} bonus question${missingBonusCount === 1 ? '' : 's'} unanswered`
				];
			}
			default:
				return [];
		}
	}

	async function handleContinueStep(): Promise<void> {
		if (!nextStepId) return;

		// 1. Re-validate the section we're LEAVING. The Continue button
		//    is already gated by `canContinue`, so this is defense-in-depth
		//    for callers that bypass the button (keyboard / a11y).
		const current = wizardSteps.find((s) => s.id === activeSection);
		if (current && !current.complete) {
			const missing = buildMissingForSection(activeSection);
			openCompletenessModal({
				title: `${current.label} is incomplete`,
				missing: missing.length > 0 ? missing : ['Some entries are still missing.'],
				goToLabel: 'OK',
				goToTarget: null
			});
			return;
		}

		// 2. Cross-section bracket check on Bonus → Submit. Bonus's
		//    `complete` flag doesn't know about the bracket, so a user
		//    who damaged a completed bracket and walked back to Bonus
		//    would otherwise sail through to Submit.
		if (activeSection === 'bonus' && !bracketIsComplete) {
			openCompletenessModal({
				title: 'Knockout bracket is incomplete',
				missing: buildMissingForSection('knockout'),
				goToLabel: 'Go to Knockout',
				goToTarget: 'knockout'
			});
			return;
		}

		// 3. Auto-save before navigating. handleSaveAll handles its own
		//    error routing (ErrorModal / LifecycleConflictModal); we only
		//    navigate if it returned true.
		const ok = await handleSaveAll();
		if (!ok) return;

		// 4. Navigate.
		setStep(nextStepId);
	}

	$: incompleteSummary = (() => {
		if (phase1AllComplete) return null;
		const parts: string[] = [];
		if (missingFixtureCount > 0)
			parts.push(`${missingFixtureCount} fixture${missingFixtureCount === 1 ? '' : 's'}`);
		if (!bracketIsComplete) parts.push('bracket');
		if (missingBonusCount > 0)
			parts.push(`${missingBonusCount} bonus`);
		return parts.join(', ');
	})();

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

	// Typed-prediction helper for FixtureCard. Returns null when either
	// side is empty (no prediction at all); returns the numeric pair
	// when both home and away are set. Mirrors the truthy/falsy logic
	// the legacy `predictionState` reactive uses.
	$: fixturePrediction = (fixtureId: string): { home: number; away: number } | null => {
		const entry = scoreValueMap.get(fixtureId);
		if (!entry) return null;
		if (entry.home === '' || entry.away === '') return null;
		const h = parseInt(entry.home, 10);
		const a = parseInt(entry.away, 10);
		if (Number.isNaN(h) || Number.isNaN(a)) return null;
		return { home: h, away: a };
	};

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
		// Stored stage values are SINGULAR ("quarter_final", "semi_final"),
		// matching the backend's Fixture.stage and scoring keys. The plural
		// names live only on the BracketPrediction display fields.
		push('round_of_32', b.round_of_32);
		push('round_of_16', b.round_of_16);
		push('quarter_final', b.quarter_finals);
		push('semi_final', b.semi_finals);
		push('final', b.final);
		if (b.winner) out.push({ team: b.winner, stage: 'winner', group_position: null });
		return out;
	}

	let bracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	function handleBracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedBracketPrediction.set(event.detail);
	}
	// Empty-prediction sentinel for "Clear Brackets". Setting unsavedBracketPrediction
	// to an object with empty round arrays causes hasValidPrediction() inside the
	// bracket component to return false, falling through to initializeBracketState()
	// which renders every match with no winner → picked counter goes to 0.
	function makeEmptyBracket(): BracketPrediction {
		return {
			group_winners: {},
			round_of_32: [],
			round_of_16: [],
			quarter_finals: [],
			semi_finals: [],
			final: [],
			winner: ''
		};
	}
	function handleBracketClear() {
		unsavedBracketPrediction.set(makeEmptyBracket());
	}
	async function handleSaveBracket() {
		const b = $unsavedBracketPrediction;
		if (!b) return;
		if (!(await confirmMultiTabIfNeeded())) return;
		bracketSaveStatus = 'saving';
		try {
			await saveBracketPredictions(bracketToPredictions(b));
			bracketSaveStatus = 'saved';
			unsavedBracketPrediction.set(null);
			setTimeout(() => (bracketSaveStatus = 'idle'), 2000);
		} catch (e) {
			bracketSaveStatus = 'error';
			routeSaveError(e, () => handleSaveBracket());
		}
	}

	// ---- Phase 2 wiring ---------------------------------------------------
	let phase2BracketComponent: KnockoutBracket;
	let phase2BracketSaveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';
	$: phase2DisplayBracket = $unsavedPhase2BracketPrediction || $phase2BracketPrediction;
	function handlePhase2BracketUpdate(event: CustomEvent<BracketPrediction>) {
		unsavedPhase2BracketPrediction.set(event.detail);
	}
	function handlePhase2BracketClear() {
		unsavedPhase2BracketPrediction.set(makeEmptyBracket());
	}
	async function handleSavePhase2Bracket() {
		const b = $unsavedPhase2BracketPrediction;
		if (!b) return;
		if (!(await confirmMultiTabIfNeeded())) return;
		phase2BracketSaveStatus = 'saving';
		const preds = bracketToPredictions(b).filter((p) => p.stage !== 'round_of_32');
		try {
			await saveBracketPredictions(preds);
			phase2BracketSaveStatus = 'saved';
			unsavedPhase2BracketPrediction.set(null);
			setTimeout(() => (phase2BracketSaveStatus = 'idle'), 2000);
		} catch (e) {
			phase2BracketSaveStatus = 'error';
			routeSaveError(e, () => handleSavePhase2Bracket());
		}
	}

	// ---- Unified save -----------------------------------------------------
	// hasAnyUnsaved now covers matches + bracket + Phase 2 bracket + bonus.
	// All four save through the single handleSaveAll flow.
	$: hasAnyUnsaved =
		$hasUnsavedChanges ||
		$hasUnsavedBracketChanges ||
		$hasUnsavedPhase2BracketChanges ||
		hasUnsavedBonus;
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

	async function handleSaveAll(): Promise<boolean> {
		// Same-browser tab-presence gate. confirmSubmit reaches here via
		// its own save, so the gate covers Submit too without double-prompting.
		if (!(await confirmMultiTabIfNeeded())) return false;
		saveStatus = 'saving';

		try {
			// Matches (Phase 1 group-stage + any other locked-out edits).
			// saveAllPredictions returns true vacuously when unsavedChanges
			// is empty, so calling unconditionally is cheap and idempotent.
			await saveAllPredictions();

			// Phase 1 bracket. saveBracketPredictions takes the team-
			// advancement list shape. On success we clear the unsaved
			// store so the dirty flag re-derives to false.
			if ($unsavedBracketPrediction) {
				const b = $unsavedBracketPrediction;
				await saveBracketPredictions(bracketToPredictions(b));
				unsavedBracketPrediction.set(null);
			}

			// Phase 2 bracket (currently dormant; the conditional below
			// is dead code in v1 but keeps the unified save honest if
			// Phase 2 ever activates).
			if ($unsavedPhase2BracketPrediction) {
				const b = $unsavedPhase2BracketPrediction;
				const preds = bracketToPredictions(b).filter((p) => p.stage !== 'round_of_32');
				await saveBracketPredictions(preds);
				unsavedPhase2BracketPrediction.set(null);
			}

			// Bonus picks (entry-scoped). Skip silently if no active entry
			// (shouldn't happen on the predictions page but guarded for safety).
			if (hasUnsavedBonus) {
				const entryId = $activeEntryId;
				if (entryId) {
					const { saveBonusPredictions } = await import('$api/bonus');
					const preds = Array.from(bonusAnswers.entries()).map(([question_id, answer]) => ({
						question_id,
						answer
					}));
					const saved = await saveBonusPredictions(entryId, preds);
					const fresh = new Map<string, string>();
					for (const p of saved) fresh.set(p.question_id, p.answer);
					bonusAnswers = fresh;
					bonusInitial = new Map(fresh);
				}
			}

			saveStatus = 'saved';
			setTimeout(() => (saveStatus = 'idle'), 2000);
			return true;
		} catch (e) {
			// Semantics: the FIRST failure halts the rest of the save flow
			// and routes to a modal. Previously each phase ran regardless
			// and a boolean `ok` flag rolled up at the end. That meant a
			// lifecycle-locked save would still try the bracket (also
			// lifecycle-locked) and pile up errors — now we short-circuit
			// to one explicit recovery path.
			saveStatus = 'error';
			routeSaveError(e, () => handleSaveAll());
			return false;
		}
	}

	// ---- Bonus questions (real backend) ----------------------------------
	let bonusQuestions: import('$api/bonus').BonusQuestion[] = [];
	let bonusAnswers: Map<string, string> = new Map(); // question_id → answer
	let bonusInitial: Map<string, string> = new Map(); // for change tracking
	// FIFA top_n team list — sourced from /api/predictions/bonus/meta on
	// loadBonus(). Drives the dark_horse / flop dropdown filters; empty
	// until the meta call resolves, so dropdowns render with whatever
	// subset of allTeams is appropriate.
	let fifaTopTeams: string[] = [];
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
		const bonusApi = await import('$api/bonus');
		const entryId = $activeEntryId;
		// Questions are static — always loadable. Predictions are entry-scoped;
		// skip the fetch (and any error from a not-yet-resolved active entry).
		// Meta (top_n + fifa_top_teams) drives the dark_horse / flop dropdowns
		// and is fetched in parallel for one round-trip on wizard open.
		const [qs, meta] = await Promise.all([
			bonusApi.getBonusQuestions(),
			bonusApi.getBonusMeta()
		]);
		bonusQuestions = qs;
		fifaTopTeams = meta.fifa_top_teams;
		if (entryId) {
			try {
				const preds = await bonusApi.getMyBonusPredictions(entryId);
				// Drop any stored answer that no longer satisfies its
				// question's input_type filter — e.g. a 'Brazil' saved for
				// dark_horse when it was input_type:team, now invalid under
				// team_outside_top_n. Without this scrub, the select renders
				// blank but the counter still counts it (the 4-of-4 bug).
				// We pass an undefined allTeams here because $groupFixtures
				// may not have resolved yet — fifa-only validation is enough
				// to catch the headline bug.
				const byId = new Map<string, (typeof qs)[number]>(qs.map((q) => [q.id, q]));
				const map = new Map<string, string>();
				for (const p of preds) {
					const q = byId.get(p.question_id);
					if (!q) continue; // orphan (question removed from YAML)
					if (validateBonusAnswer(q, p.answer, meta.fifa_top_teams)) {
						map.set(p.question_id, p.answer);
					}
				}
				bonusAnswers = map;
				// Anchor `bonusInitial` to the cleaned set, NOT the raw
				// server response, so the dirty-detector doesn't
				// permanently mark the entry dirty just because the server
				// still holds a stale value. If the user picks a fresh
				// answer the change still registers vs. this baseline.
				bonusInitial = new Map(map);
			} catch (e) {
				// Predictions failed but questions still render — better UX
				// than blanking the whole bonus tab on a single-endpoint hiccup.
				console.warn('Failed to load bonus predictions', e);
			}
		}
	}

	async function handleSaveBonus() {
		const entryId = $activeEntryId;
		if (!entryId) return;
		bonusSaveStatus = 'saving';
		try {
			const { saveBonusPredictions } = await import('$api/bonus');
			const preds = Array.from(bonusAnswers.entries()).map(([question_id, answer]) => ({
				question_id,
				answer
			}));
			const saved = await saveBonusPredictions(entryId, preds);
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

	// Counter ignores answers tied to question IDs not currently served
	// by the API — guards against stale drafts. Reactive: recomputes
	// when bonusQuestions or bonusAnswers shifts.
	$: answeredCount = countAnsweredQuestions(
		bonusQuestions.map((q) => q.id),
		bonusAnswers
	);

	// Per-card red/green border. Wrapping the pure helper so the markup
	// can call it with just an id.
	function bonusBorderClass(id: string): string {
		return bonusBorderClassFn(Boolean(bonusAnswer(id)));
	}

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
		// Internal literal stays `top_flop`; display is the longer phrase.
		top_flop: 'Knockout Stage — Top / Flop',
		// Kept defensively in case awards questions are re-added; no
		// current YAML question uses this category.
		awards: 'Awards'
	};

	// Initial load: questions only (entry-agnostic). Predictions are
	// entry-scoped and reload via the reactive below when the active
	// entry changes.
	$: if ($isAuthenticated && bonusQuestions.length === 0) {
		loadBonus().catch(() => {});
	}

	// Reload bonus predictions whenever the active entry changes (and
	// after questions have loaded).
	let lastBonusEntryId: string | null = null;
	$: if ($isAuthenticated && $activeEntryId && $activeEntryId !== lastBonusEntryId && bonusQuestions.length > 0) {
		lastBonusEntryId = $activeEntryId;
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
	<title>{$activeEntry?.display_name ?? 'Entry'} - Predictor v2</title>
</svelte:head>

<!-- Group-selector arrow-key navigation. The handler self-guards on
     activeSection !== 'groups' and on typing-in-input, so it's a no-op
     for the knockout / bonus / Phase 2 sections and while editing scores. -->
<svelte:window on:keydown={handleSelectorKeydown} />

{#if $isAuthenticated}
	<!-- xl:pr makes room for the live-standings panel docked at the right
	     edge ≥1280px. Below that, the panel is hidden (drawer pattern is a
	     follow-up). -->
	<!-- pt-6 pb-40: extra bottom padding so the last accordion (Third
	     Place) — and its expanded body — can scroll above the fixed
	     BottomActionBar (which is ~120–140px tall on mobile when the
	     Save Draft / Submit buttons are showing). Without this the user
	     can scroll to Third Place but its tap zone sits behind the bar. -->
	<div class="container mx-auto mobile-padding pt-6 pb-40 {activeSection === 'groups' ? 'xl:pr-[26rem]' : ''}">
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

		{#if $otherTabCount > 0 && !multiTabBannerDismissed}
			<div class="alert alert-warning text-xs py-2 mb-4" transition:fade={{ duration: 400 }}>
				<div>
					<div class="font-semibold mb-0.5">
						⚠ Another tab in this browser is editing this entry
					</div>
					<p class="text-[11px] opacity-90">
						Saves will ask you to confirm so you don't accidentally overwrite
						the other tab's work. Same-browser detection only — won't notice a
						session on another device.
					</p>
				</div>
				<button
					class="btn btn-ghost btn-xs"
					on:click={dismissMultiTabBanner}
					aria-label="Dismiss tab warning"
				>
					×
				</button>
			</div>
		{/if}

		<!-- Hero. Top row = tabs (left) + doughnut (right corner) on every
		     viewport. Smart Fill drops to its own row below so the top row
		     stays compact even on 375px screens. The deadline countdown
		     lives in the global topbar — not here.
		     Padding: tighter on mobile (12px) than desktop (16px). -->
		<div class="stadium-card no-glow p-3 sm:p-4 mb-6 overflow-visible">
			<!-- TOP ROW: nav toggles on the left, doughnut on the right.
			     items-center so the tabs and doughnut share a baseline;
			     flex-wrap only kicks in if BOTH Phase I/II + section tabs
			     are wider than the viewport (Phase 2 case only). -->
			<div class="flex items-center justify-between gap-3 flex-wrap">
				<div class="flex items-center gap-2 sm:gap-3 flex-wrap flex-1 w-full min-w-0">
					{#if $isPhase2Active}
						<div class="tabs tabs-boxed bg-base-300/40">
							<button class="tab {activePhase === 'phase1' ? 'tab-active' : ''}" on:click={() => (activePhase = 'phase1')}>Phase I</button>
							<button class="tab {activePhase === 'phase2' ? 'tab-active' : ''}" on:click={() => (activePhase = 'phase2')}>Phase II</button>
						</div>
					{/if}
					{#if activePhase === 'phase1'}
						<!-- 4-step wizard: Groups → Knockout → Bonus → Submit.
						     Each step's complete/locked state is derived from
						     existing progress signals (allGroupsComplete,
						     bracketIsComplete, missingBonusCount, etc.) — see
						     the `wizardSteps` reactive block above. -->
						<div class="flex-1 min-w-[16rem] w-full">
							<WizardStepper
								steps={wizardSteps}
								activeStep={activeSection}
								on:navigate={handleStepNavigate}
							/>
						</div>
					{/if}
				</div>
			</div>

			<!-- Smart Fill + Print row. Smart Fill only on drafts. Print always
			     visible. Right-aligned under the Submit step pill on every
			     viewport — compact and content-width so they sit side-by-side
			     even at 375 px (no Print wrap, no full-width SmartFill).
			     SmartFill carries a soft-gold accent treatment so users
			     actually see it (Tweak 1 in stay-in-plan-mode-dynamic-adleman.md). -->
			<div class="mt-3 flex items-center justify-end gap-2 flex-wrap">
				{#if uiStatus === 'draft'}
					<div class="tooltip tooltip-bottom tooltip-wrap z-50" data-tip="Auto-fill blank picks using FIFA rankings or odds">
						<button
							type="button"
							class="px-3 rounded-lg border-2 border-primary bg-primary/20 hover:bg-primary/30 text-sm font-medium font-display text-primary min-h-10 transition-colors whitespace-nowrap shadow-glow-gold inline-flex items-center"
							on:click={() => {
								void track('smartfill_opened');
								smartFillModalOpen = true;
							}}
						>
							<svg class="w-3.5 h-3.5 -mt-0.5 mr-1 text-info" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
								<path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z"/>
							</svg>
							SmartFill
						</button>
					</div>
				{/if}
				<div class="tooltip tooltip-bottom tooltip-wrap z-50" data-tip="Open a printable summary of your predictions">
					<button
						type="button"
						class="btn btn-ghost btn-sm gap-1"
						on:click={() => (printPreviewOpen = true)}
					>
						🖨 Print
					</button>
				</div>
			</div>

			<!-- Entry name + READY/LOCKED badge + NO PRIZE chip removed from
			     the hero — entry name lives in the topbar breadcrumb (desktop)
			     and the mobile navbar-center, status is conveyed by the
			     doughnut + BottomActionBar, and NO PRIZE is also rendered in
			     the SheetSelector dropdown rows. Save / lifecycle errors now
			     surface via ErrorModal / LifecycleConflictModal mounted at
			     the end of the page. -->

		</div>

		<!-- ============================== PHASE 1 ============================== -->
		{#if activePhase === 'phase1'}
			<!-- 12 group accordions (A-L). Expanded by default — `openGroups`
			     is derived as `allGroupKeys - userCollapses`, so the natural
			     empty initial state of userCollapses means everything is open
			     without any async init. User collapses persist via userCollapses. -->
			{#if activeSection === 'groups'}
				<!-- Status banner for locked / scored / missed sheets. Hidden on
				     editable drafts (returns nothing). Unlock button only when
				     deadline hasn't passed — wires into the existing Edit flow. -->
				<StatusBanner status={uiStatus} canUnlock={uiStatus === 'locked'} on:unlock={handleEdit} />

				<!-- Helper microcopy paired with the Expand/Collapse-all
				     toggle on the same row. On mobile they stack (helper
				     first, toggle below right-aligned); from sm+ they sit
				     side by side. items-start keeps the button anchored
				     to the top of the row when the helper wraps. -->
				<div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-4 mb-3">
					<p class="text-sm text-base-content/60 flex-1">
						Tap <strong>−/+</strong> to score each match. Or <strong>⚡ SmartFill</strong> to auto-fill, then tweak what you disagree with.
					</p>
					<div class="flex justify-end shrink-0">
						<button
							type="button"
							class="btn btn-ghost btn-xs gap-1"
							on:click={toggleExpandAll}
							aria-pressed={allExpanded}
						>
							<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								{#if allExpanded}
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 15l7-7 7 7" />
								{:else}
									<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
								{/if}
							</svg>
							{allExpanded ? 'Collapse all' : 'Expand all'}
						</button>
					</div>
				</div>

				<!-- Standings overview lives in the right-hand StandingsPanel
				     ('all' mode); the panel auto-opens as a drawer at narrow
				     viewports when Expand-all is clicked. No inline stack here. -->

				<div class="space-y-3 mb-6">
					{#each $groupFixtures.filter((g) => g.group !== 'thirdplace') as g (g.group)}
						{@const gp = groupProgress(g)}
						<GroupAccordion
							group={g}
							open={openGroups.has(g.group)}
							editable={$activeEntry !== null && isPhaseEditable($activeEntry, 'phase_1')}
							getPrediction={fixturePrediction}
							onScore={(fid, home, away) => updateLocalPrediction(fid, home, away)}
							onToggle={() => toggleGroupAccordion(g.group)}
							tieBreakNeeded={gp.total > 0 &&
								gp.done === gp.total &&
								groupStandingsWarnings.some((w) => w.group === g.group)}
							onOpenStandings={() => openStandingsForGroup(g.group)}
						/>
					{/each}
				</div>

				<!-- Third-place qualifying accordion. Mirrors the GroupAccordion
				     header chrome (clickable name + chip + chevron). The body
				     is lightweight (caption + small flag preview) because the
				     actual standings table lives in the StandingsPanel — same
				     pattern as the regular groups. Chip variants:
				       - tied → ⚠ Tie break needed (both viewports)
				       - not tied → View Table (mobile only via xl:hidden) -->
				{@const thirdPlaceTieBreakNeeded =
					allGroupsComplete && thirdPlaceWarnings.length > 0}
				<div class="group-accordion rounded-xl bg-base-200/30 overflow-hidden mb-6">
					<div class="flex items-center gap-3 w-full px-4 py-3 hover:bg-base-300/30 min-h-12">
						<button
							type="button"
							class="flex-1 flex items-center gap-3 min-w-0 text-left"
							on:click={() => toggleGroupAccordion('thirdplace')}
							aria-expanded={openGroups.has('thirdplace')}
							aria-controls="group-thirdplace-body"
						>
							<span class="font-display font-bold text-base sm:text-lg whitespace-nowrap">
								Third Place
							</span>
							<!-- Flag preview: top-4 currently-qualifying third-placed teams. -->
							<div class="hidden sm:flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
								{#each thirdPlaceStandings.slice(0, 4) as t (t.team)}
									{#if hasFlag(t.team)}
										<img
											src={getFlagUrl(t.team, 'sm')}
											alt=""
											class="w-5 h-auto rounded-sm flex-shrink-0"
											title={t.team} style="aspect-ratio: 4 / 3" />
									{/if}
								{/each}
							</div>
							<span class="flex-1 sm:hidden" aria-hidden="true"></span>
						</button>

						<!-- Standings-trigger chip — same pattern as GroupAccordion. -->
						{#if thirdPlaceTieBreakNeeded}
							<button
								type="button"
								class="badge badge-warning badge-sm gap-1 font-medium whitespace-nowrap hover:brightness-110 transition-[filter]"
								on:click={() => openStandingsForGroup('thirdplace')}
								title="View standings — third-place teams tied on points, GD, GF"
							>⚠ Tie break needed</button>
						{:else if thirdPlaceStandings.length > 0}
							<button
								type="button"
								class="badge badge-ghost badge-sm gap-1 font-medium whitespace-nowrap xl:hidden hover:brightness-110 transition-[filter]"
								on:click={() => openStandingsForGroup('thirdplace')}
								title="View third-place qualifying standings"
							>View Table</button>
						{/if}

						<button
							type="button"
							class="flex items-center gap-3"
							on:click={() => toggleGroupAccordion('thirdplace')}
							aria-label="Toggle Third Place"
							tabindex="-1"
						>
							<svg
								class="w-4 h-4 opacity-60 flex-shrink-0 transition-transform"
								class:rotate-180={openGroups.has('thirdplace')}
								viewBox="0 0 20 20"
								fill="currentColor"
								aria-hidden="true"
							>
								<path
									fill-rule="evenodd"
									d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
									clip-rule="evenodd"
								/>
							</svg>
						</button>
					</div>

					{#if openGroups.has('thirdplace')}
						<div
							id="group-thirdplace-body"
							transition:slide={{ duration: 200, easing: cubicOut }}
							class="px-4 pt-1 pb-3 text-sm text-base-content/70"
						>
							{#if thirdPlaceStandings.length === 0}
								<p>Fill in some group predictions to see third-place qualifying.</p>
							{:else}
								<!-- Live third-place qualifying table — mirrors the StandingsPanel
								     variant so the eye sees the same ranking in both surfaces.
								     Top-8 rows tinted success; positions 9-12 stay neutral. -->
								<div class="overflow-x-auto fixture-card rounded-xl border p-3">
									<table class="w-full text-xs">
										<thead class="text-base-content/40 uppercase tracking-wider">
											<tr>
												<th class="text-left font-normal pb-1 w-6">#</th>
												<th class="text-center font-normal pb-1 w-8">Grp</th>
												<th class="text-left font-normal pb-1">Team</th>
												<th class="text-center font-normal pb-1">P</th>
												<th class="text-center font-normal pb-1">W</th>
												<th class="text-center font-normal pb-1">D</th>
												<th class="text-center font-normal pb-1">L</th>
												<th class="text-center font-normal pb-1">GD</th>
												<th class="text-center font-normal pb-1">Pts</th>
											</tr>
										</thead>
										<tbody>
											{#each thirdPlaceStandings as t, i (t.team)}
												<tr class="border-t border-base-content/5 {i < 8 ? 'bg-success/5' : ''}">
													<td class="py-1">
														<span
															class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono {i < 8
																? 'bg-success/20 text-success'
																: 'bg-base-300/40 text-base-content/50'}">{i + 1}</span
														>
													</td>
													<td class="text-center text-[11px] font-mono py-1">{t.group}</td>
													<td class="py-1">
														<span class="flex items-center gap-1.5">
															{#if hasFlag(t.team)}
																<img
																	src={getFlagUrl(t.team, 'sm')}
																	alt=""
																	class="w-4 h-auto rounded-sm flex-shrink-0" style="aspect-ratio: 4 / 3" />
															{/if}
															<span class="truncate">{displayTeamName(t.team)}</span>
														</span>
													</td>
													<td class="text-center font-mono tabular-nums py-1">{t.played}</td>
													<td class="text-center font-mono tabular-nums py-1">{t.won}</td>
													<td class="text-center font-mono tabular-nums py-1">{t.drawn}</td>
													<td class="text-center font-mono tabular-nums py-1">{t.lost}</td>
													<td class="text-center font-mono tabular-nums py-1">
														<span
															class={t.goalDifference > 0
																? 'text-success'
																: t.goalDifference < 0
																	? 'text-error'
																	: 'opacity-60'}
															>{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}</span
														>
													</td>
													<td class="text-center font-mono tabular-nums font-bold py-1">{t.points}</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
								<p class="text-[10px] text-base-content/50 mt-2 uppercase tracking-wider">
									★ Top 8 third-placed teams qualify for the Round of 32 (FIFA 2026 format)
								</p>
							{/if}
						</div>
					{/if}
				</div>
			{:else if activeSection === 'knockout'}
				<!-- The wizard stepper prevents reaching this step until Groups
				     is complete (locked step). The legacy phase1BracketGated
				     panel + button has been removed; if the user revisits this
				     step after partially un-doing Groups, the bracket falls
				     back to initializeBracketState (empty matches). -->
				<KnockoutBracket
					bind:this={bracketComponent}
					prediction={displayBracket}
					groupStandings={standingsMap}
					locked={phase1ReadOnly}
					phase="phase_1"
					on:update={handleBracketUpdate}
					on:clear={handleBracketClear}
				/>
				<!-- Legacy "Save bracket" button removed — bracket edits now
				     flow through the unified Save Draft in BottomActionBar. -->
			{:else if activeSection === 'bonus'}
				{#if phase1ReadOnly}
					<!-- Locked cue — the selects below are disabled but otherwise
					     look active; mirror FixtureCard's read-only signalling so
					     nobody wonders why their taps do nothing. -->
					<div
						class="mt-4 flex items-center gap-2 rounded-btn border border-base-300/60 bg-base-300/20 px-3 py-2 text-[12.5px] text-base-content/70"
						role="status"
					>
						<span class="text-[13px]">🔒</span>
						Your bonus answers are locked — this is a read-only view of what you submitted.
					</div>
				{/if}
				{#each Object.entries(bonusByCategory) as [cat, qs] (cat)}
					{#if qs.length > 0}
						{@const catDone = qs.filter((q) => bonusAnswer(q.id)).length}
						<div class="flex items-center gap-2 mt-5 mb-3">
							<h2 class="text-lg font-display tracking-wide">{CATEGORY_LABEL[cat]} <span class="text-sm text-base-content/40">· {qs.length} question{qs.length === 1 ? '' : 's'}</span></h2>
							<span class="badge badge-sm {catDone === qs.length ? 'badge-success' : 'badge-ghost'}">{catDone}/{qs.length}</span>
						</div>
						<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
							{#each qs as bq (bq.id)}
								{@const answer = bonusAnswer(bq.id)}
								<!-- Card surface lifts above the panel: bg-base-200 →
								     white in hybrid (light), premium navy in
								     premium-night (dark). Dropdowns stay on bg-base-100
								     to give the requested two-tone contrast (canvas
								     dim slate vs. card white, or canvas midnight vs.
								     card navy). Border thickness signals state. -->
								<div class="rounded-xl border-2 bg-base-200 p-4 transition-colors {bonusBorderClass(bq.id)} {phase1ReadOnly ? 'opacity-75' : ''} relative">
									<div class="text-sm font-medium mb-2">{bq.label}</div>
									{#if bq.input_type === 'team'}
										<select class="select select-bordered select-sm w-full bg-base-100" value={answer} disabled={phase1ReadOnly} on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}>
											<option value="">— Select a team —</option>
											{#each allTeams as t (t)}<option value={t}>{t}</option>{/each}
										</select>
									{:else if bq.input_type === 'team_outside_top_n'}
										<!-- Dark Horse — every team NOT in the FIFA top_n list. -->
										<select class="select select-bordered select-sm w-full bg-base-100" value={answer} disabled={phase1ReadOnly} on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}>
											<option value="">— Select a team —</option>
											{#each filterTeamsOutsideTopN(allTeams, fifaTopTeams) as t (t)}<option value={t}>{t}</option>{/each}
										</select>
									{:else if bq.input_type === 'team_in_top_n'}
										<!-- Bottlers — only the FIFA top_n teams (intersected
										     with allTeams; preserves FIFA-rank order). -->
										<select class="select select-bordered select-sm w-full bg-base-100" value={answer} disabled={phase1ReadOnly} on:change={(e) => setBonusAnswer(bq.id, e.currentTarget.value)}>
											<option value="">— Select a team —</option>
											{#each filterTeamsInTopN(allTeams, fifaTopTeams) as t (t)}<option value={t}>{t}</option>{/each}
										</select>
									{:else}
										<input type="text" class="input input-bordered input-sm w-full bg-base-100" value={answer} disabled={phase1ReadOnly} on:input={(e) => setBonusAnswer(bq.id, e.currentTarget.value)} placeholder="Type a player name…" />
									{/if}
									<div class="text-xs text-accent mt-2">+{bq.points} pts</div>
								</div>
							{/each}
						</div>
					{/if}
				{/each}

				<div class="flex justify-end items-center gap-3 mt-4">
					<span class="text-xs text-base-content/50"
						>{answeredCount} of {bonusQuestions.length} answered{phase1ReadOnly
							? ''
							: ' · use Save Draft below to persist'}</span
					>
					<button class="btn btn-primary btn-sm hidden" on:click={handleSaveBonus} disabled={!hasUnsavedBonus || bonusSaveStatus === 'saving'}>
						{bonusSaveStatus === 'saving' ? 'Saving…' : bonusSaveStatus === 'saved' ? '✓ Saved' : bonusSaveStatus === 'error' ? '× Error — retry' : 'Save bonus picks'}
					</button>
				</div>
				<p class="text-xs text-base-content/50 mt-3 normal-case tracking-normal leading-relaxed">★ Admin will reveal correct answers as the tournament progresses. If multiple teams qualify — e.g. Germany and Spain both score 20 goals in the group stage — users who picked either team will get the bonus points.</p>
			{:else if activeSection === 'submit'}
				<!-- ============================ SUBMIT STEP ============================ -->
				<!-- Full read-only recap (groups + bracket + bonus) plus a state-aware
				     submission panel. The Submit / Unlock buttons live inside the
				     SubmitSummary component, NOT in BottomActionBar (which drops the
				     Submit button when activeStep is set). -->
				<SubmitSummary
					entryName={$activeEntry?.display_name ?? ''}
					entryRef={$activeEntry?.reference ?? ''}
					playerName={$user?.name ?? ''}
					groupFixtures={$groupFixtures.filter((g) => g.group !== 'thirdplace')}
					{scoreValueMap}
					{displayBracket}
					{bonusQuestions}
					{bonusAnswers}
					groupStandings={standingsMap}
					{submissionMeta}
					userPaidTo={$user?.paid_to ?? null}
					submitBusy={lifecycleBusy === 'submit'}
					status={uiStatus}
					canSubmit={phase1AllComplete}
					submittedAt={$activeEntry?.phases?.find((p) => p.phase === 'phase_1')?.submitted_at ?? null}
					canUnlock={uiStatus === 'locked' && !$isPhase1Locked}
					{canCreateNewEntry}
					on:editStep={(e) => setStep(e.detail.step)}
					on:submit={(e) => confirmSubmit(e.detail.paidTo)}
					on:unlock={handleEdit}
					on:newEntry={handleNewEntry}
				/>
			{/if}

			<!-- Phase I sticky save bar removed at Prompt 14 — superseded by
			     BottomActionBar at the page bottom. Bracket-specific save
			     still lives in the knockout section's own save button. -->
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
					on:clear={handlePhase2BracketClear}
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
									{#if hasFlag(f.home_team)}<img src={getFlagUrl(f.home_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" style="aspect-ratio: 4 / 3" />{/if}
									<span class="team-name">{teamCode(f.home_team)}</span>
								</div>
								<div class="flex items-center gap-1 shrink-0">
									<input type="number" class="score-input" min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'home')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'home', e.currentTarget.value); }} aria-label="{f.home_team} score" />
									<span class="text-base-content/40">–</span>
									<input type="number" class="score-input" min="0" max={MAX_GOALS} inputmode="numeric" disabled={f.is_locked} value={scoreValue(f.id, 'away')} on:input={(e) => { clampScoreInput(e.currentTarget); handleScoreInput(f.id, 'away', e.currentTarget.value); }} aria-label="{f.away_team} score" />
								</div>
								<div class="flex items-center gap-2 flex-1 min-w-0 justify-end" title={f.away_team}>
									<span class="team-name">{teamCode(f.away_team)}</span>
									{#if hasFlag(f.away_team)}<img src={getFlagUrl(f.away_team, 'sm')} alt="" class="w-6 h-auto rounded-sm" style="aspect-ratio: 4 / 3" />{/if}
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

		<!-- Sticky bottom action bar — state-driven CTA strip. Sits above
		     the layout's mobile bottom nav (pb-16). Gold-glows when there
		     are unsaved changes; the Save Draft label carries the count;
		     a Discard button (with confirmation) lets the user revert. -->
		<!-- Wizard-aware: activeStep + neighbour ids put the bar into wizard
		     mode (Back/Continue cluster). On the Submit step, Continue is
		     suppressed; on intermediate steps, Submit is suppressed (the
		     canonical Submit button lives in <SubmitSummary>). -->
		<BottomActionBar
			status={uiStatus}
			canSubmit={phase1AllComplete}
			incompleteSummary={incompleteSummary}
			hasUnsavedChanges={hasAnyUnsaved}
			unsavedCount={$unsavedChangesCount}
			savingDraft={saveStatus === 'saving'}
			activeStep={activeSection}
			prevStep={prevStepId}
			nextStep={nextStepId}
			{prevStepLabel}
			{nextStepLabel}
			{canContinue}
			on:saveDraft={handleSaveAll}
			on:submit={scrollToInlineSubmit}
			on:unlock={handleEdit}
			on:discard={openDiscardDialog}
			on:back={handleBackStep}
			on:continue={handleContinueStep}
		/>

		<!-- Submit modal is now the dual-mode PrintPreviewModal below (mode='submit').
		     The remaining ConfirmModal instances drive the smaller lifecycle
		     actions (revert, discard). -->

		<ConfirmModal
			open={unlockModalOpen}
			icon="✏️"
			title="Revert to draft?"
			message={$activeEntry
				? `"${$activeEntry.display_name}" goes back to draft. Your predictions stay as they are — you'll just need to tap Lock In again before the competition starts.`
				: ''}
			confirmLabel="Revert"
			confirmVariant="warning"
			disabled={lifecycleBusy === 'edit'}
			onConfirm={confirmEdit}
			onCancel={() => (unlockModalOpen = false)}
		/>

		<ConfirmModal
			open={discardModalOpen}
			icon="🗑️"
			title="Discard unsaved changes?"
			message={$unsavedChangesCount === 1
				? 'Your 1 unsaved prediction will be reverted to the last saved state. This cannot be undone.'
				: `Your ${$unsavedChangesCount} unsaved predictions will be reverted to the last saved state. This cannot be undone.`}
			confirmLabel="Discard"
			confirmVariant="warning"
			onConfirm={confirmDiscard}
			onCancel={() => (discardModalOpen = false)}
		/>

		<!-- Smart Fill modal — checkbox form (overwrite, fill blanks, fill
		     bracket). The fill-bracket checkbox is gated on having every
		     group fixture predicted (or selecting fill-blanks). -->
		<SmartFillModal
			open={smartFillModalOpen}
			existingCount={smartFillExisting.length}
			blankCount={smartFillBlanksOnly.length}
			bracketAlreadyFilled={bracketIsComplete}
			{oddsAvailable}
			{oddsCacheInfo}
			on:apply={(e) => runSmartFill(e.detail)}
			on:cancel={() => (smartFillModalOpen = false)}
		/>

		<!-- Read-only Print Preview modal. The submit flow lives inline in
		     SubmitSummary (see plan R9). -->
		<PrintPreviewModal
			open={printPreviewOpen}
			entryName={$activeEntry?.display_name ?? ''}
			entryRef={$activeEntry?.reference ?? ''}
			playerName={$user?.name ?? ''}
			groupFixtures={$groupFixtures.filter((g) => g.group !== 'thirdplace')}
			{scoreValueMap}
			displayBracket={displayBracket}
			{bonusQuestions}
			{bonusAnswers}
			groupStandings={standingsMap}
			{submissionMeta}
			onClose={() => (printPreviewOpen = false)}
		/>

		<!-- Error modals — driven by routeSaveError() from every save /
		     lifecycle catch block. ErrorModal handles generic failures;
		     LifecycleConflictModal handles HTTP 409 with "is in status"
		     (another tab submitted while this tab was editing). -->
		<ErrorModal
			open={errorModalOpen}
			title={errorModalTitle}
			message={errorModalMessage}
			details={errorModalDetails}
			onDismiss={handleErrorDismiss}
		/>

		<LifecycleConflictModal
			open={lifecycleConflictOpen}
			entryStatus={lifecycleConflictStatus}
			canReopen={lifecycleConflictCanReopen}
			onDiscard={handleLifecycleDiscard}
			onReopen={handleLifecycleReopen}
			onCancel={handleLifecycleCancel}
		/>

		<!-- CompletenessModal — fires from handleContinueStep when the
		     section we're leaving (or a section it depends on) is
		     incomplete. The Continue button is normally gated by
		     `canContinue`, so this is defense-in-depth + the
		     Bonus → Submit cross-section bracket check. -->
		<CompletenessModal
			open={completenessOpen}
			title={completenessTitle}
			missing={completenessMissing}
			goToLabel={completenessGoToLabel}
			onGoTo={handleCompletenessGoTo}
			onCancel={handleCompletenessCancel}
		/>

		<!-- Same-browser tab-presence confirmation. Fires before any
		     save when otherTabCount > 0. Cross-device collisions live
		     in LifecycleConflictModal's lane, not here. -->
		<MultiTabConfirmModal
			open={multiTabConfirmOpen}
			onConfirm={handleMultiTabConfirm}
			onCancel={handleMultiTabCancel}
		/>
	</div>

	<!-- Desktop docked panel — always visible at xl+ when in Groups section.
	     Decoupled from the mobile-drawer store so SSR's false default
	     does not hide it on first render. -->
	{#if activeSection === 'groups'}
		<aside class="hidden xl:flex flex-col fixed top-12 right-0 bottom-24 w-[26rem] z-20">
			<StandingsPanel
				activeGroup={activeGroupPill || 'A'}
				{activeSection}
				mode="split"
				{bonusQuestions}
				{bonusAnswers}
				{thirdPlaceStandings}
				{thirdPlaceWarnings}
				{allGroupsComplete}
			/>
		</aside>
	{/if}

	<!-- Mobile/tablet drawer overlay (<1280px). User-triggered via chip taps.
	     Also gated on groups section — pointless in knockout/bonus. -->
	{#if $standingsPanelOpen && activeSection === 'groups'}
		<div
			class="xl:hidden fixed inset-0 z-40"
			role="dialog"
			aria-modal="true"
			aria-label="Live standings"
			transition:fade={{ duration: 150 }}
		>
			<div
				class="absolute inset-0 bg-black/50 backdrop-blur-sm"
				on:click={closeStandingsDrawer}
				on:keydown={(e) => e.key === 'Enter' && closeStandingsDrawer()}
				role="button"
				tabindex="-1"
				aria-label="Close standings drawer"
			></div>
			<!-- Drawer panel. `top-16 bottom-0` clears the mobile navbar
			     (which is z-50 and would otherwise overlay the panel's
			     own header + Done button). The backdrop above stays
			     `inset-0` so page content behind it is dimmed; the
			     navbar stays bright above the backdrop (iOS-sheet
			     pattern). -->
			<div
				class="absolute top-16 bottom-36 right-0 w-full max-w-[24rem] bg-base-200 shadow-2xl flex flex-col"
				transition:fly={{ x: 400, duration: 250, easing: cubicOut }}
			>
				<StandingsPanel
					activeGroup={activeGroupPill || 'A'}
					{activeSection}
					mode="drawer"
					{bonusQuestions}
					{bonusAnswers}
					{thirdPlaceStandings}
					{thirdPlaceWarnings}
					{allGroupsComplete}
					on:close={closeStandingsDrawer}
				/>
			</div>
		</div>
	{/if}
{/if}

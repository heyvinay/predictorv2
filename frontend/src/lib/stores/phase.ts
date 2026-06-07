/**
 * Phase store for competition phase status.
 */

import { writable, derived, readable } from 'svelte/store';
import { browser } from '$app/environment';
import * as competitionApi from '$api/competition';
import type { PhaseStatus, UxPhase } from '$types';
import { fixtures } from '$stores/fixtures';

// Stores
export const phaseStatus = writable<PhaseStatus | null>(null);
export const phaseLoading = writable<boolean>(false);
export const phaseError = writable<string | null>(null);

// Current time store that updates every second (for countdown)
export const currentTime = readable(new Date(), (set) => {
	if (!browser) return;

	set(new Date());
	const interval = setInterval(() => {
		set(new Date());
	}, 1000);

	return () => clearInterval(interval);
});

// Derived stores - Phase 1
export const phase1Deadline = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase1_deadline ?? null
);

export const isPhase1Locked = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase1_locked ?? false
);

// Derived stores - Phase 2
export const currentPhase = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.current_phase ?? 'phase_1'
);

export const isPhase2Active = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.is_phase2_active ?? false
);

export const isPhase2BracketLocked = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase2_bracket_locked ?? false
);

export const phase2BracketDeadline = derived(
	phaseStatus,
	($phaseStatus) => $phaseStatus?.phase2_bracket_deadline ?? null
);

// Live countdown stores (update every second)
export const phase1Countdown = derived(
	[phase1Deadline, currentTime],
	([$deadline, $now]) => getTimeUntilDeadline($deadline, $now)
);

export const phase2Countdown = derived(
	[phase2BracketDeadline, currentTime],
	([$deadline, $now]) => getTimeUntilDeadline($deadline, $now)
);

// Actions
export async function fetchPhaseStatus(): Promise<void> {
	phaseLoading.set(true);
	phaseError.set(null);

	try {
		const data = await competitionApi.getPhaseStatus();
		phaseStatus.set(data);
	} catch (e) {
		phaseError.set(e instanceof Error ? e.message : 'Failed to load phase status');
	} finally {
		phaseLoading.set(false);
	}
}

// Utility functions
export function formatDeadline(deadline: string | null): string {
	if (!deadline) return 'Not set';
	const date = new Date(deadline);
	return date.toLocaleString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function getTimeUntilDeadline(deadline: string | null, now: Date = new Date()): string {
	if (!deadline) return 'Not set';

	const deadlineDate = new Date(deadline);
	const diff = deadlineDate.getTime() - now.getTime();

	if (diff <= 0) return 'Locked';

	const days = Math.floor(diff / (1000 * 60 * 60 * 24));
	const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
	const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
	const seconds = Math.floor((diff % (1000 * 60)) / 1000);

	if (days > 0) return `${days}d ${hours}h ${minutes}m ${seconds}s`;
	if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
	if (minutes > 0) return `${minutes}m ${seconds}s`;
	return `${seconds}s`;
}

// ---------------------------------------------------------------------------
// uxPhase — UI-facing tournament phase derivation
// ---------------------------------------------------------------------------
//
// Composes PhaseStatus + final-fixture-finished into a single UI enum that
// drives the landing dispatcher. Pattern lifted from upstream
// (laarohi/predictorv2). We collapse their 5-phase taxonomy
// (pre/group_stage/between/knockout/post) to 3 (pre/during/post) because
// Phase 2 is dormant in our fork per CLAUDE.md.
//
// Post-competition (final fixture finished) is detected via a SEPARATE
// derived store (`isFinalFinished`) — we don't put fixtures into the
// uxPhase derived's dependency list because dashboards may mutate
// `fixtures` heavily on mount, and that cascade triggered an infinite
// reactive loop upstream when the dispatcher's many transitive subscribers
// all re-fired together. The dispatcher reads finalFinished once via the
// composed uxPhase derived; uxPhase stays stable across fixture writes.

/**
 * Pure derivation — exported separately for unit testing. The Svelte
 * derived store below is a thin wrapper.
 *
 * Priority of checks matters:
 *   1. finalFinished short-circuits everything — a finished final
 *      overrides any lingering lock states.
 *   2. Null phaseStatus → pre_tournament (defensive default for first
 *      paint before /phase-status returns).
 *   3. phase1_locked partitions the remaining space deterministically.
 */
export function deriveUxPhase(
	phaseStatus: PhaseStatus | null,
	finalFinished: boolean
): UxPhase {
	if (finalFinished) return 'post_competition';
	if (!phaseStatus) return 'pre_tournament';
	if (!phaseStatus.phase1_locked) return 'pre_tournament';
	return 'during_tournament';
}

/**
 * True when the FINAL fixture has status="finished". Derived from the
 * `fixtures` store so it tracks score-sync writes, but kept separate from
 * `uxPhase` to avoid cascading reactive updates into every uxPhase
 * subscriber on every fixture write.
 */
export const isFinalFinished = derived(fixtures, ($fixtures) => {
	const finalFixture = $fixtures.find((f) => f.stage === 'final');
	return finalFixture?.status === 'finished';
});

/**
 * Dev-only override for the derived uxPhase. Set by +layout.svelte when
 * the URL carries ?uxPhase=... and `dev` from $app/environment is true.
 * Always null in production builds.
 */
export const uxPhaseOverride = writable<UxPhase | null>(null);

/**
 * Composed UX phase store. Reads the override first, then derives from
 * phaseStatus + finalFinished. Consumers (the landing dispatcher) should
 * subscribe to this, never to the raw signals directly — that ensures
 * the dev override works.
 */
export const uxPhase = derived(
	[phaseStatus, isFinalFinished, uxPhaseOverride],
	([$phaseStatus, $finalFinished, $override]) =>
		$override ?? deriveUxPhase($phaseStatus, $finalFinished)
);

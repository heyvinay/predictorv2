/**
 * Phase store for competition phase status.
 */

import { writable, derived, readable } from 'svelte/store';
import { browser } from '$app/environment';
import * as competitionApi from '$api/competition';
import type { PhaseStatus } from '$types';

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

/** Admin-controlled release switch for the post-deadline pages
 *  (v2.166.0). The field exists on the wire but not on the barrel's
 *  PhaseStatus interface (user WIP lockout) — cast through. False until
 *  the admin clicks "Go live" on /admin after the deadline clean-up. */
export const postDeadlineLive = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { post_deadline_live?: boolean }) | null)
			?.post_deadline_live ?? false
);

/** Admin-controlled release switch for the Group Stage Winner card +
 *  GROUP_STAGE_FINAL broadcast (v2.181.0). False until the admin
 *  presses release on /admin at 7pm Malta on Sunday 28 June 2026
 *  (or whenever the group-stage winner is to be revealed). */
export const groupStageWinnerReleased = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { group_stage_winner_released?: boolean }) | null)
			?.group_stage_winner_released ?? false
);

/** Admin-controlled gate for the scoring engine's advancement payouts
 *  (v2.181.1). False until the admin presses "Enable knockout scoring"
 *  on /admin — typically right after the group-stage winner has been
 *  announced and the bracket seeding has been verified. Cast through
 *  PhaseStatus the same way as the post-deadline switch above (barrel
 *  WIP lockout). */
export const knockoutScoringEnabled = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { knockout_scoring_enabled?: boolean }) | null)
			?.knockout_scoring_enabled ?? false
);

/** Admin-controlled master switch for the live projected leaderboard
 *  (v2.198.0). False until the admin flips it on /admin. Requires
 *  knockoutScoringEnabled to ALSO be true for the live board to ever
 *  actually appear — this flag alone doesn't guarantee it. */
export const liveProjectionEnabled = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { live_projection_enabled?: boolean }) | null)
			?.live_projection_enabled ?? false
);

/** Admin-controlled master switch for the what-if bracket simulator
 *  (v2.194.x). False until the admin flips it on /admin. Used at the
 *  layout level to render a subtle "NEW" nudge on the Results rail item
 *  once it's enabled — no dedicated /simulator/status fetch per page
 *  load, since phase-status is already hydrated in the layout. */
export const simulatorEnabled = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { simulator_enabled?: boolean }) | null)
			?.simulator_enabled ?? false
);

/** Admin-controlled master switch for the Win Probability leaderboard
 *  tab. False (admin-only) until the admin flips it on /admin — at
 *  which point non-admins see the tab too. */
export const winProbabilityEnabled = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { win_probability_enabled?: boolean }) | null)
			?.win_probability_enabled ?? false
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

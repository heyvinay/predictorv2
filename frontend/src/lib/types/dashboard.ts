/**
 * V4 Dashboard types (v2.165.0).
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched.
 * Import directly: `from '$lib/types/dashboard'`.
 */

import type { Fixture } from '$types';

/** Tag-pill tone for announcement cards (frontend colour mapping). */
export type AnnouncementTone = 'gold' | 'green' | 'mute';

/** One admin-authored announcement from GET /api/announcements. */
export interface Announcement {
	id: string;
	tag: string;
	tone: AnnouncementTone | string;
	title: string;
	body: string;
	author_name: string;
	published: boolean;
	created_at: string;
	updated_at: string;
}

/** Create/update payload for the admin CRUD endpoints. */
export interface AnnouncementWrite {
	tag: string;
	tone: AnnouncementTone;
	title: string;
	body: string;
	published: boolean;
}

/** Round chip + context label for a dashboard table row. */
export interface DashRoundChip {
	/** "R1".."R3" group matchdays, "R32".."F" knockout. */
	chip: string;
	/** "Group D" for group rows, "9 Jul" for knockout rows. */
	sub: string;
	isGroup: boolean;
}

/** The selected entry's pick on a not-yet-finished fixture. */
export type DashPick =
	| { kind: 'score'; label: string }
	| { kind: 'team'; team: string; tla: string }
	| { kind: 'none' };

/** The selected entry's call + points on a finished fixture. */
export type DashCall =
	| { kind: 'score'; label: string; grade: 'exact' | 'result' | 'miss'; pts: number }
	| { kind: 'team'; team: string; tla: string; hit: boolean; pts: number }
	| { kind: 'none'; pts: 0 };

/** One row of the Movers card. */
export interface MoverRow {
	entry_id: string;
	label: string;
	move: number;
}

/** One pill in the Matchday strip. 'today' = live/scheduled/finished-earlier
 *  fixture on today's local calendar day (full emphasis). 'context' = a
 *  flanking fixture — the most recent finished game before today, or one of
 *  tomorrow's scheduled games — rendered dimmed to signal it's not "now". */
export interface MatchdayStripItem {
	fixture: Fixture;
	variant: 'today' | 'context';
}

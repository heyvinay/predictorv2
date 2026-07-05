/**
 * Release + feature-highlight helpers — the shared source of truth for
 * surfacing version/release information to BOTH the admin Release Notes
 * page (`/admin/releases`) and the user-facing "What's New" panel.
 *
 * Two distinct data sources, deliberately kept separate:
 *   - `changelog.json`        → the raw, per-semver DEV log (100s of rows,
 *                               includes internal/fix/merge noise). Powers
 *                               the admin Release Notes page + currentVersion().
 *   - `featureHighlights.json` → a short, hand-curated CONSOLIDATION of many
 *                               releases into user-friendly themes. Powers the
 *                               What's New panel. Never a filter of the raw
 *                               changelog — so dev framing / phase language
 *                               can't leak into user-facing copy.
 */

import changelogData from '$lib/data/changelog.json';
import featureHighlightsData from '$lib/data/featureHighlights.json';

export type ReleaseType = 'feature' | 'improvement' | 'fix' | 'internal' | 'merge';

/** One row of the raw dev changelog. */
export interface ReleaseEntry {
	version: string;
	date: string;
	type: string;
	summary: string;
	commit: string;
}

/** One curated, user-facing feature theme (consolidates many releases). */
export interface FeatureHighlight {
	id: string;
	title: string;
	blurb: string;
	/** Version this theme first landed in (rendered as a "Since v…" chip). */
	since: string;
	/** ISO date the theme first landed. */
	date: string;
	/** Optional in-app deep link to the feature. */
	href?: string;
	/** Optional CTA label for the deep link. */
	cta?: string;
}

/** type → DaisyUI badge class. Shared so admin + user surfaces never drift. */
export const RELEASE_TYPE_BADGE: Record<string, string> = {
	feature: 'badge-success',
	improvement: 'badge-info',
	fix: 'badge-warning',
	internal: 'badge-ghost',
	merge: 'badge-primary'
};

/** type → user-facing label. */
export const RELEASE_TYPE_LABEL: Record<string, string> = {
	feature: 'New',
	improvement: 'Polish',
	fix: 'Fix',
	internal: 'Internal',
	merge: 'Merge'
};

/** All raw changelog entries, newest-first (the JSON ships oldest-first). */
export function allReleasesNewestFirst(): ReleaseEntry[] {
	return ([...changelogData.entries] as ReleaseEntry[]).reverse();
}

/**
 * Current app version = the newest changelog entry's version. Matches
 * `package.json` per the release process (the version bump and the
 * changelog append land in the same release), so this is a safe runtime
 * proxy without wiring `package.json` through a Vite `define`.
 */
export function currentVersion(): string {
	const entries = changelogData.entries as ReleaseEntry[];
	return entries.length ? entries[entries.length - 1].version : '—';
}

/** Curated user-facing highlights, newest-first (as authored in the JSON). */
export const featureHighlights: FeatureHighlight[] =
	featureHighlightsData.highlights as FeatureHighlight[];

/**
 * Identity of the newest highlight — the "have they seen the latest thing?"
 * key behind the What's New "New" badge. Empty string when there are no
 * highlights (badge then never shows).
 */
export function latestHighlightId(): string {
	return featureHighlights.length ? featureHighlights[0].id : '';
}

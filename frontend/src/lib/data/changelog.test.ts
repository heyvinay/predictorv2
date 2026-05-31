/**
 * Guard-rails for `changelog.json`.
 *
 * Two real bugs shipped to production on 2026-05-31 because the changelog's
 * implicit conventions were violated:
 *
 *   1. A new entry was *prepended* to entries[], but the admin Release Notes
 *      panel calls `.reverse()` on the array for display (oldest-first in JSON
 *      → newest-first in UI). The new entry ended up at the bottom of the
 *      displayed list, invisible behind the default 50-row slice.
 *
 *   2. Two entries simultaneously held `commit: "pending"` as a placeholder.
 *      The admin's `{#each ... (r.commit)}` keyed-each rejects duplicate keys
 *      at runtime, crashing the panel mid-render and blanking the page.
 *
 * This test makes both classes of bug a CI failure. Add new invariants here
 * as new ways to break the changelog are discovered.
 */
import { describe, expect, it } from 'vitest';

import changelog from './changelog.json';

interface ReleaseEntry {
	version: string;
	date: string;
	type: string;
	summary: string;
	commit: string;
}

const VALID_TYPES = ['feature', 'improvement', 'fix', 'internal', 'merge'];

/** Parse a 3-part semver string like "2.150.1" into `[2, 150, 1]`. */
function parseSemver(v: string): [number, number, number] {
	const parts = v.split('.').map((n) => parseInt(n, 10));
	return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
}

/** Returns negative if `a < b`, positive if `a > b`, zero if equal. */
function compareSemver(a: string, b: string): number {
	const av = parseSemver(a);
	const bv = parseSemver(b);
	for (let i = 0; i < 3; i++) {
		if (av[i] !== bv[i]) return av[i] - bv[i];
	}
	return 0;
}

describe('changelog.json invariants', () => {
	const entries = changelog.entries as ReleaseEntry[];

	it('has at least one entry', () => {
		expect(entries.length).toBeGreaterThan(0);
	});

	it('every entry has every required field populated', () => {
		for (const [i, e] of entries.entries()) {
			expect(e.version, `entry ${i} missing version`).toBeTruthy();
			expect(e.date, `entry ${i} (${e.version}) missing date`).toBeTruthy();
			expect(e.type, `entry ${i} (${e.version}) missing type`).toBeTruthy();
			expect(e.summary, `entry ${i} (${e.version}) missing summary`).toBeTruthy();
			expect(e.commit, `entry ${i} (${e.version}) missing commit`).toBeTruthy();
		}
	});

	it('every entry has a valid type', () => {
		for (const e of entries) {
			expect(
				VALID_TYPES.includes(e.type),
				`${e.version} has invalid type "${e.type}" (allowed: ${VALID_TYPES.join(', ')})`
			).toBe(true);
		}
	});

	it('version strings are unique', () => {
		const seen = new Set<string>();
		for (const e of entries) {
			expect(seen.has(e.version), `duplicate version: ${e.version}`).toBe(false);
			seen.add(e.version);
		}
	});

	it('commit SHAs are unique (apart from "pending" placeholders)', () => {
		// "pending" is allowed as a temporary placeholder when you commit before
		// knowing the SHA — fill it in shortly after. The admin renderer also has
		// a defensive composite each-key (version + commit) so multiple "pending"
		// entries don't crash, but it's still hygienic to keep at most one.
		const seenReal = new Set<string>();
		for (const e of entries) {
			if (e.commit === 'pending') continue;
			expect(
				seenReal.has(e.commit),
				`duplicate commit SHA: ${e.commit} (used by ${e.version})`
			).toBe(false);
			seenReal.add(e.commit);
		}
	});

	it('entries are stored oldest-first (semver-ascending)', () => {
		// The admin Release Notes panel reverses this array to display newest-first.
		// If you prepend a new entry to the top instead of appending to the bottom,
		// the "latest" header will show the wrong version and your entry will sit
		// at the bottom of the displayed list. Always append.
		for (let i = 1; i < entries.length; i++) {
			const prev = entries[i - 1];
			const curr = entries[i];
			const cmp = compareSemver(prev.version, curr.version);
			expect(
				cmp,
				`out-of-order: entries[${i - 1}] (${prev.version}) should be < entries[${i}] (${curr.version})`
			).toBeLessThanOrEqual(0);
		}
	});

	it('date strings parse as valid ISO dates', () => {
		for (const e of entries) {
			const d = new Date(e.date);
			expect(
				!Number.isNaN(d.getTime()),
				`${e.version} has unparseable date "${e.date}" (expected YYYY-MM-DD)`
			).toBe(true);
		}
	});
});

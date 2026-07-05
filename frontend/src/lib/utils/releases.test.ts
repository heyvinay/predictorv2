import { describe, it, expect } from 'vitest';
import changelogData from '$lib/data/changelog.json';
import {
	allReleasesNewestFirst,
	currentVersion,
	featureHighlights,
	latestHighlightId
} from './releases';

describe('releases util', () => {
	it('currentVersion() matches the newest changelog entry', () => {
		const entries = changelogData.entries;
		const newest = entries[entries.length - 1].version;
		expect(currentVersion()).toBe(newest);
		expect(currentVersion()).toMatch(/^\d+\.\d+\.\d+$/);
	});

	it('allReleasesNewestFirst() reverses the oldest-first changelog', () => {
		const all = allReleasesNewestFirst();
		expect(all.length).toBe(changelogData.entries.length);
		// index 0 is the newest = last entry of the source array
		expect(all[0].version).toBe(changelogData.entries[changelogData.entries.length - 1].version);
	});

	it('latestHighlightId() is the first (newest) highlight', () => {
		expect(latestHighlightId()).toBe(featureHighlights[0].id);
		expect(latestHighlightId().length).toBeGreaterThan(0);
	});

	it('every highlight has the required user-facing fields', () => {
		expect(featureHighlights.length).toBeGreaterThan(0);
		for (const h of featureHighlights) {
			expect(h.id).toBeTruthy();
			expect(h.title).toBeTruthy();
			expect(h.blurb).toBeTruthy();
			expect(h.since).toMatch(/^\d+\.\d+\.\d+$/);
			expect(h.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
		}
	});

	it('highlight ids are unique', () => {
		const ids = featureHighlights.map((h) => h.id);
		expect(new Set(ids).size).toBe(ids.length);
	});

	it('no highlight copy leaks phase language (single-phase invariant)', () => {
		for (const h of featureHighlights) {
			const copy = `${h.title} ${h.blurb} ${h.cta ?? ''}`.toLowerCase();
			expect(copy).not.toContain('phase 1');
			expect(copy).not.toContain('phase 2');
		}
	});
});

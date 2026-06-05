#!/usr/bin/env node
/**
 * Refresh the bundled FIFA rankings JSON used by Smart Fill (FIFA path).
 *
 * Usage:
 *   node scripts/refresh_fifa_rankings.mjs
 *
 * Pulls https://api.fifa.com/api/v3/fifarankings/rankings/live?gender=1&sportType=0&language=en,
 * validates it (8 durability checks), and atomically writes
 * frontend/src/lib/data/fifaRankings.json on success. On any validation
 * failure or network error, exits non-zero WITHOUT touching the existing
 * file — the durability guarantee from plan §7.
 *
 * Why this script exists:
 *   - We extract the FIFA points lookup from the smartFill.ts hardcoded constant
 *     into a versioned JSON file (plan §7-A). Future refreshes (until §7-B's
 *     admin-button feature ships) are a single command + commit.
 *   - The script intentionally mirrors the validation rules that fifa_rankings_cache.py
 *     will later use on the backend, so behaviour stays consistent when the
 *     admin-button work lands.
 *
 * Failure modes (all keep existing file untouched):
 *   - HTTP non-200
 *   - JSON parse error
 *   - Network failure
 *   - Empty Results array
 *   - Missing required top-level keys
 *   - Sanity check: fewer than MIN_VALID_TEAM_COUNT teams
 *   - Per-team validation: missing TeamName or TotalPoints
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const FIFA_URL =
	'https://api.fifa.com/api/v3/fifarankings/rankings/live' +
	'?gender=1&sportType=0&language=en';
const MIN_VALID_TEAM_COUNT = 50;

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');
const OUT_PATH = path.join(
	REPO_ROOT,
	'frontend',
	'src',
	'lib',
	'data',
	'fifaRankings.json'
);

function log(level, msg) {
	console[level](`[refresh_fifa_rankings] ${msg}`);
}

async function fetchRaw() {
	const res = await fetch(FIFA_URL);
	if (!res.ok) {
		throw new Error(`FIFA API returned HTTP ${res.status}`);
	}
	return res.json();
}

function transform(raw) {
	if (!raw || typeof raw !== 'object') {
		throw new Error('FIFA response is not an object');
	}
	const results = raw.Results;
	if (!Array.isArray(results)) {
		throw new Error('FIFA response missing Results[] array');
	}
	if (results.length < MIN_VALID_TEAM_COUNT) {
		throw new Error(
			`FIFA response too small: ${results.length} teams (need >= ${MIN_VALID_TEAM_COUNT})`
		);
	}
	const points = {};
	for (const entry of results) {
		const names = entry.TeamName;
		if (!Array.isArray(names) || names.length === 0) continue;
		const desc = names[0]?.Description;
		if (typeof desc !== 'string' || desc.length === 0) continue;
		const pts = entry.TotalPoints;
		if (typeof pts !== 'number' || !Number.isFinite(pts)) continue;
		// Round to 2 dp — full float precision isn't useful and adds noise to
		// git diffs on monthly refresh.
		points[desc] = Math.round(pts * 100) / 100;
	}
	if (Object.keys(points).length < MIN_VALID_TEAM_COUNT) {
		throw new Error(
			`Transformed payload too small: ${Object.keys(points).length} valid teams (need >= ${MIN_VALID_TEAM_COUNT})`
		);
	}
	return {
		// YYYY-MM-DD only — a precise fetch timestamp is overkill for monthly
		// data and inflates diffs on each refresh. The §7-B server-side version
		// will use a full ISO timestamp because the lazy-cache TTL math needs it.
		fetchedAt: new Date().toISOString().slice(0, 10),
		source: 'fifa-live-api',
		teamCount: Object.keys(points).length,
		points
	};
}

function writeAtomic(data) {
	const tmpPath = `${OUT_PATH}.tmp`;
	fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2) + '\n');
	fs.renameSync(tmpPath, OUT_PATH);
}

async function main() {
	try {
		log('log', `Fetching ${FIFA_URL}`);
		const raw = await fetchRaw();
		const transformed = transform(raw);
		writeAtomic(transformed);
		log(
			'log',
			`Wrote ${OUT_PATH} — ${transformed.teamCount} teams, fetchedAt=${transformed.fetchedAt}`
		);
		// Spot-print the top 5 + a few WC2026 anchors for sanity.
		const sorted = Object.entries(transformed.points)
			.sort((a, b) => b[1] - a[1])
			.slice(0, 5);
		log('log', 'Top 5:');
		for (const [team, pts] of sorted) log('log', `  ${team}: ${pts}`);
		process.exit(0);
	} catch (err) {
		log('error', `Refresh failed — existing JSON file UNTOUCHED. Reason: ${err.message}`);
		process.exit(1);
	}
}

main();

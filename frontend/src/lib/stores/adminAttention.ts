/**
 * Admin attention counter.
 *
 * Polls the admin entries endpoint every 60s for entries that need
 * admin follow-up. The current signal is **unpaid entries** — admins
 * should chase payment before the competition starts. The shape lets
 * us swap or add signals later without touching the consumer.
 *
 * Only polls when the logged-in user is an admin. Non-admins keep the
 * store at 0 and never make a request. Tear-down on logout via
 * `stopAdminAttentionPolling`.
 */

import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { adminListEntries } from '$lib/api/admin';

/** Count of entries currently flagged for admin attention. 0 hides the badge. */
export const adminAttentionCount = writable<number>(0);

const POLL_INTERVAL_MS = 60_000;

let pollTimer: ReturnType<typeof setInterval> | null = null;
let inflight = false;

async function pollOnce(): Promise<void> {
	if (inflight) return; // overlapping polls would double-spend network
	inflight = true;
	try {
		// limit=1 keeps the response small; we only need the total count.
		const page = await adminListEntries({ paid: false }, { limit: 1, offset: 0 });
		adminAttentionCount.set(page.total);
	} catch {
		// Silently degrade — keep last known count rather than zeroing it out
		// and flickering the badge on transient errors.
	} finally {
		inflight = false;
	}
}

export function startAdminAttentionPolling(): void {
	if (!browser) return;
	if (pollTimer) return; // idempotent
	void pollOnce();
	pollTimer = setInterval(() => void pollOnce(), POLL_INTERVAL_MS);
}

export function stopAdminAttentionPolling(): void {
	if (pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
	adminAttentionCount.set(0);
}

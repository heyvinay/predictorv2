/**
 * Shared loader for the /entries subtree (list + detail).
 *
 * The list page and the wizard both need a populated entries store. By
 * running `loadEntries` here we guarantee:
 *   1. The store is hydrated by the time either page mounts.
 *   2. The hydration call happens exactly once per navigation into the
 *      subtree, not twice when the user moves list → detail.
 *
 * Auth-gating stays in each page; the root layout already redirects
 * unauthenticated visitors to /login, so we don't duplicate that here.
 */

import { browser } from '$app/environment';
import { get } from 'svelte/store';
import { user, isAuthenticated } from '$stores/auth';
import { entries, loadEntries } from '$stores/entries';

export const load = async (): Promise<Record<string, never>> => {
	if (!browser) return {};
	const u = get(user);
	if (!get(isAuthenticated) || !u?.id) return {};
	if (get(entries).length === 0) {
		await loadEntries(u.id);
	}
	return {};
};

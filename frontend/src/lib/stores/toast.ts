/**
 * Minimal toast store — a tiny stack of transient notifications rendered by
 * `Toaster.svelte`. No external library; DaisyUI classes only.
 *
 * Used today for one-time contextual feature nudges (see
 * `utils/featureNudges.ts`), but generic enough for any fire-and-forget
 * message. Toasts auto-dismiss after `timeout` ms (default 8s) and can be
 * dismissed manually.
 */

import { writable } from 'svelte/store';

export interface Toast {
	id: string;
	title: string;
	message?: string;
	/** Optional in-app deep link. Rendered as the CTA anchor when present. */
	href?: string;
	/** CTA label (only used with `href`). */
	cta?: string;
	/** Auto-dismiss delay in ms. 0 disables auto-dismiss. Default 8000. */
	timeout?: number;
	/** Fired when the user clicks the CTA (e.g. analytics). */
	onCta?: () => void;
}

export const toasts = writable<Toast[]>([]);

/** Push a toast onto the stack. Returns its id. */
export function pushToast(t: Omit<Toast, 'id'> & { id?: string }): string {
	const id = t.id ?? `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
	toasts.update((list) => [...list.filter((x) => x.id !== id), { ...t, id }]);

	const timeout = t.timeout ?? 8000;
	if (timeout > 0 && typeof window !== 'undefined') {
		window.setTimeout(() => dismissToast(id), timeout);
	}
	return id;
}

export function dismissToast(id: string): void {
	toasts.update((list) => list.filter((t) => t.id !== id));
}

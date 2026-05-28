/**
 * Authentication store for user state and JWT management.
 */

import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { api } from '$api/client';
import * as authApi from '$api/auth';
import { clearAllForUser } from '$stores/unsavedPersistence';
import { resetEntries } from '$stores/entries';
import type { User } from '$types';

const TOKEN_KEY = 'predictor_token';

// Initialize token from localStorage
function getStoredToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token: string | null) {
	if (!browser) return;
	if (token) {
		localStorage.setItem(TOKEN_KEY, token);
	} else {
		localStorage.removeItem(TOKEN_KEY);
	}
}

// Stores
export const token = writable<string | null>(getStoredToken());
export const user = writable<User | null>(null);
export const loading = writable<boolean>(false);
export const error = writable<string | null>(null);

// Derived stores
export const isAuthenticated = derived(token, ($token) => !!$token);
export const isAdmin = derived(user, ($user) => $user?.is_admin ?? false);

// Subscribe to token changes to update API client and localStorage
token.subscribe((value) => {
	api.setToken(value);
	setStoredToken(value);
});

// Actions
export async function requestMagicLink(
	email: string,
	captchaToken?: string | null
): Promise<boolean> {
	loading.set(true);
	error.set(null);

	try {
		await authApi.requestMagicLink({ email, captcha_token: captchaToken ?? null });
		return true;
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to send sign-in link');
		return false;
	} finally {
		loading.set(false);
	}
}

export async function fetchUser(): Promise<User | null> {
	const currentToken = get(token);
	if (!currentToken) {
		user.set(null);
		return null;
	}

	try {
		const userData = await authApi.getCurrentUser();
		user.set(userData);
		return userData;
	} catch (e) {
		// Token invalid, clear auth state. Also wipe any persisted draft
		// buffers for the previous user so they don't bleed into a re-auth
		// on the same browser.
		const prevId = get(user)?.id;
		if (prevId) clearAllForUser(prevId);
		resetEntries();
		token.set(null);
		user.set(null);
		return null;
	}
}

export function logout() {
	const prevId = get(user)?.id;
	if (prevId) clearAllForUser(prevId);
	resetEntries();
	token.set(null);
	user.set(null);
	error.set(null);
	goto('/login');
}

export async function handleOAuthCallback(accessToken: string): Promise<void> {
	token.set(accessToken);
	// Await so the user store is populated BEFORE the caller's goto() fires.
	// Previously this was fire-and-forget, which let the dashboard mount
	// while $user was still null — and any route that branched on $user
	// (or any reactive that re-checked $isAuthenticated mid-load) would
	// bounce the freshly-authenticated session back to /login.
	await fetchUser();
}

// Initialize auth state on app load
export async function initAuth() {
	const currentToken = get(token);
	if (currentToken) {
		await fetchUser();
	}
}

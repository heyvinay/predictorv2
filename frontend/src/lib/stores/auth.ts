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
import type { User, UserCreate, UserLogin } from '$types';

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
export async function register(data: UserCreate): Promise<boolean> {
	loading.set(true);
	error.set(null);

	try {
		const result = await authApi.register(data);
		token.set(result.access_token);
		await fetchUser();
		return true;
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Registration failed');
		return false;
	} finally {
		loading.set(false);
	}
}

export async function login(data: UserLogin): Promise<boolean> {
	loading.set(true);
	error.set(null);

	try {
		const result = await authApi.login(data);
		token.set(result.access_token);
		await fetchUser();
		return true;
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Login failed');
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

export function handleOAuthCallback(accessToken: string) {
	token.set(accessToken);
	fetchUser();
}

// Initialize auth state on app load
export async function initAuth() {
	const currentToken = get(token);
	if (currentToken) {
		await fetchUser();
	}
}

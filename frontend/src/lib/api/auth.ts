/**
 * Authentication API functions.
 */

import { api } from './client';
import type { Token, User, UserCreate, UserLogin, PasswordChange, UserStats } from '$types';

export async function register(data: UserCreate): Promise<Token> {
	return api.post<Token>('/auth/register', data);
}

export async function login(data: UserLogin): Promise<Token> {
	return api.post<Token>('/auth/login', data);
}

export async function getCurrentUser(): Promise<User> {
	return api.get<User>('/auth/me');
}

export function getGoogleAuthUrl(): string {
	return '/api/auth/google';
}

export async function changePassword(data: PasswordChange): Promise<{ message: string }> {
	return api.post<{ message: string }>('/auth/me/password', data);
}

/**
 * Stats are entry-scoped — points only aggregate at the entry level.
 * Pass `entryId` to scope to a specific entry; otherwise the backend
 * resolves to the user's primary eligible entry. Returns zero-filled
 * stats when the user has no eligible entry.
 */
export async function getUserStats(entryId?: string | null): Promise<UserStats> {
	const url = entryId
		? `/auth/me/stats?entry_id=${encodeURIComponent(entryId)}`
		: '/auth/me/stats';
	return api.get<UserStats>(url);
}

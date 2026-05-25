/**
 * Authentication API functions.
 */

import { api } from './client';
import type { MagicLinkRequest, User, UserUpdate, UserStats } from '$types';

export async function requestMagicLink(data: MagicLinkRequest): Promise<{ message: string }> {
	return api.post<{ message: string }>('/auth/request-magic-link', data);
}

export async function getCurrentUser(): Promise<User> {
	return api.get<User>('/auth/me');
}

export async function updateProfile(data: UserUpdate): Promise<User> {
	return api.patch<User>('/auth/me', data);
}

export function getGoogleAuthUrl(): string {
	return '/api/auth/google';
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

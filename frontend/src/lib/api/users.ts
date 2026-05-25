/**
 * Users API functions — public profiles and prediction viewing.
 *
 * Both routes accept an optional `entryId` query param so a viewer can
 * inspect a specific entry of the target user. Without it, the backend
 * resolves to the user's primary eligible entry.
 */

import { api } from './client';
import type { PublicProfile, UserPredictionsResponse } from '$types';

export async function getUserProfile(
	userId: string,
	entryId?: string | null
): Promise<PublicProfile> {
	const url = entryId
		? `/users/${userId}/profile?entry_id=${encodeURIComponent(entryId)}`
		: `/users/${userId}/profile`;
	return api.get<PublicProfile>(url);
}

export async function getUserPredictions(
	userId: string,
	entryId?: string | null
): Promise<UserPredictionsResponse> {
	const url = entryId
		? `/users/${userId}/predictions?entry_id=${encodeURIComponent(entryId)}`
		: `/users/${userId}/predictions`;
	return api.get<UserPredictionsResponse>(url);
}

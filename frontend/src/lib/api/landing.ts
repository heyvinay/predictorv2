/**
 * Landing-page stats API (v2.160.x).
 *
 * Powers the social-proof card. Public endpoint, no auth required.
 */

import { api } from './client';

export interface LandingStats {
	/** Total users with name set (onboarding-complete). */
	predictors_signed_up: number;
	/** Same definition, filtered to created_at within the last hour. */
	joined_in_last_hour: number;
}

export async function getLandingStats(): Promise<LandingStats> {
	return api.get<LandingStats>('/landing/stats');
}

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
	/** Total entries with at least one phase row in SUBMITTED. Drives
	 *  the "X × €Y" tagline under the prize pot. */
	submitted_entries: number;
	/** Active competition's entry fee in euros. 0 when no active
	 *  competition — frontend hides the pot in that case. */
	entry_fee_eur: number;
	/** `entry_fee_eur × submitted_entries`. Computed server-side so the
	 *  frontend doesn't need to know about entry_fee separately. */
	prize_pot_eur: number;
}

export async function getLandingStats(): Promise<LandingStats> {
	return api.get<LandingStats>('/landing/stats');
}

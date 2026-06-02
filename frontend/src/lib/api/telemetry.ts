/**
 * Telemetry tracker — fire-and-forget POST to the backend's
 * /api/telemetry/event endpoint. Backend forwards to PostHog via its
 * server-side SDK (see backend/app/services/analytics.py +
 * backend/app/api/telemetry.py).
 *
 * Failures (network down, 400 on unknown event, no auth) are swallowed
 * — analytics must never break the app. The backend allow-list at
 * api/telemetry.py is the security boundary; this wrapper is just a
 * thin convenience.
 */

import { api } from './client';

export async function track(
	event: string,
	properties?: Record<string, unknown>
): Promise<void> {
	try {
		await api.post('/telemetry/event', { event, properties });
	} catch {
		// Analytics must never break the app — swallow all errors.
	}
}

/**
 * Feedback API — POST the user's star rating + written message. The backend
 * emails it to the pool owner via Resend (see backend/app/api/feedback.py).
 * Thin wrapper around the shared `api` client; callers catch
 * `ApiResponseError` for the failure state.
 */

import { api } from './client';

export async function sendFeedback(rating: number, message: string): Promise<void> {
	await api.post('/feedback/', { rating, message });
}

/**
 * Feedback API — POST the user's star rating + written message. The backend
 * emails it to the pool owner via Resend (see backend/app/api/feedback.py).
 * Thin wrapper around the shared `api` client; callers catch
 * `ApiResponseError` for the failure state.
 *
 * `features` (v2.214.0, wrap-up FeedbackTile) is an optional list of
 * feature-chip ids the submitter flagged — additive param, defaults to `[]`
 * so the existing 2-arg call sites (RatingPrompt.svelte) keep working
 * unchanged. Backend silently drops any id outside its ALLOWED_FEATURES
 * set rather than 422ing (see backend/app/api/feedback.py).
 */

import { api } from './client';

export async function sendFeedback(
	rating: number,
	message: string,
	features: string[] = []
): Promise<void> {
	await api.post('/feedback/', { rating, message, features });
}

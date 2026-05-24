/**
 * Prediction-entry API client.
 *
 * Mirrors `backend/app/api/entries.py` after the lifecycle simplification.
 * User endpoints live under `/api/entries`; admin endpoints (withdraw,
 * reinstate, disable/enable, paid/prize toggles) live under
 * `/api/admin/entries/{id}/...` and are called from the admin UI.
 */

import { api } from './client';
import type {
	CompletionSummary,
	Entry,
	EntrySettings,
	EntryCreate,
	EntryRename,
	EntryWithdraw,
	EntryReinstate
} from '$lib/types/entry';

export async function listEntries(): Promise<Entry[]> {
	return api.get<Entry[]>('/entries');
}

export async function getEntrySettings(): Promise<EntrySettings> {
	return api.get<EntrySettings>('/entries/settings');
}

export async function createEntry(payload: EntryCreate = {}): Promise<Entry> {
	return api.post<Entry>('/entries', payload);
}

export async function getEntry(entryId: string): Promise<Entry> {
	return api.get<Entry>(`/entries/${entryId}`);
}

export async function renameEntry(
	entryId: string,
	payload: EntryRename
): Promise<Entry> {
	return api.patch<Entry>(`/entries/${entryId}`, payload);
}

export async function duplicateEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/duplicate`);
}

/** DRAFT → SUBMITTED. Visible only when canSubmit() returns true. */
export async function submitEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/submit`);
}

/** SUBMITTED → DRAFT. Allowed only before competition.phase1_deadline. */
export async function editEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/edit`);
}

/** DRAFT → WITHDRAWN. User-initiated, before competition start. */
export async function withdrawEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/withdraw`);
}

/** WITHDRAWN → DRAFT. User-initiated, before competition start. */
export async function reinstateEntry(entryId: string): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/reinstate`);
}

/** Per-entry completion counts for all entries in the active competition. */
export async function getCompletionSummary(): Promise<CompletionSummary[]> {
	return api.get<CompletionSummary[]>('/entries/completion-summary');
}

// ---- Admin-only endpoints (called from the admin entries table) ----

export async function adminWithdrawEntry(
	entryId: string,
	payload: EntryWithdraw
): Promise<Entry> {
	return api.post<Entry>(`/admin/entries/${entryId}/withdraw`, payload);
}

export async function adminReinstateEntry(
	entryId: string,
	payload: EntryReinstate
): Promise<Entry> {
	return api.post<Entry>(`/admin/entries/${entryId}/reinstate`, payload);
}

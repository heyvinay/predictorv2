/**
 * Prediction-entry API client.
 *
 * Mirrors `backend/app/api/entries.py` user_router (mounted at `/api/entries`).
 * Admin endpoints under `/api/admin/...` are NOT included here — those
 * arrive in Task F.
 */

import { api } from './client';
import type {
	Entry,
	EntrySettings,
	EntryCreate,
	EntryRename,
	EntryWithdraw
} from '$lib/types/entry';
import type { PredictionPhase } from '$types';

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

export async function markPhaseReady(
	entryId: string,
	phase: PredictionPhase
): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/phases/${phase}/ready`);
}

export async function submitPhase(
	entryId: string,
	phase: PredictionPhase
): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/phases/${phase}/submit`);
}

export async function reopenPhase(
	entryId: string,
	phase: PredictionPhase
): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/phases/${phase}/reopen`);
}

export async function withdrawEntry(
	entryId: string,
	payload: EntryWithdraw = {}
): Promise<Entry> {
	return api.post<Entry>(`/entries/${entryId}/withdraw`, payload);
}

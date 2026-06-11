/**
 * Announcements API (v2.165.0) — dashboard hero feed + admin CRUD.
 */

import { api } from './client';
import type { Announcement, AnnouncementWrite } from '$lib/types/dashboard';

/** Published announcements, newest first (signed-in users). */
export async function getAnnouncements(): Promise<Announcement[]> {
	return api.get<Announcement[]>('/announcements/');
}

/** Every announcement including unpublished drafts (admin). */
export async function getAllAnnouncements(): Promise<Announcement[]> {
	return api.get<Announcement[]>('/admin/announcements/');
}

export async function createAnnouncement(
	payload: AnnouncementWrite
): Promise<Announcement> {
	return api.post<Announcement>('/admin/announcements/', payload);
}

export async function updateAnnouncement(
	id: string,
	payload: Partial<AnnouncementWrite>
): Promise<Announcement> {
	return api.patch<Announcement>(`/admin/announcements/${id}`, payload);
}

export async function deleteAnnouncement(id: string): Promise<void> {
	await api.delete(`/admin/announcements/${id}`);
}

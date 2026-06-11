/**
 * Pool-facing CSV exports (v2.168+).
 *
 * Separate from admin.ts because these downloads are for everyone once
 * the post-deadline release is live — the transparency sheet, not admin
 * tooling. Same Bearer-token blob pattern as downloadAdminEntriesCsv:
 * the JSON ApiClient can't carry a raw CSV body, and window.location
 * can't carry the Authorization header.
 */

import { api, ApiResponseError } from './client';

/** Trigger a browser download of the all-entries predictions CSV —
 *  every eligible entry's group scores, bracket picks and bonus
 *  answers, one column per entry. Backend gates on admin OR the
 *  post-deadline release switch (403 before release). */
export async function downloadAllEntriesCsv(): Promise<void> {
	const url = '/api/predictions/export/all-entries.csv';
	const tokenRaw = (api as unknown as { token: string | null }).token;
	const headers: Record<string, string> = {};
	if (tokenRaw) headers['Authorization'] = `Bearer ${tokenRaw}`;

	const response = await fetch(url, { method: 'GET', headers });
	if (!response.ok) {
		const body = await response
			.json()
			.catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
		throw new ApiResponseError(response.status, body.detail, body);
	}

	const blob = await response.blob();

	const cd = response.headers.get('Content-Disposition') ?? '';
	const match = cd.match(/filename="?([^"]+)"?/i);
	const today = new Date().toISOString().slice(0, 10);
	const filename = match?.[1] ?? `all-entries-predictions-${today}.csv`;

	const objectUrl = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = objectUrl;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(objectUrl), 100);
}

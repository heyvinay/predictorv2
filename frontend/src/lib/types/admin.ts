/**
 * Admin-only types.
 *
 * Lives in its own module (not the `$lib/types` barrel) — admin types are
 * only imported by admin surfaces, keeping the main bundle's type graph
 * clean.
 */

/** Drill-down for one incomplete entry (?detail=true on the endpoint). */
export interface EntryCompletenessDetail {
	missing_fixture_ids: string[];
	missing_bracket: Record<string, number>;
	missing_bonus_ids: string[];
}

/** One row of GET /api/admin/entries/completeness-check. */
export interface EntryCompletenessResult {
	entry_id: string;
	entry_name: string;
	user_name: string;
	user_email: string;
	missing_match_picks: number;
	missing_bracket_picks: number;
	missing_bonus_picks: number;
	is_complete: boolean;
	detail: EntryCompletenessDetail | null;
}

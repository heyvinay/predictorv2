/**
 * Bonus-question API functions.
 *
 * Questions are defined in worldcup2026.yml under `bonus:` and shipped to
 * the frontend pre-rendered (with {top_n} substituted). The DB holds
 * per-user picks and per-competition correct answers.
 */

import { api } from './client';

export type BonusCategory = 'group_stage' | 'top_flop' | 'awards';
// `top_flop` is rendered as "Knockout Stage — Top / Flop" in user-facing
// copy; the literal stays for backward compatibility with stored data.
// The filtered input_types added 2026-06-01 drive FIFA-rank-aware dropdowns.
export type BonusInputType =
	| 'team'
	| 'player'
	| 'team_outside_top_n'
	| 'team_in_top_n';

export interface BonusQuestion {
	id: string;
	category: BonusCategory;
	label: string;
	input_type: BonusInputType;
	points: number;
}

export interface BonusPrediction {
	question_id: string;
	answer: string;
}

export interface BonusAnswerView {
	question_id: string;
	label: string;
	category: BonusCategory;
	points: number;
	input_type: BonusInputType;
	/** All accepted correct answers (multiple entries = a tie). Empty if unresolved. */
	correct_answers: string[];
	/** Auto-derived suggestion(s) from fixtures + scores. Group-stage and
	 *  top/flop only; awards-category questions always have []. Advisory
	 *  — admin can apply via "Use computed" or override manually. */
	computed_answers: string[];
	resolved_at: string | null;
}

// User-side ----------------------------------------------------------------

export async function getBonusQuestions(): Promise<BonusQuestion[]> {
	return api.get<BonusQuestion[]>('/predictions/bonus/questions');
}

/** FIFA top_n cutoff + the team list it expands to, sourced from
 *  config/worldcup2026.yml. Used by the wizard to filter the
 *  dark_horse / flop dropdowns. Public — same auth surface as
 *  getBonusQuestions(). */
export interface BonusMeta {
	top_n: number;
	fifa_top_teams: string[];
}

export async function getBonusMeta(): Promise<BonusMeta> {
	return api.get<BonusMeta>('/predictions/bonus/meta');
}

export async function getMyBonusPredictions(entryId: string): Promise<BonusPrediction[]> {
	return api.get<BonusPrediction[]>(`/entries/${entryId}/predictions/bonus`);
}

export async function saveBonusPredictions(
	entryId: string,
	predictions: BonusPrediction[]
): Promise<BonusPrediction[]> {
	return api.post<BonusPrediction[]>(`/entries/${entryId}/predictions/bonus`, {
		predictions
	});
}

// Admin-side ---------------------------------------------------------------

export async function listBonusAnswers(): Promise<BonusAnswerView[]> {
	return api.get<BonusAnswerView[]>('/admin/bonus/answers');
}

export async function setBonusAnswer(
	questionId: string,
	correctAnswers: string[]
): Promise<BonusAnswerView> {
	return api.post<BonusAnswerView>('/admin/bonus/answers', {
		question_id: questionId,
		correct_answers: correctAnswers
	});
}

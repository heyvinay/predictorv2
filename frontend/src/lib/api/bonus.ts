/**
 * Bonus-question API functions.
 *
 * Questions are defined in worldcup2026.yml under `bonus:` and shipped to
 * the frontend pre-rendered (with {top_n} substituted). The DB holds
 * per-user picks and per-competition correct answers.
 */

import { api } from './client';

export type BonusCategory = 'group_stage' | 'top_flop' | 'awards';
export type BonusInputType = 'team' | 'player';

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
	correct_answer: string | null;
	resolved_at: string | null;
}

// User-side ----------------------------------------------------------------

export async function getBonusQuestions(): Promise<BonusQuestion[]> {
	return api.get<BonusQuestion[]>('/predictions/bonus/questions');
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
	correctAnswer: string
): Promise<BonusAnswerView> {
	return api.post<BonusAnswerView>('/admin/bonus/answers', {
		question_id: questionId,
		correct_answer: correctAnswer
	});
}

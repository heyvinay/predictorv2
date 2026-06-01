/**
 * Pure helpers backing the bonus-questions UI in the entries wizard and
 * the /rules page. Extracted from `+page.svelte` so vitest can exercise
 * them without rendering the component.
 *
 * Keep these functions side-effect-free — they're called from Svelte
 * reactive blocks where any mutation would create dependency loops.
 */

/**
 * Count how many questions in `questionIds` have a non-empty answer.
 *
 * Critical: filters `answers` against `questionIds` so a stale draft
 * holding entries for removed question IDs (e.g. legacy `best_player`
 * after the 2026-06-01 trim) cannot inflate the numerator past the
 * denominator. Without this filter the wizard counter could read
 * "6 of 4 answered" — confusing and a bug-report magnet.
 */
export function countAnsweredQuestions(
	questionIds: string[],
	answers: Map<string, string>
): number {
	const liveIds = new Set(questionIds);
	let n = 0;
	for (const [id, v] of answers.entries()) {
		if (liveIds.has(id) && v?.trim()) n++;
	}
	return n;
}

/**
 * Dynamic border class for a bonus card — thick red when empty, thick
 * green when answered. Matches the visual language users get on the
 * fixture-card surface (`bg-base-100`) but uses border-2 + state color
 * instead of border + neutral. Pure: takes a boolean so it's trivial to
 * test and reuse from the rules-page preview if we ever add one.
 */
export function bonusBorderClass(answered: boolean): string {
	return answered ? 'border-success/60' : 'border-error/60';
}

/**
 * Filter the 48-team pool down to teams NOT in the FIFA top_n list.
 * Used by the Dark Horse dropdown — "team outside FIFA top {top_n}
 * that progresses furthest."
 *
 * `allTeams` is the wizard's reactive list of every team appearing in
 * the YAML's `groups:` section (TBD entries already excluded upstream).
 */
export function filterTeamsOutsideTopN(allTeams: string[], topTeams: string[]): string[] {
	const top = new Set(topTeams);
	return allTeams.filter((t) => !top.has(t));
}

/**
 * Return the FIFA top_n list intersected with the active competition's
 * teams. Used by the Bottlers dropdown — "team inside FIFA top {top_n}
 * eliminated earliest."
 *
 * Intersection guards against the rare case where the YAML's
 * `fifa_top_teams` lists a team that didn't qualify or was renamed
 * (e.g. Italy in 2026). Order preserved from `topTeams` so the dropdown
 * shows teams in FIFA-rank order, not alphabetical.
 */
export function filterTeamsInTopN(allTeams: string[], topTeams: string[]): string[] {
	const allSet = new Set(allTeams);
	return topTeams.filter((t) => allSet.has(t));
}

/**
 * Question shape this helper validates against. Loose typing — we accept
 * any object with `input_type` so the function works against both the API
 * response shape and any future internal shape variants.
 */
type ValidatableBonusQuestion = {
	input_type: 'team' | 'player' | 'team_outside_top_n' | 'team_in_top_n' | string;
};

/**
 * Decide whether a stored answer is still a structurally-valid pick for
 * its question given the current FIFA top_n list and (optionally) the
 * pool of teams in the active tournament.
 *
 * Why this exists: when input_type was tightened from `team` (any) to
 * `team_outside_top_n` or `team_in_top_n` on 2026-06-01, draft answers
 * saved under the old contract can become un-pickable. The select
 * renders blank because the option list no longer includes the stored
 * value, but bonusAnswers.get(id) still returns the stale string — the
 * counter and border-class would count it as "answered" without this
 * filter. Treating an invalid stored value as "no answer" is the
 * pragmatic UX: red border + accurate counter prompts the user to pick
 * a fresh option from the new list.
 *
 * `allTeams` is optional because at first-paint of the wizard the
 * `groupFixtures` reactive may not have populated yet. Pass it when you
 * have it (tightens the `team` and `team_outside_top_n` checks); skip
 * it to validate against fifa_top_teams alone.
 */
export function validateBonusAnswer(
	question: ValidatableBonusQuestion,
	answer: string,
	fifaTopTeams: string[],
	allTeams?: string[]
): boolean {
	if (!answer?.trim()) return false;
	const inTopN = fifaTopTeams.includes(answer);
	switch (question.input_type) {
		case 'team_outside_top_n':
			// Must be a real tournament team AND not in fifa_top_teams.
			if (inTopN) return false;
			return allTeams ? allTeams.includes(answer) : true;
		case 'team_in_top_n':
			// Must be a top_n team that's also in the tournament. The
			// outer fifa_top_teams membership is the binding constraint;
			// the allTeams intersection catches the (rare) case of a
			// top-10 team that didn't qualify (Italy in 2026).
			if (!inTopN) return false;
			return allTeams ? allTeams.includes(answer) : true;
		case 'team':
			// Any tournament team is valid; without `allTeams` we accept.
			return allTeams ? allTeams.includes(answer) : true;
		case 'player':
			// No structural validator beyond non-empty (squad lookup TBD).
			return true;
		default:
			// Unknown input_type — be conservative, treat as invalid so
			// the user is prompted to re-pick rather than silently kept
			// with a value the new wizard can't render.
			return false;
	}
}

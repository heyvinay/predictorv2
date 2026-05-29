/**
 * Title-similarity deduplication for the aggregated news feed.
 *
 * When BBC and Guardian both cover the same story (which they do
 * frequently), their headlines are usually 80-95% identical — different
 * wording on the verb, sometimes a different scoreline format. A simple
 * exact-string match misses these; full embedding-similarity is overkill
 * for top-12 lists. Jaccard on word-token sets sits in the right zone:
 * cheap, deterministic, and good enough to dedupe paraphrases.
 *
 * Algorithm:
 *   1. Normalize titles (lowercase, drop punctuation, drop tokens < 3
 *      chars to filter "of", "in", "vs"-ish noise).
 *   2. For each item, compare its token set to each previously-kept
 *      item. If Jaccard ≥ threshold, treat as duplicate.
 *   3. When a duplicate is detected, keep whichever item has the
 *      EARLIER publishedAt — that's the original story; later "matches"
 *      are usually re-posts.
 *
 * O(n²) is fine — caller passes at most ~30 items at a time.
 */
import type { NewsItem } from './types';

/** Default similarity threshold. 0.85 ≈ "same headline, minor wording
 *  differences"; 0.70 starts catching same-topic-different-angle pairs
 *  (which we DON'T want to dedupe — two perspectives on the same story
 *  is editorially valuable). */
export const DEFAULT_DEDUPE_THRESHOLD = 0.85;

/** Public API — returns a deduplicated copy of `items` in input order. */
export function dedupeByTitle(
	items: NewsItem[],
	threshold: number = DEFAULT_DEDUPE_THRESHOLD
): NewsItem[] {
	const kept: Array<{ item: NewsItem; tokens: Set<string> }> = [];

	for (const item of items) {
		const tokens = tokenize(item.title);
		// Titles too short to tokenize meaningfully — just keep, can't
		// confidently call them duplicates.
		if (tokens.size === 0) {
			kept.push({ item, tokens });
			continue;
		}

		const dupIndex = kept.findIndex((k) => jaccard(tokens, k.tokens) >= threshold);

		if (dupIndex === -1) {
			kept.push({ item, tokens });
		} else {
			// Duplicate found — keep whichever is earlier (the original
			// publication, not the re-post).
			const existing = kept[dupIndex].item;
			if (toEpoch(item.publishedAt) < toEpoch(existing.publishedAt)) {
				kept[dupIndex] = { item, tokens };
			}
		}
	}

	return kept.map((k) => k.item);
}

/** Lowercase → strip non-alphanumeric → tokenize on whitespace → drop
 *  tokens of length ≤ 2. Returns a Set for cheap intersection later.
 *  Exported for unit testing. */
export function tokenize(title: string): Set<string> {
	return new Set(
		title
			.toLowerCase()
			.replace(/[^a-z0-9\s]/g, ' ')
			.split(/\s+/)
			.filter((w) => w.length > 2)
	);
}

/** Jaccard similarity between two token sets:
 *  |A ∩ B| / |A ∪ B|. Returns 0 if either side is empty. Exported for
 *  unit testing. */
export function jaccard(a: Set<string>, b: Set<string>): number {
	if (a.size === 0 || b.size === 0) return 0;
	let intersection = 0;
	for (const token of a) {
		if (b.has(token)) intersection++;
	}
	const union = a.size + b.size - intersection;
	return union === 0 ? 0 : intersection / union;
}

function toEpoch(iso: string): number {
	const t = new Date(iso).getTime();
	return Number.isNaN(t) ? Number.POSITIVE_INFINITY : t;
}

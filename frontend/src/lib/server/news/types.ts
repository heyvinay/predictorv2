/**
 * Shared types for the server-side news aggregator. Lives under
 * `$lib/server` so the implementation never ships to the browser bundle
 * (feed URLs, parser logic, dedupe rules stay server-only).
 */

/** A normalized news article from any source. Featured items are
 *  rendered as the large "Featured" card in `FromTheTouchline.svelte`;
 *  the rest fill the 5-card grid. */
export type NewsItem = {
	/** Human-readable source name shown as the eyebrow chip, e.g.
	 *  "BBC Sport" or "Guardian Football". */
	source: string;
	/** Headline. */
	title: string;
	/** Absolute URL to the article. */
	link: string;
	/** ISO 8601 UTC timestamp — caller converts to local time for
	 *  display via Intl. */
	publishedAt: string;
	/** Short description / lede if the feed provides one. */
	excerpt?: string;
	/** Article hero image URL if the feed exposes one via
	 *  `<media:thumbnail>`, `<media:content type="image/*">`, or
	 *  `<enclosure type="image/*">`. */
	imageUrl?: string;
	/** True for the single most-recent item, used to render the larger
	 *  "Featured" card on the landing page. Set by `fetchAllNews()`. */
	featured?: boolean;
};

/** Feed source declaration. */
export type FeedSource = {
	/** Display name shown in the source chip. */
	name: string;
	/** Public RSS / Atom URL. */
	url: string;
	/** Feed format. v1 only handles RSS 2.0; Atom support is wired in
	 *  the parser interface but not yet implemented. */
	format: 'rss2' | 'atom';
};

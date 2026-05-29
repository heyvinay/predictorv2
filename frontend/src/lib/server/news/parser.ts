/**
 * RSS / Atom parser using fast-xml-parser. Produces normalized
 * `NewsItem[]` from raw feed XML. Tolerant of common feed quirks:
 *
 *  - Single `<item>` rendered as object vs array — forced to array.
 *  - Image embedded via `<media:thumbnail url="...">`, `<media:content
 *    url="..." medium="image">`, or `<enclosure url="..." type="image/*">`
 *    depending on the source.
 *  - HTML in `<description>` — stripped to plain text for the excerpt.
 *  - RFC 822 `<pubDate>` — converted to ISO 8601 UTC for serialization.
 *
 * Errors per item are swallowed — a single malformed entry doesn't kill
 * the whole feed. Errors at the XML level (truly malformed XML) throw
 * up to the caller, which logs and treats the feed as empty for that
 * round.
 */
import { XMLParser } from 'fast-xml-parser';
import type { NewsItem } from './types';

interface MediaWithUrl {
	'@_url'?: string;
	'@_type'?: string;
	'@_medium'?: string;
}

interface RssItem {
	title?: string;
	link?: string;
	description?: string;
	pubDate?: string;
	'media:thumbnail'?: MediaWithUrl | MediaWithUrl[];
	'media:content'?: MediaWithUrl | MediaWithUrl[];
	enclosure?: MediaWithUrl | MediaWithUrl[];
}

interface RssChannel {
	item?: RssItem | RssItem[];
}

interface Rss2Doc {
	rss?: { channel?: RssChannel };
}

const parser = new XMLParser({
	ignoreAttributes: false,
	attributeNamePrefix: '@_',
	// Force <item> to always parse as an array so callers don't branch on
	// "is it an object or a list?" for single-item feeds.
	isArray: (name) => name === 'item' || name === 'entry'
});

/** Parse a raw feed XML string into normalized news items. */
export function parseFeed(xml: string, source: string, format: 'rss2' | 'atom'): NewsItem[] {
	if (format !== 'rss2') {
		// Atom support deferred — v1 feeds (BBC + Guardian) are both RSS 2.0.
		// Adding Atom is a parallel parse path; tracked under "Deferred".
		return [];
	}

	const doc = parser.parse(xml) as Rss2Doc;
	// `isArray` is configured to force `item` into an array, but TS can't
	// see that constraint — defensively narrow at the boundary.
	const rawItem = doc?.rss?.channel?.item;
	const items: RssItem[] = Array.isArray(rawItem) ? rawItem : rawItem ? [rawItem] : [];

	const out: NewsItem[] = [];
	for (const raw of items) {
		const item = mapRssItem(raw, source);
		if (item) out.push(item);
	}
	return out;
}

/** Map one RSS 2.0 `<item>` element to a NewsItem. Returns `null` if
 *  the item is missing required fields (title + link) — caller filters. */
function mapRssItem(raw: RssItem, source: string): NewsItem | null {
	const title = sanitizeTitle(raw.title);
	const link = (raw.link ?? '').trim();
	if (!title || !link) return null;

	const publishedAt = parsePubDate(raw.pubDate);

	return {
		source,
		title,
		link,
		publishedAt,
		excerpt: extractExcerpt(raw.description),
		imageUrl: extractImageUrl(raw)
	};
}

/** Strip whitespace and the occasional CDATA wrapper that lingers
 *  around `<title>`. fast-xml-parser handles CDATA internally most of
 *  the time, but defensively trim. */
function sanitizeTitle(t: string | undefined): string {
	if (!t) return '';
	return t.replace(/<!\[CDATA\[|\]\]>/g, '').trim();
}

/** RFC 822 → ISO 8601 UTC. Returns the original input if parsing fails
 *  (so downstream sort still has SOMETHING to compare), or epoch if the
 *  string is missing entirely. */
function parsePubDate(input: string | undefined): string {
	if (!input) return new Date(0).toISOString();
	const d = new Date(input);
	if (Number.isNaN(d.getTime())) return new Date(0).toISOString();
	return d.toISOString();
}

/** Strip HTML tags, collapse whitespace, and truncate to 240 chars so
 *  the excerpt fits the featured-card layout without overflowing.
 *  Plain-text only — no markdown / no entity decoding beyond what the
 *  browser will do downstream. */
function extractExcerpt(html: string | undefined): string | undefined {
	if (!html) return undefined;
	const stripped = html
		.replace(/<!\[CDATA\[|\]\]>/g, '')
		.replace(/<[^>]*>/g, ' ')
		.replace(/&nbsp;/g, ' ')
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/\s+/g, ' ')
		.trim();
	if (!stripped) return undefined;
	if (stripped.length <= 240) return stripped;
	return stripped.slice(0, 237).trimEnd() + '…';
}

/** Find a hero image URL via any of the three common image conventions.
 *  Returns the first match; precedence is `media:thumbnail` (BBC's
 *  convention), then `media:content` (Guardian's convention), then
 *  `enclosure` (older RSS spec). */
function extractImageUrl(raw: RssItem): string | undefined {
	const candidates: Array<MediaWithUrl | MediaWithUrl[] | undefined> = [
		raw['media:thumbnail'],
		raw['media:content'],
		raw.enclosure
	];

	for (const candidate of candidates) {
		if (!candidate) continue;
		const list = Array.isArray(candidate) ? candidate : [candidate];
		for (const c of list) {
			const url = c?.['@_url']?.trim();
			if (!url) continue;
			// For media:content / enclosure, require an image MIME type
			// (BBC's media:content sometimes lists video). For
			// media:thumbnail, assume image.
			const type = c['@_type']?.toLowerCase() ?? '';
			const medium = c['@_medium']?.toLowerCase() ?? '';
			if (type.startsWith('image/') || medium === 'image' || (!type && !medium)) {
				return url;
			}
		}
	}
	return undefined;
}

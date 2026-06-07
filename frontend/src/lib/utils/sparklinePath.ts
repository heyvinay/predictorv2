/**
 * Sparkline path builder. Pure — caller owns scale and styling.
 *
 * Ranks are inverted (lower number = better). Maps rank 1 to the top of
 * the chart, rank `maxRank` to the bottom, with optional padding bands.
 *
 * Returns:
 *   linePath  — SVG path "d" attribute for the trend line
 *   fillPath  — same but closed at the baseline, used for the area fill
 *   points    — [[x, y], ...] in chart coordinates for marker placement
 *
 * Ported from upstream's `lib/stubs/panini.ts:sparklinePath`. Promoted out
 * of stubs/ since the visualization is real.
 */

export interface SparklineOptions {
	width: number;
	height: number;
	padTop?: number;
	padBottom?: number;
}

export interface SparklineResult {
	linePath: string;
	fillPath: string;
	points: Array<[number, number]>;
}

export function sparklinePath(
	ranks: number[],
	maxRank: number,
	opts: SparklineOptions
): SparklineResult {
	const { width, height, padTop = 0.05, padBottom = 0.05 } = opts;
	if (ranks.length < 2) return { linePath: '', fillPath: '', points: [] };
	const points: Array<[number, number]> = ranks.map((r, i) => {
		const x = (i / (ranks.length - 1)) * width;
		const norm = (r - 1) / Math.max(1, maxRank - 1);
		const y = padTop * height + norm * (1 - padTop - padBottom) * height;
		return [x, y];
	});
	const linePath = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
	const fillPath = `${linePath} L${width},${height} L0,${height} Z`;
	return { linePath, fillPath, points };
}

import { describe, expect, it } from 'vitest';
import { formatGroupCell, formatKoCell } from './pointsCellFormat';

describe('formatGroupCell', () => {
	it('renders no pill (dash) when the fixture has not banked points', () => {
		expect(formatGroupCell(null).pill).toBeNull();
		expect(formatGroupCell(undefined).pill).toBeNull();
	});

	it('renders EXACT pill with rarity star when exact + rarity', () => {
		const cell = formatGroupCell({ base: 15, base_kind: 'exact', rarity: 3, total: 18 });
		expect(cell.pill).toEqual({
			label: 'EXACT',
			display: '+18',
			tone: 'exact',
			showRarityStar: true,
			rarityTitle: 'Includes +3 rarity bonus'
		});
	});

	it('renders RESULT pill without star when no rarity', () => {
		const cell = formatGroupCell({ base: 5, base_kind: 'result', rarity: 0, total: 5 });
		expect(cell.pill).toEqual({
			label: 'RESULT',
			display: '+5',
			tone: 'result',
			showRarityStar: false,
			rarityTitle: null
		});
	});

	it('renders MISS 0 for a played miss', () => {
		const cell = formatGroupCell({ base: 0, base_kind: 'miss', rarity: 0, total: 0 });
		expect(cell.pill).toEqual({
			label: 'MISS',
			display: '0',
			tone: 'miss',
			showRarityStar: false,
			rarityTitle: null
		});
	});
});

describe('formatKoCell', () => {
	it('renders a dash for third_place / unseeded fixtures', () => {
		expect(formatKoCell(20, 2, false).line).toBeNull();
	});

	it('templates the stage points — never a hardcoded +5', () => {
		expect(formatKoCell(20, 2, true).line).toEqual({
			breakdown: '+20×2:',
			total: 40,
			tone: 'full'
		});
		expect(formatKoCell(50, 1, true).line).toEqual({
			breakdown: '+50×1:',
			total: 50,
			tone: 'half'
		});
		expect(formatKoCell(30, 0, true).line).toEqual({
			breakdown: '+30×0:',
			total: 0,
			tone: 'none'
		});
	});
});

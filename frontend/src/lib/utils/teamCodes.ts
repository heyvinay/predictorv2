/**
 * Map team names (as stored in Fixture.home_team / away_team) to FIFA
 * three-letter codes used by flag swatches.
 *
 * Falls back to the first three letters uppercased for teams not in
 * the table. Expand the map as new teams appear in real fixture data.
 */

const TEAM_CODES: Record<string, string> = {
	Argentina: 'ARG',
	Brazil: 'BRA',
	France: 'FRA',
	Spain: 'ESP',
	Germany: 'GER',
	Italy: 'ITA',
	Portugal: 'POR',
	Netherlands: 'NED',
	Croatia: 'CRO',
	England: 'ENG',
	Uruguay: 'URU',
	Morocco: 'MAR',
	Japan: 'JPN',
	Mexico: 'MEX',
	'South Korea': 'KOR',
	Korea: 'KOR',
	'United States': 'USA',
	USA: 'USA',
	Poland: 'POL',
	Belgium: 'BEL',
	Switzerland: 'SUI',
	Senegal: 'SEN',
	Ghana: 'GHA',
	Tunisia: 'TUN',
	Egypt: 'EGY',
	Iran: 'IRN',
	Australia: 'AUS',
	Canada: 'CAN',
	'Saudi Arabia': 'KSA',
	Denmark: 'DEN',
	Colombia: 'COL',
	Nigeria: 'NGA',
	Ecuador: 'ECU',
	Serbia: 'SRB'
};

export function teamCode(name: string | null | undefined): string {
	if (!name) return '???';
	if (TEAM_CODES[name]) return TEAM_CODES[name];
	// Strip non-letters and uppercase the first 3 chars.
	const compact = name.replace(/[^A-Za-z]/g, '');
	return compact.slice(0, 3).toUpperCase() || '???';
}

/**
 * Map team names (as stored in Fixture.home_team / away_team) to FIFA
 * three-letter codes used by flag swatches.
 *
 * Falls back to the first three letters uppercased for teams not in
 * the table. Expand the map as new teams appear in real fixture data.
 */

const TEAM_CODES: Record<string, string> = {
	// Group A–L confirmed teams (live in fixtures DB)
	Algeria: 'ALG',
	Argentina: 'ARG',
	Australia: 'AUS',
	Austria: 'AUT',
	Belgium: 'BEL',
	'Bosnia-Herzegovina': 'BIH',
	Brazil: 'BRA',
	Canada: 'CAN',
	'Cape Verde Islands': 'CPV',
	Colombia: 'COL',
	'Congo DR': 'COD',
	Croatia: 'CRO',
	Curaçao: 'CUW',
	Curacao: 'CUW',
	Czechia: 'CZE',
	Denmark: 'DEN',
	Ecuador: 'ECU',
	Egypt: 'EGY',
	England: 'ENG',
	France: 'FRA',
	Germany: 'GER',
	Ghana: 'GHA',
	Haiti: 'HAI',
	Iran: 'IRN',
	Iraq: 'IRQ',
	Italy: 'ITA',
	'Ivory Coast': 'CIV',
	Jamaica: 'JAM',
	Japan: 'JPN',
	Jordan: 'JOR',
	Mexico: 'MEX',
	Morocco: 'MAR',
	Netherlands: 'NED',
	'New Zealand': 'NZL',
	Nigeria: 'NGA',
	Norway: 'NOR',
	Panama: 'PAN',
	Paraguay: 'PAR',
	Poland: 'POL',
	Portugal: 'POR',
	Qatar: 'QAT',
	'Saudi Arabia': 'KSA',
	Scotland: 'SCO',
	Senegal: 'SEN',
	Serbia: 'SRB',
	'South Africa': 'RSA',
	'South Korea': 'KOR',
	Korea: 'KOR',
	Spain: 'ESP',
	Sweden: 'SWE',
	Switzerland: 'SUI',
	Tunisia: 'TUN',
	Turkey: 'TUR',
	'United States': 'USA',
	USA: 'USA',
	Uruguay: 'URU',
	Uzbekistan: 'UZB',
	// Additional teams from the YAML that may appear if qualifiers shift
	Cameroon: 'CMR',
	Chile: 'CHI',
	'Costa Rica': 'CRC',
	'Northern Ireland': 'NIR',
	Peru: 'PER',
	Venezuela: 'VEN',
	Wales: 'WAL'
};

export function teamCode(name: string | null | undefined): string {
	if (!name) return 'TBD';
	// Knockout fixtures whose teams aren't determined yet hold a
	// `slot:<stage>:<ext_id>:<side>` placeholder string. Detecting these
	// here means EVERY surface that uses teamCode() (BracketChip,
	// TeamName-via-forceCode, MatchdayPill) shows "TBD" instead of
	// a slot-derived three-letter code like "SLO".
	if (name.startsWith('slot:')) return 'TBD';
	if (TEAM_CODES[name]) return TEAM_CODES[name];
	// Strip non-letters and uppercase the first 3 chars.
	const compact = name.replace(/[^A-Za-z]/g, '');
	return compact.slice(0, 3).toUpperCase() || 'TBD';
}

// FIFA 3-letter → ISO 3166-1 alpha-2 (with UK home-nation subdivisions).
// Used by PnFlag to look up the flag-icons SVG path. Every FIFA code
// emitted by TEAM_CODES above must have an entry here.
const FIFA_TO_ISO: Record<string, string> = {
	ALG: 'dz',
	ARG: 'ar',
	AUS: 'au',
	AUT: 'at',
	BEL: 'be',
	BIH: 'ba',
	BRA: 'br',
	CAN: 'ca',
	CHI: 'cl',
	CIV: 'ci',
	CMR: 'cm',
	COD: 'cd',
	COL: 'co',
	CPV: 'cv',
	CRC: 'cr',
	CRO: 'hr',
	CUW: 'cw',
	CZE: 'cz',
	DEN: 'dk',
	ECU: 'ec',
	EGY: 'eg',
	ENG: 'gb-eng',
	ESP: 'es',
	FRA: 'fr',
	GER: 'de',
	GHA: 'gh',
	HAI: 'ht',
	IRN: 'ir',
	IRQ: 'iq',
	ITA: 'it',
	JAM: 'jm',
	JOR: 'jo',
	JPN: 'jp',
	KOR: 'kr',
	KSA: 'sa',
	MAR: 'ma',
	MEX: 'mx',
	NED: 'nl',
	NGA: 'ng',
	NIR: 'gb-nir',
	NOR: 'no',
	NZL: 'nz',
	PAN: 'pa',
	PAR: 'py',
	PER: 'pe',
	POL: 'pl',
	POR: 'pt',
	QAT: 'qa',
	RSA: 'za',
	SCO: 'gb-sct',
	SEN: 'sn',
	SRB: 'rs',
	SUI: 'ch',
	SWE: 'se',
	TUN: 'tn',
	TUR: 'tr',
	URU: 'uy',
	USA: 'us',
	UZB: 'uz',
	VEN: 've',
	WAL: 'gb-wls'
};

export function flagIsoCode(fifaCode: string | null | undefined): string | undefined {
	if (!fifaCode) return undefined;
	return FIFA_TO_ISO[fifaCode];
}

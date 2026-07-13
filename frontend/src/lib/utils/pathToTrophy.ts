/** Human-readable stage label, shared by the Path to the Trophy outcome
 *  table (outcomeGrid.ts's raw stage keys) and anywhere else a bracket
 *  stage needs prose. */
export function stageLabel(stage: string): string {
	switch (stage) {
		case 'round_of_32':
			return 'round of 32';
		case 'round_of_16':
			return 'round of 16';
		case 'quarter_final':
			return 'quarter-final';
		case 'semi_final':
			return 'semi-final';
		case 'final':
			return 'final';
		default:
			return stage.replace(/_/g, ' ');
	}
}

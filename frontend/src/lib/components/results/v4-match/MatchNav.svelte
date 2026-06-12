<script lang="ts">
	/** Back · prev/next pager · position counter. Arrows disable at round
	 *  edges (no cross-round wrap, spec §8.6). Full team names < 480px
	 *  compress to FIFA three-letter codes ("MEX v KOR"). */
	import type { Fixture } from '$types';
	import { displayTeamName, isPlaceholderTeam } from '$lib/utils/teamName';
	import { teamCode } from '$lib/utils/teamCodes';

	export let roundId: string;
	export let roundLabel: string;
	export let index: number;
	export let count: number;
	export let prevFixture: Fixture | null;
	export let nextFixture: Fixture | null;
	export let onPrev: () => void;
	export let onNext: () => void;

	const label = (f: Fixture | null) =>
		f ? `${displayTeamName(f.home_team)} vs ${displayTeamName(f.away_team)}` : null;
	const code = (t: string) => (isPlaceholderTeam(t) ? 'TBD' : teamCode(t));
	const codeLabel = (f: Fixture | null) =>
		f ? `${code(f.home_team)} v ${code(f.away_team)}` : null;
</script>

<div
	class="flex flex-wrap items-center justify-between gap-2 rounded-full border border-base-300/55 bg-base-200 px-2 py-1.5"
>
	<a
		href={`/results?round=${roundId}`}
		class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-bold text-base-content/70 transition-colors hover:bg-base-300/40 hover:text-base-content"
	>
		<span class="text-[14px] leading-none">←</span> Back to Results
	</a>

	<div class="flex items-center gap-1.5">
		<button
			class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors {prevFixture
				? 'text-base-content/70 hover:bg-base-300/40 hover:text-base-content'
				: 'cursor-not-allowed text-base-content/25'}"
			disabled={!prevFixture}
			title={label(prevFixture) ?? 'First fixture of this round'}
			aria-label="Previous fixture"
			on:click={onPrev}
		>
			<span class="text-[15px] leading-none">←</span>
			<span class="hidden max-w-[140px] truncate min-[480px]:inline">
				{label(prevFixture) ?? 'Round start'}
			</span>
			{#if codeLabel(prevFixture)}
				<span class="min-[480px]:hidden">{codeLabel(prevFixture)}</span>
			{/if}
		</button>

		<div class="flex flex-col items-center px-2">
			<span class="font-display text-[13px] leading-tight">{index + 1} of {count}</span>
			<span class="text-[9px] font-extrabold uppercase tracking-[0.12em] text-base-content/55"
				>{roundLabel}</span
			>
		</div>

		<button
			class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors {nextFixture
				? 'text-base-content/70 hover:bg-base-300/40 hover:text-base-content'
				: 'cursor-not-allowed text-base-content/25'}"
			disabled={!nextFixture}
			title={label(nextFixture) ?? 'Last fixture of this round'}
			aria-label="Next fixture"
			on:click={onNext}
		>
			<span class="hidden max-w-[140px] truncate min-[480px]:inline">
				{label(nextFixture) ?? 'Round end'}
			</span>
			{#if codeLabel(nextFixture)}
				<span class="min-[480px]:hidden">{codeLabel(nextFixture)}</span>
			{/if}
			<span class="text-[15px] leading-none">→</span>
		</button>
	</div>
</div>

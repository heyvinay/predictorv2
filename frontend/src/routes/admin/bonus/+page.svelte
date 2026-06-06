<script lang="ts">
	// Bonus question answers — admin resolves each question by entering the
	// correct team(s). Moved out of /admin/+page.svelte in v2.160.0.
	// Backend writes via setBonusAnswer; loadBonusAnswers gives the
	// current state + per-question metadata (label, points, input_type).
	import { onDestroy, onMount } from 'svelte';
	import { listBonusAnswers, setBonusAnswer, type BonusAnswerView } from '$api/bonus';
	import { pageTitle } from '$lib/stores/pageTitle';

	let bonusAnswerViews: BonusAnswerView[] = [];
	let bonusDrafts: Map<string, string> = new Map();
	let savingQId: string | null = null;
	let bonusError: string | null = null;

	async function loadBonusAnswers() {
		try {
			bonusAnswerViews = await listBonusAnswers();
		} catch (e) {
			bonusError = e instanceof Error ? e.message : 'Failed to load bonus answers';
		}
	}

	function draftFor(view: BonusAnswerView): string {
		// Ties supported: comma-separated. Show the joined list when no
		// draft is in flight; otherwise show the in-progress edit.
		return bonusDrafts.get(view.question_id) ?? view.correct_answers.join(', ') ?? '';
	}

	function setDraft(qid: string, value: string) {
		const next = new Map(bonusDrafts);
		next.set(qid, value);
		bonusDrafts = next;
	}

	async function handleSaveBonusAnswer(view: BonusAnswerView) {
		const rawValue = draftFor(view).trim();
		const values = rawValue
			.split(',')
			.map((s) => s.trim())
			.filter((s) => s.length > 0);
		savingQId = view.question_id;
		bonusError = null;
		try {
			const updated = await setBonusAnswer(view.question_id, values);
			bonusAnswerViews = bonusAnswerViews.map((v) =>
				v.question_id === view.question_id ? updated : v
			);
			const next = new Map(bonusDrafts);
			next.delete(view.question_id);
			bonusDrafts = next;
		} catch (e) {
			bonusError = e instanceof Error ? e.message : 'Failed to save bonus answer';
		} finally {
			savingQId = null;
		}
	}

	$: bonusByCategory = (() => {
		const groups: Record<string, BonusAnswerView[]> = {
			group_stage: [],
			top_flop: [],
			awards: []
		};
		for (const v of bonusAnswerViews) {
			(groups[v.category] ?? (groups[v.category] = [])).push(v);
		}
		return groups;
	})();

	const BONUS_CATEGORY_LABEL: Record<string, string> = {
		group_stage: 'Group stage',
		// Internal literal `top_flop` preserved; UI label is the longer phrase.
		top_flop: 'Knockout Stage — Top / Flop',
		awards: 'Awards'
	};

	function fmtResolved(iso: string | null): string {
		if (!iso) return 'Not resolved';
		const d = new Date(iso);
		return `Resolved ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
	}

	$: resolvedCount = bonusAnswerViews.filter((v) => v.correct_answers.length > 0).length;

	onMount(async () => {
		pageTitle.set('Bonus Question Answers');
		await loadBonusAnswers();
	});

	onDestroy(() => {
		pageTitle.set('');
	});
</script>

<svelte:head>
	<title>Bonus Answers · Admin · Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6">
	<section class="rounded-xl border bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">
			Bonus Question Answers
			<span class="text-xs text-base-content/40">
				· {resolvedCount} of {bonusAnswerViews.length} resolved
			</span>
		</h2>
		{#if bonusError}<div class="alert alert-error text-sm mb-3">{bonusError}</div>{/if}
		{#each ['group_stage', 'top_flop', 'awards'] as cat}
			{@const items = bonusByCategory[cat] ?? []}
			{#if items.length > 0}
				<h3 class="text-sm font-display uppercase tracking-wide mt-4 mb-2">
					{BONUS_CATEGORY_LABEL[cat]}
				</h3>
				{#each items as v (v.question_id)}
					<div class="flex items-center gap-3 py-2 flex-wrap">
						<div class="flex-1 min-w-[200px]">
							<div class="text-sm font-medium">{v.label}</div>
							<div class="text-xs text-base-content/40">
								{v.points} pts · {v.input_type} · {fmtResolved(v.resolved_at)}
							</div>
						</div>
						<input
							type="text"
							class="input input-bordered input-sm flex-1 min-w-[160px]"
							placeholder={v.correct_answers.length > 0
								? ''
								: 'Enter correct answer (comma-separate for ties)…'}
							value={draftFor(v)}
							on:input={(e) => setDraft(v.question_id, e.currentTarget.value)}
						/>
						{#if v.correct_answers.length > 0}
							<span
								class="badge badge-success"
								title="Currently saved: {v.correct_answers.join(', ')}"
							>
								✓ {v.correct_answers.join(', ')}
							</span>
						{:else}
							<span class="badge badge-ghost">Unset</span>
						{/if}
						<button
							class="btn btn-xs btn-outline"
							type="button"
							on:click={() => handleSaveBonusAnswer(v)}
							disabled={savingQId === v.question_id}
						>
							{savingQId === v.question_id ? 'Saving…' : 'Save'}
						</button>
					</div>
				{/each}
			{/if}
		{/each}
		<p class="text-xs text-base-content/50 mt-3">
			★ Saving a correct answer awards bonus points to every player whose pick matches
			(case- and accent-insensitive). Leave blank to un-resolve a question.
		</p>
	</section>
</div>

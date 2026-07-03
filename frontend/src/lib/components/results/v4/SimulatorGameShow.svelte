<!--
	SimulatorGameShow — "Who Wants to Be a Millionaire"-style unlock gate for
	the what-if bracket simulator (v2.194.x). Renders as a fixed overlay +
	scrim, same chrome convention as `SmartFillModal.svelte` / other predictions
	modals (fixed inset-0, backdrop click + Escape both dismiss).

	State machine (single component, `{#if}`-driven — no display:none tabs):

	  INTRO   → headline + "Start challenge" button. Fires
	            `simulator_gate_opened` on mount.
	  ACTIVE  → fetches a question, renders it + 4 options + a 15s countdown
	            ring + a 50:50 lifeline. Clicking an option locks it in
	            (brief amber state), submits to the server, and the SERVER'S
	            verdict (not any client-side guess) decides correct/incorrect.
	  FAIL    → "sent off" copy + Try again (re-fetches a fresh question).
	  SUCCESS → confetti + "GOAL!" copy + a button that fires
	            `simulator_unlocked`, dispatches `unlocked`, and closes.

	50:50 lifeline — clicking it hits a dedicated server endpoint
	(`POST /simulator/challenge/fifty-fifty`) that returns two option
	indexes the server knows are WRONG for the current question. The client
	greys them out and DISABLES clicks on them, so the classic Millionaire
	mechanic works properly: two wrong answers vanish, the correct answer
	is guaranteed to be in the remaining pair. `correct_index` still never
	leaves the server; only two of the three wrong indexes do, so a
	two-way choice remains for the player.

	Dispatches:
	  - unlocked: void   — challenge won, gate should flip open
	  - close: void      — user dismissed (backdrop/Escape/close button)
-->
<script lang="ts">
	import { createEventDispatcher, onMount, onDestroy } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import { track } from '$lib/analytics';
	import {
		getSimulatorChallenge,
		getSimulatorFiftyFifty,
		submitSimulatorChallenge
	} from '$lib/api/simulator';
	import { ApiResponseError } from '$lib/api/client';
	import type { ChallengeQuestion } from '$lib/types/simulator';

	export let open = false;

	const dispatch = createEventDispatcher<{ unlocked: void; close: void }>();

	// `reveal` is the brief window (REVEAL_MS) after grading where the
	// locked-in option flashes green/red, before advancing to the
	// full-screen success/fail verdict.
	type GameState =
		| 'intro'
		| 'loading'
		| 'active'
		| 'grading'
		| 'reveal'
		| 'fail'
		| 'success'
		| 'error';

	let state: GameState = 'intro';
	let question: ChallengeQuestion | null = null;
	let errorMessage = '';

	// Timer
	const TIMEOUT_MS = 15000;
	let questionStartedAt = 0;
	let remainingMs = TIMEOUT_MS;
	let timerHandle: ReturnType<typeof setInterval> | null = null;
	let revealHandle: ReturnType<typeof setTimeout> | null = null;

	// Selection / grading state
	let selectedIndex: number | null = null;
	let lockedInIndex: number | null = null;
	/** Server verdict for the LOCKED-IN option only. The `/challenge`
	 *  response carries no answer key (by design — the correct index never
	 *  ships to the client), so we can never reveal which OTHER option was
	 *  right. We only ever colour the option the player actually chose. */
	let gradeResult: 'win' | 'lose' | null = null;
	/** How long the per-option green/red flash lingers before the
	 *  full-screen verdict. */
	const REVEAL_MS = 900;
	let greyedOut = new Set<number>();
	let usedFiftyFifty = false;
	let timedOut = false;

	// Reduced-motion — surfaced once via matchMedia; consumed by the
	// countdown-pulse class binding and the confetti burst.
	let prefersReducedMotion = false;

	$: reachedCritical = state === 'active' && remainingMs <= 5000;
	// `class:` reads a plain reactive var (not a store access inside a
	// function) so this re-triggers correctly — see CLAUDE.md frontend
	// gotchas re: class:foo={someFn()} not tracking store reads.
	$: pulseTimer = reachedCritical && !prefersReducedMotion;

	// Circular ring geometry
	const RING_RADIUS = 26;
	const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
	$: ringProgress = Math.max(0, Math.min(1, remainingMs / TIMEOUT_MS));
	$: ringOffset = RING_CIRCUMFERENCE * (1 - ringProgress);

	onMount(() => {
		if (typeof window !== 'undefined' && window.matchMedia) {
			prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		}
	});

	onDestroy(() => {
		stopTimer();
	});

	// Fire the funnel-entry event once when the gate first renders open.
	let hasFiredGateOpened = false;
	$: if (open && !hasFiredGateOpened) {
		hasFiredGateOpened = true;
		track('simulator_gate_opened');
	}

	function stopTimer() {
		if (timerHandle !== null) {
			clearInterval(timerHandle);
			timerHandle = null;
		}
		if (revealHandle !== null) {
			clearTimeout(revealHandle);
			revealHandle = null;
		}
	}

	function resetRoundState() {
		selectedIndex = null;
		lockedInIndex = null;
		gradeResult = null;
		greyedOut = new Set();
		usedFiftyFifty = false;
		timedOut = false;
		errorMessage = '';
	}

	async function startChallenge() {
		resetRoundState();
		state = 'loading';
		try {
			question = await getSimulatorChallenge();
			state = 'active';
			questionStartedAt = performance.now();
			remainingMs = TIMEOUT_MS;
			stopTimer();
			timerHandle = setInterval(() => {
				const elapsed = performance.now() - questionStartedAt;
				remainingMs = Math.max(0, TIMEOUT_MS - elapsed);
				if (remainingMs <= 0) {
					stopTimer();
					handleTimeout();
				}
			}, 100);
		} catch (e) {
			state = 'error';
			errorMessage = e instanceof Error ? e.message : 'Could not load the challenge.';
		}
	}

	/** 50:50 lifeline — spends a round-trip to the server, which knows the
	 *  answer key and returns two indexes it can guarantee are wrong for
	 *  this question. Those two are greyed out AND disabled (see the
	 *  option button's `disabled` binding below), so the classic Millionaire
	 *  mechanic works: two wrong answers vanish, the correct answer is
	 *  guaranteed to be in the surviving pair. `correct_index` still never
	 *  leaves the server — only two of the three wrong indexes come back.
	 *
	 *  Optimistically flip `usedFiftyFifty` before the fetch so the button
	 *  disables immediately (no double-click); revert if the request fails
	 *  so the player can try again. */
	async function applyFiftyFifty() {
		if (usedFiftyFifty || !question || lockedInIndex !== null) return;
		usedFiftyFifty = true;
		try {
			const wrong = await getSimulatorFiftyFifty(question.question_id);
			greyedOut = new Set(wrong);
		} catch {
			// Network / auth blip — let the user try again rather than
			// silently burning their lifeline.
			usedFiftyFifty = false;
		}
	}

	function handleTimeout() {
		if (lockedInIndex !== null) return; // already submitting/submitted
		timedOut = true;
		void submitAttempt(-1, TIMEOUT_MS + 1);
	}

	function handleOptionClick(index: number) {
		if (state !== 'active' || lockedInIndex !== null) return;
		if (greyedOut.has(index)) return; // 50:50 eliminated this one — server says it's wrong
		selectedIndex = index;
		lockedInIndex = index;
		stopTimer();
		const elapsedMs = Math.round(performance.now() - questionStartedAt);
		void submitAttempt(index, elapsedMs);
	}

	async function submitAttempt(answerIndex: number, elapsedMs: number) {
		if (!question) return;
		state = 'grading';
		const questionId = question.question_id;
		try {
			const result = await submitSimulatorChallenge({
				question_id: questionId,
				answer_index: answerIndex,
				elapsed_ms: elapsedMs
			});
			track('simulator_challenge_submitted', {
				result: result.unlocked ? 'win' : timedOut ? 'timeout' : 'fail',
				used_5050: usedFiftyFifty
			});
			// Flash the locked-in option green/red for REVEAL_MS, then
			// advance to the full-screen verdict. On a timeout there's no
			// locked-in option to colour, so we skip straight through.
			gradeResult = result.unlocked ? 'win' : 'lose';
			if (lockedInIndex !== null) {
				state = 'reveal';
				revealHandle = setTimeout(() => {
					revealHandle = null;
					state = result.unlocked ? 'success' : 'fail';
				}, REVEAL_MS);
			} else {
				state = result.unlocked ? 'success' : 'fail';
			}
		} catch (e) {
			track('simulator_challenge_submitted', {
				result: 'fail',
				used_5050: usedFiftyFifty
			});
			state = 'error';
			errorMessage =
				e instanceof ApiResponseError ? e.detail : 'Something went wrong grading that answer.';
		}
	}

	function handleUnlockClaim() {
		track('simulator_unlocked');
		dispatch('unlocked');
		handleClose();
	}

	function handleClose() {
		stopTimer();
		dispatch('close');
	}

	function handleKey(e: KeyboardEvent) {
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			handleClose();
		}
	}

	function optionLetter(index: number): string {
		return ['A', 'B', 'C', 'D'][index] ?? '?';
	}

	/** Per-option button styling. Kept in the script (not inline in the
	 *  template) so `state` here is the full GameState union — the previous
	 *  inline version narrowed `state` to 'active' | 'grading' and made the
	 *  'success'/'fail' branches unreachable dead code.
	 *
	 *  Colouring is keyed ONLY on the locked-in index + the server's
	 *  win/lose verdict for that option. The client never learns which
	 *  OTHER option was correct (no answer key is shipped), so we never
	 *  attempt to highlight a "correct" option the player didn't pick.
	 *    - grading  → amber "locking in" flash on the chosen option
	 *    - reveal   → green (win) / red (lose) on the chosen option
	 *    - greyed   → faded (50:50 lifeline)
	 *    - default  → interactive base */
	// Reactive dependencies (`state`, `lockedInIndex`, `gradeResult`,
	// `greyedOut`) are passed EXPLICITLY so Svelte's template dep-tracker
	// re-invokes this per option button when any of them change. A function
	// that read those from its enclosing scope would look correct but would
	// NOT re-evaluate — same class of bug as the resolvedOf/scenario reactivity
	// fix on SimulatorBracket. In particular, without this the "greyed on
	// 50:50" styling never applies visually even though the click is disabled.
	function optionClass(
		index: number,
		s: GameState,
		locked: number | null,
		grade: 'win' | 'lose' | null,
		greyed: Set<number>
	): string {
		const isLockedIn = locked === index;
		if (isLockedIn && s === 'grading') {
			return 'border-warning bg-warning/20';
		}
		if (isLockedIn && s === 'reveal') {
			return grade === 'win'
				? 'border-success bg-success/20'
				: 'border-error bg-error/20';
		}
		if (greyed.has(index)) {
			return 'border-base-300/40 bg-base-300/10 opacity-40';
		}
		return 'border-base-300/60 bg-base-300/20 hover:bg-base-300/40';
	}
</script>

<svelte:window on:keydown={handleKey} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="simgame-title"
	>
		<!-- Backdrop -->
		<button
			type="button"
			class="absolute inset-0 cursor-default bg-black/70 backdrop-blur-sm"
			tabindex="-1"
			aria-label="Close dialog"
			on:click={handleClose}
			transition:fade={{ duration: 150 }}
		></button>

		<!-- Dialog -->
		<div
			class="stadium-card no-glow w-full max-w-md p-6"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			{#if state === 'intro'}
				<div class="text-center" in:fade={{ duration: 150 }}>
					<div class="mb-3 text-5xl leading-none" aria-hidden="true">🔮</div>
					<h2 id="simgame-title" class="mb-2 font-display text-xl font-bold">
						A new feature has appeared.
					</h2>
					<p class="mb-6 text-sm text-base-content/70">
						Prove your worth to unlock the crystal ball.
					</p>
					<button type="button" class="btn btn-primary min-h-11 w-full" on:click={startChallenge}>
						Start challenge
					</button>
					<button
						type="button"
						class="btn btn-ghost mt-2 min-h-11 w-full"
						on:click={handleClose}
					>
						Not now
					</button>
				</div>
			{:else if state === 'loading'}
				<div class="flex flex-col items-center gap-3 py-8 text-center">
					<span class="loading loading-spinner loading-lg text-primary" aria-hidden="true"></span>
					<p class="text-sm text-base-content/60">Loading your challenge…</p>
				</div>
			{:else if state === 'error'}
				<div class="text-center" in:fade={{ duration: 150 }}>
					<div class="mb-3 text-4xl leading-none" aria-hidden="true">⚠️</div>
					<h2 id="simgame-title" class="mb-2 font-display text-lg font-bold">
						Couldn't load that.
					</h2>
					<p class="mb-6 text-sm text-base-content/70">{errorMessage}</p>
					<button type="button" class="btn btn-primary min-h-11 w-full" on:click={startChallenge}>
						Try again
					</button>
				</div>
			{:else if (state === 'active' || state === 'grading' || state === 'reveal') && question}
				<div in:fade={{ duration: 150 }}>
					<div class="mb-4 flex items-center justify-between gap-3">
						<h2 id="simgame-title" class="font-display text-base font-bold leading-snug">
							{question.question}
						</h2>
						<!-- Countdown ring -->
						<svg
							viewBox="0 0 64 64"
							class="h-14 w-14 flex-shrink-0 {pulseTimer ? 'animate-pulse' : ''}"
							aria-hidden="true"
						>
							<circle
								cx="32"
								cy="32"
								r={RING_RADIUS}
								fill="none"
								stroke="currentColor"
								stroke-width="5"
								class="text-base-300"
							/>
							<circle
								cx="32"
								cy="32"
								r={RING_RADIUS}
								fill="none"
								stroke="currentColor"
								stroke-width="5"
								stroke-linecap="round"
								stroke-dasharray={RING_CIRCUMFERENCE}
								stroke-dashoffset={ringOffset}
								transform="rotate(-90 32 32)"
								class={reachedCritical ? 'text-error' : 'text-primary'}
							/>
							<text
								x="32"
								y="37"
								text-anchor="middle"
								class="fill-current font-mono text-[16px] font-semibold {reachedCritical
									? 'text-error'
									: 'text-base-content'}"
							>
								{Math.ceil(remainingMs / 1000)}
							</text>
						</svg>
					</div>

					<div class="mb-4 grid grid-cols-1 gap-2">
						{#each question.options as optionText, index (index)}
							<button
								type="button"
								class="flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors {optionClass(
									index,
									state,
									lockedInIndex,
									gradeResult,
									greyedOut
								)}"
								disabled={state !== 'active' || greyedOut.has(index)}
								on:click={() => handleOptionClick(index)}
							>
								<span
									class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/15 font-mono text-[11px] font-bold text-primary"
									aria-hidden="true"
								>
									{optionLetter(index)}
								</span>
								<span>{optionText}</span>
							</button>
						{/each}
					</div>

					<button
						type="button"
						class="btn btn-outline btn-sm"
						disabled={usedFiftyFifty || state !== 'active'}
						on:click={applyFiftyFifty}
					>
						50:50 lifeline
					</button>
				</div>
			{:else if state === 'fail'}
				<div class="text-center" in:fade={{ duration: 150 }}>
					<div class="mb-3 text-5xl leading-none" aria-hidden="true">🟥</div>
					<h2 id="simgame-title" class="mb-2 font-display text-xl font-bold text-error">
						Red card! Sent off.
					</h2>
					<p class="mb-6 text-sm text-base-content/70">
						{timedOut
							? "Time's up — even VAR couldn't save that one."
							: 'Wrong answer — that shot went well over the bar.'}
					</p>
					<button type="button" class="btn btn-primary min-h-11 w-full" on:click={startChallenge}>
						Try again
					</button>
					<button
						type="button"
						class="btn btn-ghost mt-2 min-h-11 w-full"
						on:click={handleClose}
					>
						Maybe later
					</button>
				</div>
			{:else if state === 'success'}
				<div class="relative text-center" in:fade={{ duration: 150 }}>
					{#if !prefersReducedMotion}
						<div class="confetti-burst" aria-hidden="true">
							{#each Array(18) as _, i (i)}
								<span
									class="confetti-piece"
									style="--i: {i}; --hue: {(i * 47) % 360}deg;"
								></span>
							{/each}
						</div>
					{/if}
					<div class="mb-3 text-5xl leading-none" aria-hidden="true">🥅</div>
					<h2 id="simgame-title" class="mb-2 font-display text-xl font-bold text-success">
						GOAL! Access granted.
					</h2>
					<p class="mb-6 text-sm text-base-content/70">
						The crystal ball is yours. Go run some what-ifs.
					</p>
					<button type="button" class="btn btn-primary min-h-11 w-full" on:click={handleUnlockClaim}>
						Enter the simulator
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.confetti-burst {
		position: absolute;
		inset: 0;
		overflow: visible;
		pointer-events: none;
	}

	.confetti-piece {
		position: absolute;
		top: 10%;
		left: 50%;
		width: 8px;
		height: 8px;
		background: hsl(var(--hue) 85% 60%);
		border-radius: 2px;
		opacity: 0;
		animation: confetti-fall 900ms ease-out forwards;
		animation-delay: calc(var(--i) * 18ms);
		transform: translate(-50%, 0) rotate(0deg);
	}

	@keyframes confetti-fall {
		0% {
			opacity: 1;
			transform: translate(calc(-50% + (var(--i) - 9) * 12px), -10px) rotate(0deg);
		}
		100% {
			opacity: 0;
			transform: translate(calc(-50% + (var(--i) - 9) * 22px), 140px) rotate(340deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.confetti-piece {
			animation: none;
			opacity: 0;
		}
	}
</style>

<!--
	FaqSection — "Frequently Asked" inline FAQ.

	Sits between HowItWorks and EntryDepth on the landing. Native
	<details>/<summary> accordions for keyboard accessibility — no JS,
	no Svelte transitions needed. Closed by default so the section stays
	scannable; users expand the question they care about.

	Pattern matches /rules: copy lives inline. The single "Read the full
	rules →" link in the section header points readers at the deeper
	explanation; each individual answer is self-contained.
-->
<script lang="ts">
	import { track } from '$lib/analytics';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';

	type FaqItem = { q: string; a: string };

	// Q&A inline. Edit answers directly here when copy changes; same
	// flow as /rules. Keep answers ~40–60 words — long enough to be
	// useful, short enough to scan after expand.
	const faqs: FaqItem[] = [
		{
			q: 'Can I change my picks after submitting?',
			a: "Yes — your picks stay editable until 2 hours before the tournament starts. All entries will be locked after the deadline — no exceptions!"
		},
		{
			q: "What if I don't know much about football?",
			a: "You're in good company — many top finishers aren't experts. You can use the AI-assisted Smart Fill for your picks with sensible defaults. The smart picks are based on bookmaker odds, form, historical patterns, and FIFA rankings. One button, two minutes, done. You can leave it as-is, tweak only the matches you have opinions on, or submit multiple entries with different strategies."
		},
		{
			q: 'Who do I pay the €5 per entry fee to?',
			a: "Atlas and JMFA staff: see the email you received with payment details. Everyone else: contact the person who brought you to the pool. Unpaid entries will be disabled and won't be eligible for the prize. Each sheet costs just €5 — 1 sheet €5, 2 sheets €10, 3 sheets €15, and so on. You can submit as many sheets as you want, and share the link with as many people as you like."
		},
		{
			q: 'Who can play?',
			a: "Anyone with an invite. The pool is for Atlas, JMFA staff, and their invitees — their family and friends. If someone in the pool shared the link with you, you're welcome to join."
		},
		{
			q: 'How is the prize money distributed?',
			a: "The prize fund is typically split as follows: 65% to the overall winner, 20% to the Group Stage winner, and the rest to a charity chosen by the organisers."
		},
		{
			q: 'Which charity are we donating to?',
			a: "TBD — the organisers will pick a charity before the tournament kickoff. An announcement will be posted on the website."
		},
		{
			q: 'I signed up — what next? How do I follow my points and leaderboard?',
			a: "Three steps. (1) Hit 'Enter your predictions' — click on the Entries tab in the nav — to make your picks. (2) Pay your fee for each submission, then sit back and enjoy the games. (3) Once the tournament kicks off, your standings will be updated live on the Leaderboard tab, and individual match scores on the Results tab. Points update within minutes of each match finishing."
		}
	];

	function onRulesLinkClick() {
		track('rules_link_clicked', { placement: 'faq_section' });
	}

	function onToggle(question: string) {
		// Fire once per expand interaction. We don't differentiate
		// expand vs collapse — both are signal that this question
		// caught the user's eye.
		track('cta_clicked', {
			placement: 'faq_section',
			cta_label: 'faq_toggle',
			question
		});
	}
</script>

<div class="bg-base-100">
	<div class="max-w-5xl mx-auto mobile-padding py-20 sm:py-24">
		<header class="mb-8">
			<h2 class="font-hero text-3xl sm:text-4xl tracking-wide inline-block">FREQUENTLY ASKED</h2>
			<div class="h-0.5 w-24 bg-primary mt-2"></div>
			<p class="text-sm text-base-content/70 mt-3">
				Quick answers for the curious.
				<a
					href="/rules"
					class="text-primary hover:opacity-80 transition-opacity ml-1"
					on:click={onRulesLinkClick}
				>
					Read the full rules →
				</a>
			</p>
		</header>

		<!--
			2-column grid on md+, single column on mobile. `items-start` is
			critical: without it, row height tracks the tallest cell so
			expanding one card would visually inflate its row-mate's
			whitespace. With items-start, each card stays at its natural
			height and only the expanded card grows.

			Odd-count handling: with 7 questions the final item would sit
			alone in row 4. We span it across both columns so it reads as
			a "post-signup finale" rather than a stranded card.
		-->
		<div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 items-start">
			{#each faqs as faq, i (faq.q)}
				<details
					class="group rounded-xl bg-base-200 border border-base-300/60
						hover:border-primary/30 transition-colors overflow-hidden
						{i === faqs.length - 1 ? 'md:col-span-2' : ''}"
					on:toggle={() => onToggle(faq.q)}
				>
					<summary
						class="flex items-center justify-between gap-4 cursor-pointer
							px-5 py-4 list-none
							font-display text-base sm:text-lg text-base-content
							group-hover:text-primary transition-colors"
					>
						<span>{faq.q}</span>
						<ChevronDown
							size={18}
							strokeWidth={2}
							class="shrink-0 text-base-content/50 group-open:rotate-180 transition-transform duration-200"
						/>
					</summary>
					<div class="px-5 pb-5 -mt-1">
						<p class="text-sm sm:text-[15px] text-base-content/75 leading-relaxed">
							{faq.a}
						</p>
					</div>
				</details>
			{/each}
		</div>
	</div>
</div>

<style>
	/* Hide the default disclosure triangle in Firefox / older browsers.
	   Chrome respects `list-style: none` via the `list-none` class above
	   on the <summary>, but Firefox needs the explicit `::-webkit-details-marker`
	   override + `display: list-item` removal. */
	summary {
		display: block;
	}
	summary::-webkit-details-marker {
		display: none;
	}
</style>

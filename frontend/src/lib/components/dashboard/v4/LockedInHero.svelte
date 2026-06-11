<script lang="ts">
	/** Post-deadline holding hero (v2.166.0).
	 *
	 *  Shown to signed-in non-admins between the deadline passing and
	 *  the admin flipping the go-live switch — the window where the
	 *  close-out clean-up runs. Calm, celebratory, no CTA: there is
	 *  nothing for the user to do but wait for the first whistle. */
	import { user } from '$stores/auth';
	import { submittedEntries } from '$stores/entries';
	import { loadEntries } from '$stores/entries';

	let requested = false;
	$: if ($user?.id && !requested) {
		requested = true;
		void loadEntries($user.id);
	}

	$: n = $submittedEntries.length;
</script>

<section class="mx-auto flex min-h-[55vh] max-w-[640px] flex-col items-center justify-center px-4 py-16 text-center">
	<div
		class="relative w-full overflow-hidden rounded-box border border-primary/30 bg-base-200 px-6 py-10 sm:px-10"
	>
		<div
			class="pointer-events-none absolute inset-0"
			style="background: radial-gradient(120% 160% at 50% -30%, hsl(var(--p) / 0.14), transparent 60%);"
		></div>
		<div class="relative flex flex-col items-center gap-3">
			<span class="text-3xl" aria-hidden="true">🔒</span>
			<h1 class="font-hero text-4xl tracking-[0.03em] text-base-content sm:text-5xl">
				You're locked in
			</h1>
			<p class="max-w-[440px] text-[14px] leading-relaxed text-base-content/70">
				The pool is closed — every submitted entry is final{n > 0
					? ` (you have ${n} ${n === 1 ? 'entry' : 'entries'} in the running)`
					: ''}. Your dashboard, results and the live table go live before the
				first whistle.
			</p>
			<p class="text-[11.5px] font-semibold uppercase tracking-[0.14em] text-base-content/45">
				Sealing the pool · see you at kickoff
			</p>
		</div>
	</div>
</section>

import { writable } from 'svelte/store';

/** Open/closed state for the Rate &amp; feedback side panel. Mirrors
 *  `supportPanel.ts` — a single global boolean any surface can flip. */
export const feedbackOpen = writable<boolean>(false);

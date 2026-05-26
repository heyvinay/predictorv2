import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export const THEMES = ['light', 'premium-night'] as const;

export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = 'premium-night';
const STORAGE_KEY = 'predictor:theme';

function readInitial(): Theme {
	if (!browser) return DEFAULT_THEME;
	const saved = localStorage.getItem(STORAGE_KEY);
	return saved && (THEMES as readonly string[]).includes(saved) ? (saved as Theme) : DEFAULT_THEME;
}

export const theme = writable<Theme>(readInitial());

if (browser) {
	theme.subscribe((value) => {
		document.documentElement.setAttribute('data-theme', value);
		try {
			localStorage.setItem(STORAGE_KEY, value);
		} catch {
			// localStorage unavailable (private mode etc.) — theme still applies for this session
		}
	});
}

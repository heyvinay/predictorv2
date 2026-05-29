/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				'display': ['Manrope', 'system-ui', 'sans-serif'],
				'sans': ['Inter', 'system-ui', 'sans-serif'],
				'mono': ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
				// Editorial hero font — landing page hero headlines only.
				// Manrope remains the system display font; reach for `font-hero`
				// when you want a loud, broadcast-poster moment.
				'hero': ['"Bebas Neue"', 'Impact', 'sans-serif'],
			},
			backgroundImage: {
				// Subtle 50px vertical stripes — barely-visible texture for
				// hero canvases. Theme-neutral (white at 2% alpha).
				'pitch-pattern': 'repeating-linear-gradient(90deg, transparent, transparent 50px, rgba(255,255,255,0.02) 50px, rgba(255,255,255,0.02) 100px)',
				// Ambient gold radial — soft champagne wash from the top.
				// Matches the new premium-night/day aesthetic.
				'stadium-glow': 'radial-gradient(ellipse at top, rgba(212, 175, 55, 0.10) 0%, transparent 50%)',
			},
			boxShadow: {
				// Champagne-gold glow — primary accent halo on CTAs and
				// "you" highlights. Hex matches premium-night primary (#D4AF37).
				'glow-gold': '0 0 20px rgba(212, 175, 55, 0.30)',
				'card': '0 4px 20px rgba(0, 0, 0, 0.4)',
			},
			animation: {
				'slide-up': 'slide-up 0.4s ease-out',
				'fade-in': 'fade-in 0.3s ease-out',
				'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
				'score-pop': 'score-pop 0.2s ease-out',
				'shimmer': 'shimmer 2s linear infinite',
			},
			keyframes: {
				'slide-up': {
					'0%': { opacity: '0', transform: 'translateY(10px)' },
					'100%': { opacity: '1', transform: 'translateY(0)' },
				},
				'fade-in': {
					'0%': { opacity: '0' },
					'100%': { opacity: '1' },
				},
				'pulse-soft': {
					'0%, 100%': { opacity: '1' },
					'50%': { opacity: '0.7' },
				},
				'score-pop': {
					'0%': { transform: 'scale(1)' },
					'50%': { transform: 'scale(1.1)' },
					'100%': { transform: 'scale(1)' },
				},
				'shimmer': {
					'0%': { backgroundPosition: '-200% 0' },
					'100%': { backgroundPosition: '200% 0' },
				},
			},
		}
	},
	plugins: [require('daisyui')],
	daisyui: {
		themes: [
			{
				// Dark theme — sports-broadcast editorial.
				// Gold-on-navy, mint success, amber/red urgency.
				'premium-night': {
					'primary': '#D4AF37',           // gold — CTAs, brand, accents
					'primary-content': '#0B1329',   // ink on gold
					'secondary': '#1C2541',         // premium navy (used by DaisyUI btn-secondary)
					'secondary-content': '#E2E8F0',
					'accent': '#D4AF37',            // same gold for accent semantics
					'accent-content': '#0B1329',
					'neutral': '#1E293B',           // tooltip / btn-neutral bg
					'neutral-content': '#E2E8F0',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',           // mint — exact score
					'success-content': '#F8FAFC',
					'warning': '#D97706',           // amber — lock / outcome
					'warning-content': '#F8FAFC',
					'error':   '#B91C1C',           // red — miss
					'error-content': '#F8FAFC',
					'base-100': '#0B1329',          // canvas
					'base-200': '#1C2541',          // surface / cards
					'base-300': '#2A3552',          // divider / borders
					'base-content': '#E2E8F0',     // body ink
					'--rounded-box': '0.875rem',   // 14px cards
					'--rounded-btn': '0.625rem',   // 10px buttons
					'--rounded-badge': '0.5rem',   // 8px pills
					'--border-btn': '1px',
				},
			},
			{
				// Light theme — same voice, lighter canvas.
				// Deeper gold (B8941F) for AA contrast on ice — use #D4AF37
				// only for large fills/marks.
				'premium-day': {
					'primary': '#B8941F',
					'primary-content': '#0B1329',
					'secondary': '#1C2541',         // premium navy headers / chrome
					'secondary-content': '#F8FAFC',
					'accent': '#B8941F',
					'accent-content': '#F8FAFC',
					'neutral': '#1E293B',           // dark tooltip bg even on light canvas
					'neutral-content': '#F8FAFC',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',
					'success-content': '#F8FAFC',
					'warning': '#B45309',
					'warning-content': '#F8FAFC',
					'error':   '#B91C1C',
					'error-content': '#F8FAFC',
					'base-100': '#F8FAFC',          // ice canvas — NEVER pure #FFFFFF
					'base-200': '#FFFFFF',          // surface / cards
					'base-300': '#E2E8F0',          // slate-200 divider / borders
					'base-content': '#0B1329',     // navy ink
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
			{
				// Hybrid — premium-night chrome (applied in +layout.svelte) wrapping
				// a slightly-dimmed light body. base-200 sits LIGHTER than base-100
				// so cards/controls visually lift above the dim canvas.
				'hybrid': {
					'primary': '#B8941F',           // deeper gold for AA on light
					'primary-content': '#0B1329',
					'secondary': '#1C2541',
					'secondary-content': '#F8FAFC',
					'accent': '#B8941F',
					'accent-content': '#0B1329',
					'neutral': '#1E293B',
					'neutral-content': '#F8FAFC',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',
					'success-content': '#F8FAFC',
					'warning': '#B45309',
					'warning-content': '#F8FAFC',
					'error':   '#B91C1C',
					'error-content': '#F8FAFC',
					'base-100': '#E2E7F0',          // DIM canvas (body background)
					'base-200': '#FFFFFF',          // LIGHTER cards / controls
					'base-300': '#D3DBE7',          // divider
					'base-content': '#0B1329',
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
			{
				// VinDark — GitHub-flavoured dark theme. Palette is dachinat
				// (daisyui-themes/githubdark.css), with dark primary swapped to
				// canonical Primer #2f81f7 for a recognisably GitHub-blue accent.
				'vin-dark': {
					'primary': '#2f81f7',                                  // canonical Primer (overrides dachinat #106cd4)
					'primary-content': 'oklch(96% 0.018 272.314)',         // dachinat
					'secondary': '#ac81e9',                                // dachinat
					'secondary-content': 'oklch(94% 0.028 342.258)',
					'accent': '#36b4be',                                   // dachinat teal
					'accent-content': 'oklch(38% 0.063 188.416)',
					'neutral': '#5298e9',
					'neutral-content': 'oklch(92% 0.004 286.32)',
					'info': '#a2d4e7',
					'info-content': 'oklch(29% 0.066 243.157)',
					'success': '#2dac4a',
					'success-content': '#eee8d5',
					'warning': '#dfb457',
					'warning-content': 'oklch(41% 0.112 45.904)',
					'error': '#e9726a',
					'error-content': 'oklch(27% 0.105 12.094)',
					'base-100': '#0f1317',
					'base-200': '#161b22',
					'base-300': '#21252c',
					'base-content': '#dbe1e6',
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
			{
				// VinLight — GitHub-flavoured light theme. Palette transcribed
				// verbatim from dachinat daisyui-themes/githublight.css.
				'vin-light': {
					'primary': '#1067ce',
					'primary-content': '#e7e9ed',
					'secondary': '#7b4ed1',
					'secondary-content': 'oklch(29% 0.066 243.157)',
					'accent': '#da6147',                                   // dachinat orange
					'accent-content': 'oklch(28% 0.066 53.813)',
					'neutral': '#2f9b4f',
					'neutral-content': 'oklch(98% 0.001 106.423)',
					'info': '#52a3ee',
					'info-content': 'oklch(97% 0.013 236.62)',
					'success': '#2f9b4f',
					'success-content': 'oklch(98% 0.018 155.826)',
					'warning': '#d9b84f',
					'warning-content': 'oklch(98% 0.022 95.277)',
					'error': '#eb7a7c',
					'error-content': 'oklch(97% 0.013 17.38)',
					'base-100': '#e7e9ec',          // off-grey canvas (dachinat — NOT pure white)
					'base-200': '#dadee3',
					'base-300': '#c1c8cf',
					'base-content': '#292f36',
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
			{
				// VinHybrid — vin-dark chrome (applied in +layout.svelte) wrapping
				// a vin-light body. Body tokens are vin-light verbatim.
				'vin-hybrid': {
					'primary': '#1067ce',
					'primary-content': '#e7e9ed',
					'secondary': '#7b4ed1',
					'secondary-content': 'oklch(29% 0.066 243.157)',
					'accent': '#da6147',
					'accent-content': 'oklch(28% 0.066 53.813)',
					'neutral': '#2f9b4f',
					'neutral-content': 'oklch(98% 0.001 106.423)',
					'info': '#52a3ee',
					'info-content': 'oklch(97% 0.013 236.62)',
					'success': '#2f9b4f',
					'success-content': 'oklch(98% 0.018 155.826)',
					'warning': '#d9b84f',
					'warning-content': 'oklch(98% 0.022 95.277)',
					'error': '#eb7a7c',
					'error-content': 'oklch(97% 0.013 17.38)',
					'base-100': '#e7e9ec',
					'base-200': '#dadee3',
					'base-300': '#c1c8cf',
					'base-content': '#292f36',
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
		],
		darkTheme: 'premium-night'
	}
};

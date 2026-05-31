/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			// `warning` is a surface token (bg-warning/text-warning-content pair).
			// `warning-text` is the readable amber FOREGROUND token — use it as
			// `text-warning-text` on base canvases where bare `text-warning` would
			// vanish into the surface color. Channels live in app.css per theme.
			colors: {
				'warning-text': 'rgb(var(--warning-text) / <alpha-value>)',
			},
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
					'warning': '#221703',           // deep amber — tie-break / soft alert
					'warning-content': '#FDE68A',
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
				// Light theme — premium-night chrome (applied in +layout.svelte)
				// wraps a slightly-dimmed light body. base-200 sits LIGHTER than
				// base-100 so cards/controls visually lift above the dim canvas.
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
					'warning': '#FEF3C7',           // soft cream — light alert surface
					'warning-content': '#78350F',
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
		],
		darkTheme: 'premium-night'
	}
};

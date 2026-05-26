/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				'display': ['"Bebas Neue"', 'Impact', 'sans-serif'],
				'sans': ['"DM Sans"', 'system-ui', 'sans-serif'],
			},
			colors: {
				// Custom colors for win/loss indicators
				'win': '#22c55e',
				'loss': '#ef4444',
				'draw': '#f59e0b',
				// Stadium/sports palette
				'turf': '#0D9748',
				'pitch': '#0A7B3A',
				'gold': '#FFD700',
				'trophy': '#F5A623',
				'navy': '#1E3A5F',
			},
			backgroundImage: {
				'pitch-pattern': 'repeating-linear-gradient(90deg, transparent, transparent 50px, rgba(255,255,255,0.02) 50px, rgba(255,255,255,0.02) 100px)',
				'stadium-glow': 'radial-gradient(ellipse at top, rgba(13, 151, 72, 0.15) 0%, transparent 50%)',
				'hero-gradient': 'linear-gradient(135deg, rgba(13, 151, 72, 0.1) 0%, rgba(30, 58, 95, 0.1) 100%)',
			},
			boxShadow: {
				'glow-green': '0 0 20px rgba(13, 151, 72, 0.3)',
				'glow-gold': '0 0 20px rgba(245, 166, 35, 0.3)',
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
			'light',
			{
				'premium-night': {
					// Dark sports-broadcast palette: deep navy canvas with
					// champagne-gold CTAs and mint-green success.
					'primary': '#D4AF37',           // Champagne Gold
					'primary-content': '#0B1329',   // Navy on gold buttons
					'secondary': '#1C2541',         // Premium blue
					'secondary-content': '#F8FAFC',
					'accent': '#D4AF37',            // Gold accent
					'accent-content': '#0B1329',
					'neutral': '#1E293B',
					'neutral-content': '#CBD5E1',
					'base-100': '#0B1329',          // Midnight Navy canvas
					'base-200': '#1C2541',          // Raised surfaces
					'base-300': '#2A3552',          // Dividers
					'base-content': '#E2E8F0',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',
					'success-content': '#F8FAFC',
					'warning': '#D97706',
					'warning-content': '#F8FAFC',
					'error': '#B91C1C',
					'error-content': '#F8FAFC',
				}
			}
		],
		darkTheme: 'premium-night'
	}
};

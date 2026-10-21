/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./interfaces/web/templates/**/*.html",
    "./interfaces/web/static/**/*.js",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink:   { DEFAULT: '#09090b', 900: '#0c0c0f', 800: '#111114', 700: '#18181b', 600: '#27272a' },
        volt:  { DEFAULT: '#8b5cf6', 300: '#c4b5fd', 400: '#a78bfa', 600: '#7c3aed', 900: '#2e1065' },
        flare: { DEFAULT: '#d946ef', 300: '#f0abfc', 400: '#e879f9', 600: '#c026d3' },
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans:    ['"Instrument Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      transitionTimingFunction: {
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        'fade-up': {
          '0%':   { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [],
}

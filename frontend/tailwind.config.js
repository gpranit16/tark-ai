/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#000000",
        bgSecondary: "#050505",
        surface: "#0B0B0C",
        surface2: "#101011",
        border: "rgba(255, 255, 255, 0.05)",
        accent: {
          DEFAULT: "#C9A86A",
          highlight: "#E1C27A",
          muted: "#8E7548",
          soft: "#B89B62",
          hover: "#D6B574",
        },
        primary: {
          DEFAULT: "#C9A86A",
          foreground: "#080808"
        },
        muted: {
          DEFAULT: "#141415",
          foreground: "#77736D"
        }
      },
      fontFamily: {
        sans: ['Satoshi', 'system-ui', '-apple-system', 'sans-serif'],
        satoshi: ['Satoshi', 'sans-serif'],
        editorial: ['"General Sans"', 'Satoshi', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
      },
      letterSpacing: {
        luxury: '0.06em',
        tightest: '-0.035em',
      },
      boxShadow: {
        'gold-sm': '0 0 12px rgba(201,168,106,0.12)',
        'gold-md': '0 0 24px rgba(201,168,106,0.15)',
        'gold-lg': '0 0 48px rgba(201,168,106,0.12)',
      }
    },
  },
  plugins: [require('@tailwindcss/typography')],
}

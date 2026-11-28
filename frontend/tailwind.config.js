/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Pulled from the watercolor logo
        brand: {
          DEFAULT: '#C4818A',
          50:  '#FDF5F5',
          100: '#F9E9EA',
          200: '#F1CDCF',
          300: '#E6ACAF',
          400: '#D8929A',
          500: '#C4818A',
          600: '#A5666F',
          700: '#854F57',
          800: '#643B42',
          900: '#452A2F',
        },
        // Very light pink for backgrounds and borders
        blush: '#F9E9EA',
        // Near-black for body text and the logo script
        ink: '#1A1817',
        // Warm tan from the crochet hook in the logo
        tan: '#B59A6E',
      },
      fontFamily: {
        // Clean sans-serif body
        sans: ['Nunito', 'system-ui', 'sans-serif'],
        // Thin italic display font for headings; echoes the script in the logo
        display: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}

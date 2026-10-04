/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        st: {
          bg: '#ffffff',
          secondary: '#f0f2f6',
          text: '#31333f',
          muted: '#808495',
          primary: '#ff4b4b',
          'primary-hover': '#ff6c6c',
          border: 'rgba(49, 51, 63, 0.2)',
          'border-light': 'rgba(49, 51, 63, 0.1)',
          error: '#ff4b4b',
          warning: '#ffa421',
          info: '#1c83e1',
          success: '#21c354',
        },
      },
      fontFamily: {
        sans: ['"Source Sans 3"', '"Source Sans"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['"Source Code Pro"', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
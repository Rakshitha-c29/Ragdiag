/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#f0f4fa",
          100: "#dbe4f2",
          200: "#b8c9e4",
          300: "#8aa5d0",
          400: "#5b7db8",
          500: "#3d5f9e",
          600: "#2e4a82",
          700: "#253c6a",
          800: "#1b2d52",
          900: "#12203d",
          950: "#0b1428",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};

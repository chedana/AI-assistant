/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#171717",
        panel: "#212121",
        border: "#303030",
        muted: "#a3a3a3",
        text: "#f5f5f5",
        accent: "#10a37f"
      }
    },
  },
  plugins: [],
};

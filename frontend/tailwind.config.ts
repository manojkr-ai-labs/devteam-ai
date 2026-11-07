import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    borderRadius: {
      none: "0px",
      sm: "2px",
      DEFAULT: "2px",
      md: "2px",
      lg: "2px",
      xl: "2px",
      "2xl": "2px",
      "3xl": "2px",
      full: "2px",
    },
    boxShadow: {
      none: "none",
      sm: "none",
      DEFAULT: "none",
      md: "none",
      lg: "none",
      xl: "none",
      "2xl": "none",
      inner: "none",
    },
    extend: {
      colors: {
        canvas: "#f3f1ec",
        surface: "#faf9f6",
        ink: "#1a1814",
        graphite: "#6b6560",
        hairline: "#e3ddd4",
        pine: "#1e4d3a",
        brick: "#8c3a2f",
      },
      fontFamily: {
        sans: ["var(--font-plex)", "sans-serif"],
        newsreader: ["var(--font-newsreader)", "Georgia", "serif"],
        courier: ["var(--font-courier)", "monospace"],
      },
      fontSize: {
        section: ["11px", { lineHeight: "16px", letterSpacing: "0.12em" }],
        meta: ["13px", { lineHeight: "16px" }],
        prose: ["14px", { lineHeight: "22px" }],
        "row-title": ["17px", { lineHeight: "24px" }],
        display: ["40px", { lineHeight: "46px" }],
      },
      maxWidth: {
        column: "1120px",
      },
      spacing: {
        gutter: "24px",
        margin: "40px",
        header: "56px",
        row: "64px",
      },
    },
  },
  plugins: [],
};

export default config;

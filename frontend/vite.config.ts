import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "../static/react",
    emptyOutDir: true,
    minify: "oxc",
    lib: {
      entry: "src/django-entry.tsx",
      formats: ["es"],
      fileName: () => "global-exchange-react.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "global-exchange-react.[ext]",
        chunkFileNames: "chunks/[name]-[hash].js",
      },
    },
  },
});

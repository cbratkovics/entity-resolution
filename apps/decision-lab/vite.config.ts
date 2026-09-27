import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The GitHub Pages path of the lab. Override for a local preview with LAB_BASE=/ (or any path).
const base = process.env.LAB_BASE && process.env.LAB_BASE.length > 0 ? process.env.LAB_BASE : '/entity-resolution/lab/';

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    reportCompressedSize: true,
  },
  preview: { port: 4173, strictPort: true },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});

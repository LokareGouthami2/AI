import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API = process.env.WRITEAI_API_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target: API, changeOrigin: false } } },
  preview: { port: 4173, proxy: { '/api': { target: API, changeOrigin: false } } },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
    setupFiles: ['./src/__tests__/setup.js'],
  },
});

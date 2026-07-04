import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@industrial-brain/shared': path.resolve(__dirname, '../shared/ts/src/index.ts'),
    },
  },
  server: {
    port: Number(process.env.PORT) || 3000,
    // pnpm hoists workspace deps (e.g. @fontsource-variable/inter) to the repo-root
    // node_modules, which sits outside the frontend project root. Allow serving from
    // the workspace root so those assets load under `pnpm dev` instead of 403-ing.
    fs: { allow: ['..'] },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});

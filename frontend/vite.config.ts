import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: { port: 5173 },
  build: {
    // MapLibre is loaded only with the lazy map view; its 1 MB minified vendor
    // file is about 285 KB compressed. Keep Vite's warning focused on larger
    // unexpected chunks instead of this intentional map-engine chunk.
    chunkSizeWarningLimit: 1100,
  },
});

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import wasm from 'vite-plugin-wasm'
import topLevelAwait from 'vite-plugin-top-level-await'

// The Rerun web viewer ships as Wasm with top-level `await` and `import` of
// `.wasm` — both need these plugins to bundle under Vite.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), wasm(), topLevelAwait()],
  // Any browser with WebGPU (required by the viewer) also supports top-level
  // await natively, so target esnext rather than downleveling it.
  build: { target: 'esnext' },
  optimizeDeps: {
    // The Wasm viewer is large; don't let Vite try to pre-bundle / optimize it.
    exclude: ['@rerun-io/web-viewer', '@rerun-io/web-viewer-react'],
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})

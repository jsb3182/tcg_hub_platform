import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        id: '/',
        lang: 'ko',
        name: 'TCG 허브 카드 도감',
        short_name: 'TCG 허브',
        start_url: '/',
        display: 'standalone',
        background_color: '#fafaf7',
        theme_color: '#5b3fd0',
        icons: [192, 512].map(size => ({
          src: '/icon-' + size + '.png', sizes: size + 'x' + size,
          type: 'image/png', purpose: 'any maskable',
        })),
      },
      workbox: {
        globPatterns: ['**/*.{html,js,css}'],
        navigateFallback: '/index.html',
        // Protected navigation always reaches the origin and its Access policy.
        navigateFallbackAllowlist: [/^\/(?:\?.*)?$/, /^\/cards(?:\/\d+)?\/?(?:\?.*)?$/],
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: ({ sameOrigin, url, request }) =>
              sameOrigin && !request.headers.has('authorization') &&
              /^\/api\/v1\/(?:games|packs|cards(?:\/\d+)?)$/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'tcg-public-catalog-v1',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 80, maxAgeSeconds: 86400 },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            urlPattern: ({ sameOrigin, url }) =>
              sameOrigin && /^\/media\/.+\.webp$/i.test(url.pathname),
            handler: 'CacheFirst',
            options: {
              cacheName: 'tcg-public-media-v1',
              expiration: { maxEntries: 32, maxAgeSeconds: 7 * 86400 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8080', '/media': 'http://127.0.0.1:8080' },
  },
})

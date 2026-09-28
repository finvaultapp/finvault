// Build-only Vite plugin: emits /sw.js from sw/sw.js with the list of built files to precache and a
// version derived from their hashed names, so every deploy gets a fresh shell cache.
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

// Files from public/ that the shell needs offline.
const PUBLIC_FILES = ['/manifest.webmanifest', '/favicon.svg', '/icons/icon-192.png', '/icons/apple-touch-icon.png']

export default function serviceWorker() {
  return {
    name: 'finvault-sw',
    apply: 'build',
    generateBundle(_, bundle) {
      const built = Object.keys(bundle)
        .filter((f) => /\.(js|css)$/.test(f)) // fonts and images are cached on first use
        .map((f) => `/${f}`)
        .sort()
      const precache = ['/', ...built, ...PUBLIC_FILES]
      const template = readFileSync(join(here, 'sw.js'), 'utf8')
      const version = createHash('sha256').update(template).update(precache.join('\n')).digest('hex').slice(0, 12)
      const source = template
        .replace("'__FV_VERSION__'", JSON.stringify(version))
        .replace('[/* __FV_PRECACHE__ */]', JSON.stringify(precache))
      this.emitFile({ type: 'asset', fileName: 'sw.js', source })
    },
  }
}

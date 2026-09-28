// Renders the FinVault app icons (PWA manifest + apple-touch-icon) from the sorting-case mark in
// src/components/Logo.jsx: a 27x23 case with rounded corners, two vertical and one horizontal divider
// (six pigeonholes) and one amber letter. No dependencies: shapes are drawn with signed distance fields
// (so edges are anti-aliased) and written as PNG with node:zlib.
//
//   node scripts/make-icons.mjs        -> public/icons/*.png
//
// The mark's geometry below mirrors Logo.jsx (32-unit viewBox). If the logo changes, change it here too.
import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const TEAL = [0x1f, 0x5e, 0x57] // frame
const WHITE = [0xff, 0xff, 0xff] // frame-ink
const AMBER = [0xe3, 0xa4, 0x3a] // tray

// Signed distance to a rounded rectangle centred at (cx, cy) with half-size (hw, hh) and radius r.
function sdRoundRect(x, y, cx, cy, hw, hh, r) {
  const qx = Math.abs(x - cx) - (hw - r)
  const qy = Math.abs(y - cy) - (hh - r)
  const ox = Math.max(qx, 0)
  const oy = Math.max(qy, 0)
  return Math.hypot(ox, oy) + Math.min(Math.max(qx, qy), 0) - r
}
const sdRect = (x, y, x0, y0, x1, y1) => sdRoundRect(x, y, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0)

// The mark, in Logo.jsx units. Returns [whiteDistance, amberDistance].
function mark(u, v) {
  const outer = Math.abs(sdRoundRect(u, v, 16, 16, 13.5, 11.5, 2)) - 1 // stroke width 2
  const v1 = sdRect(u, v, 10.5, 5, 12.5, 27)
  const v2 = sdRect(u, v, 19.5, 5, 21.5, 27)
  const h = sdRect(u, v, 3, 15, 29, 17)
  const letter = sdRect(u, v, 13.5, 8.5, 18.5, 13.5)
  return [Math.min(outer, v1, v2, h), letter]
}

const cover = (d, px) => Math.min(1, Math.max(0, 0.5 - d / px)) // distance in units, px = units per pixel

// tile: 'rounded' (transparent corners) or 'full' (full-bleed, for maskable and iOS).
// markSize: how many pixels the 32-unit logo box spans.
function render(size, { tile, markSize }) {
  const out = Buffer.alloc(size * size * 4)
  const k = markSize / 32 // pixels per unit
  const off = (size - markSize) / 2
  const radius = size * 0.22
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const x = px + 0.5
      const y = py + 0.5
      const bg = tile === 'full' ? 1 : cover(sdRoundRect(x, y, size / 2, size / 2, size / 2, size / 2, radius), 1)
      const [dw, da] = mark((x - off) / k, (y - off) / k)
      const w = cover(dw * k, 1)
      const a = cover(da * k, 1)
      let rgb = TEAL.map((c, i) => c * (1 - w) + WHITE[i] * w)
      rgb = rgb.map((c, i) => c * (1 - a) + AMBER[i] * a)
      const alpha = Math.max(bg, 0) // the mark sits inside the tile
      const o = (py * size + px) * 4
      out[o] = Math.round(rgb[0]); out[o + 1] = Math.round(rgb[1]); out[o + 2] = Math.round(rgb[2])
      out[o + 3] = Math.round(alpha * 255)
    }
  }
  return png(size, size, out)
}

const CRC = new Uint32Array(256).map((_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})
function crc32(buf) {
  let c = 0xffffffff
  for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td))
  return Buffer.concat([len, td, crc])
}
function png(w, h, rgba) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4)
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0 // 8-bit RGBA
  const raw = Buffer.alloc((w * 4 + 1) * h)
  for (let y = 0; y < h; y++) {
    raw[y * (w * 4 + 1)] = 0 // filter: none
    rgba.copy(raw, y * (w * 4 + 1) + 1, y * w * 4, (y + 1) * w * 4)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0)),
  ])
}

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons')
mkdirSync(dir, { recursive: true })
const icons = {
  // "any" icons: a rounded teal tile, the mark at about 60% of the width (29 of 32 units).
  'icon-192.png': render(192, { tile: 'rounded', markSize: 192 * 0.66 }),
  'icon-512.png': render(512, { tile: 'rounded', markSize: 512 * 0.66 }),
  // Maskable: full bleed, mark kept inside the 80% safe circle (half-diagonal 17.7 units <= 0.36 * size).
  'icon-maskable-512.png': render(512, { tile: 'full', markSize: 512 * 0.62 }),
  // iOS masks its own rounded square and ignores transparency, so this one is full bleed too.
  'apple-touch-icon.png': render(180, { tile: 'full', markSize: 180 * 0.64 }),
}
for (const [name, buf] of Object.entries(icons)) {
  writeFileSync(join(dir, name), buf)
  console.log(`${name}  ${buf.length} bytes`)
}

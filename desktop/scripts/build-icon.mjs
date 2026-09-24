// Builds build/icon.ico from the two SVG sources and copies the small mark to
// the reader UI. Run `npm run icon` after changing build/icon.svg or
// build/icon-small.svg, and commit build/icon.ico and
// ../reader-ui/src/assets/mark.svg with them.
//
// 16 and 24 px come from icon-small.svg, which is drawn on the 16 px grid so
// it stays sharp; 32 px and up come from icon.svg. Entries below 256 px are
// stored as 32-bit BMPs and the 256 px entry as PNG, the layout Windows
// Explorer, the taskbar, rcedit, and NSIS all read.

/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JavaScript, no types to declare */

import { Resvg } from '@resvg/resvg-js'
import { copyFileSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const desktop = join(dirname(fileURLToPath(import.meta.url)), '..')
const full = readFileSync(join(desktop, 'build/icon.svg'))
const small = readFileSync(join(desktop, 'build/icon-small.svg'))
const SIZES = [16, 24, 32, 48, 64, 128, 256]

function render(svg, size) {
  const image = new Resvg(svg, { fitTo: { mode: 'width', value: size } }).render()
  if (image.width !== size || image.height !== size)
    throw new Error(`rendered ${image.width}x${image.height}, wanted ${size}`)
  return { png: image.asPng(), rgba: Buffer.from(image.pixels) }
}

/** A 32-bit BMP icon entry: BITMAPINFOHEADER, bottom-up BGRA rows, and an
 * all-zero AND mask (the alpha channel carries transparency). */
function bmpEntry(rgba, size) {
  const header = Buffer.alloc(40)
  header.writeUInt32LE(40, 0)
  header.writeInt32LE(size, 4)
  header.writeInt32LE(size * 2, 8) // colour rows plus mask rows
  header.writeUInt16LE(1, 12)
  header.writeUInt16LE(32, 14)
  const pixels = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const from = (y * size + x) * 4
      const to = ((size - 1 - y) * size + x) * 4
      pixels[to] = rgba[from + 2]
      pixels[to + 1] = rgba[from + 1]
      pixels[to + 2] = rgba[from]
      pixels[to + 3] = rgba[from + 3]
    }
  }
  const maskRow = Math.ceil(size / 32) * 4
  return Buffer.concat([header, pixels, Buffer.alloc(maskRow * size)])
}

const entries = SIZES.map((size) => {
  const { png, rgba } = render(size <= 24 ? small : full, size)
  return { size, data: size >= 256 ? png : bmpEntry(rgba, size) }
})

const directory = Buffer.alloc(6 + 16 * entries.length)
directory.writeUInt16LE(0, 0)
directory.writeUInt16LE(1, 2) // icon
directory.writeUInt16LE(entries.length, 4)
let offset = directory.length
entries.forEach(({ size, data }, index) => {
  const at = 6 + index * 16
  directory.writeUInt8(size >= 256 ? 0 : size, at)
  directory.writeUInt8(size >= 256 ? 0 : size, at + 1)
  directory.writeUInt8(0, at + 2)
  directory.writeUInt8(0, at + 3)
  directory.writeUInt16LE(1, at + 4)
  directory.writeUInt16LE(32, at + 6)
  directory.writeUInt32LE(data.length, at + 8)
  directory.writeUInt32LE(offset, at + 12)
  offset += data.length
})

writeFileSync(
  join(desktop, 'build/icon.ico'),
  Buffer.concat([directory, ...entries.map((entry) => entry.data)])
)
copyFileSync(
  join(desktop, 'build/icon-small.svg'),
  join(desktop, '../reader-ui/src/assets/mark.svg')
)
console.log(`build/icon.ico: ${SIZES.join(', ')} px; reader-ui/src/assets/mark.svg updated`)

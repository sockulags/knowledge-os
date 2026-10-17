// Writing a small file in the user-data folder through a temporary file, so
// a crash never leaves half a file. Only Node built-ins are used so the
// module is unit-testable.

import { mkdirSync, renameSync, writeFileSync } from 'fs'
import { dirname } from 'path'

/** Write `body` to `file`, creating its folder; readers see the old file or the new one, never a mix. */
export function writeFileAtomic(file: string, body: string): void {
  mkdirSync(dirname(file), { recursive: true })
  const temporary = `${file}.tmp`
  writeFileSync(temporary, body, 'utf-8')
  renameSync(temporary, file)
}

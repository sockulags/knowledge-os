import { describe, expect, it } from 'vitest'
import {
  buildMenus,
  COMMAND,
  displayAccelerator,
  matchAccelerator,
  menuViews,
  nativeTemplate,
  recentIndex,
  type KeyInput,
  type MenuInput
} from './menuModel'

const base: MenuInput = {
  recent: [{ root: 'D:\\kb', name: 'kb', lastOpened: '2026-09-25T00:00:00Z' }],
  reopenLastWorkspace: true,
  workspaceOpen: false,
  checkForUpdates: true,
  updatesSupported: true,
  updateReadyVersion: null,
  pluginMenus: [
    { label: 'Referat', items: [{ command: 'referat:record', label: 'Record', enabled: false }] }
  ]
}

function press(key: string, mods: Partial<KeyInput> = {}): KeyInput {
  return { type: 'keyDown', key, control: false, shift: false, alt: false, meta: false, ...mods }
}

describe('buildMenus', () => {
  it('keeps the native menu bar order and items', () => {
    const menus = buildMenus(base)
    expect(menus.map((menu) => menu.label)).toEqual(['File', 'View', 'Referat', 'Help'])
    const file = menus[0].items.map((item) => item.label ?? '—')
    expect(file).toEqual([
      'Open Knowledge Base…',
      'New Knowledge Base…',
      'Clone Knowledge Base…',
      'Open Recent',
      'Reopen the Last Knowledge Base on Start',
      '—',
      'Close Knowledge Base',
      '—',
      'Exit'
    ])
  })

  it('enables Close only with a knowledge base open', () => {
    const closed = buildMenus(base)[0].items.find((item) => item.command === COMMAND.close)
    const open = buildMenus({ ...base, workspaceOpen: true })[0].items.find(
      (item) => item.command === COMMAND.close
    )
    expect(closed?.enabled).toBe(false)
    expect(open?.enabled).toBe(true)
  })

  it('lists recent knowledge bases, or says there are none', () => {
    const recent = buildMenus(base)[0].items[3].submenu ?? []
    expect(recent).toEqual([{ command: 'file:recent:0', label: 'kb  (D:\\kb)' }])
    const none = buildMenus({ ...base, recent: [] })[0].items[3].submenu ?? []
    expect(none).toEqual([{ label: 'No recent knowledge bases', enabled: false }])
    expect(recentIndex('file:recent:0')).toBe(0)
    expect(recentIndex('file:open')).toBeNull()
  })

  it('offers Restart to Update only once an update is ready', () => {
    const help = (input: MenuInput): Array<string | undefined> =>
      buildMenus(input)[3].items.map((item) => item.command)
    expect(help(base)).not.toContain(COMMAND.restartToUpdate)
    const ready = buildMenus({ ...base, updateReadyVersion: '0.7.0' })[3].items
    expect(ready.at(-1)).toMatchObject({
      command: COMMAND.restartToUpdate,
      label: 'Restart to Update (0.7.0)'
    })
  })
})

describe('menuViews', () => {
  it('shows shortcuts the Windows way and marks checkboxes and submenus', () => {
    const [file, view] = menuViews(buildMenus(base))
    expect(file.items[0]).toMatchObject({ id: COMMAND.open, accelerator: 'Ctrl+O', enabled: true })
    expect(file.items[3]).toMatchObject({ type: 'submenu', id: '' })
    expect(file.items[4]).toMatchObject({ type: 'checkbox', checked: true })
    expect(file.items[5].type).toBe('separator')
    expect(view.items.find((item) => item.id === COMMAND.zoomIn)?.accelerator).toBe('Ctrl++')
  })
})

describe('displayAccelerator', () => {
  it('names keys as the menus show them', () => {
    expect(displayAccelerator('CmdOrCtrl+Shift+I')).toBe('Ctrl+Shift+I')
    expect(displayAccelerator('CmdOrCtrl+O', true)).toBe('Cmd+O')
    expect(displayAccelerator('F11')).toBe('F11')
  })
})

describe('matchAccelerator', () => {
  const menus = buildMenus({ ...base, workspaceOpen: false })

  it('finds the command for a shortcut', () => {
    expect(matchAccelerator(press('o', { control: true }), menus)).toBe(COMMAND.open)
    expect(matchAccelerator(press('I', { control: true, shift: true }), menus)).toBe(
      COMMAND.devTools
    )
    expect(matchAccelerator(press('F11'), menus)).toBe(COMMAND.fullScreen)
  })

  it('accepts both = and + for zoom in', () => {
    expect(matchAccelerator(press('=', { control: true }), menus)).toBe(COMMAND.zoomIn)
    expect(matchAccelerator(press('+', { control: true, shift: true }), menus)).toBe(COMMAND.zoomIn)
  })

  it('ignores other modifiers, key-ups, and plain typing', () => {
    expect(matchAccelerator(press('o'), menus)).toBeNull()
    expect(matchAccelerator(press('o', { control: true, alt: true }), menus)).toBeNull()
    expect(matchAccelerator({ ...press('o', { control: true }), type: 'keyUp' }, menus)).toBeNull()
    expect(matchAccelerator(press('r', { control: true, shift: true }), menus)).toBeNull()
  })

  it('uses Cmd on macOS', () => {
    expect(matchAccelerator(press('o', { meta: true }), menus, true)).toBe(COMMAND.open)
    expect(matchAccelerator(press('o', { control: true }), menus, true)).toBeNull()
  })
})

describe('nativeTemplate', () => {
  it('runs the same commands from the native menu', () => {
    const ran: string[] = []
    const template = nativeTemplate(buildMenus(base), (command) => ran.push(command))
    const file = template[0].submenu as Electron.MenuItemConstructorOptions[]
    expect(file[0]).toMatchObject({ label: 'Open Knowledge Base…', accelerator: 'CmdOrCtrl+O' })
    file[0].click?.({} as never, undefined, {} as never)
    expect(ran).toEqual([COMMAND.open])
  })
})

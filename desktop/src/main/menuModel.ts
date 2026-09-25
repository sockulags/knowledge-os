// The app's menu as plain data: which items exist, their shortcuts, and
// which are enabled or ticked. The title bar draws it (MenuView), the native
// application menu is built from it, and the main window's keyboard
// shortcuts are matched against it, so all three always agree. No Electron
// runtime here, so it is unit-testable.

import type { MenuItemConstructorOptions } from 'electron'
import type { MenuItemView, MenuView } from '../shared/chrome'
import { CLONE_TEXT } from '../shared/cloneText'
import { SHELL_TEXT, fillText } from '../shared/shellText'
import type { RecentWorkspace } from '../shared/types'

/** Commands the main process runs; a menu item names one by id. */
export const COMMAND = {
  open: 'file:open',
  create: 'file:create',
  clone: 'file:clone',
  reopenOnStart: 'file:reopen-on-start',
  close: 'file:close',
  exit: 'file:exit',
  reload: 'view:reload',
  devTools: 'view:dev-tools',
  resetZoom: 'view:reset-zoom',
  zoomIn: 'view:zoom-in',
  zoomOut: 'view:zoom-out',
  fullScreen: 'view:full-screen',
  checkForUpdates: 'help:check-for-updates',
  checkAutomatically: 'help:check-automatically',
  restartToUpdate: 'help:restart-to-update'
} as const

const RECENT_PREFIX = 'file:recent:'

/** The recent entry a command opens, or null when it is not a recent entry. */
export function recentIndex(command: string): number | null {
  if (!command.startsWith(RECENT_PREFIX)) return null
  const index = Number(command.slice(RECENT_PREFIX.length))
  return Number.isInteger(index) && index >= 0 ? index : null
}

export interface MenuSpecItem {
  /** The command to run; absent for separators and submenus. */
  command?: string
  type?: 'normal' | 'checkbox' | 'separator'
  label?: string
  /** Electron accelerator syntax, such as "CmdOrCtrl+O". */
  accelerator?: string
  enabled?: boolean
  checked?: boolean
  submenu?: MenuSpecItem[]
}

export interface MenuSpec {
  label: string
  items: MenuSpecItem[]
}

export interface MenuInput {
  recent: RecentWorkspace[]
  reopenLastWorkspace: boolean
  workspaceOpen: boolean
  checkForUpdates: boolean
  updatesSupported: boolean
  /** The downloaded update's version while it waits for a restart. */
  updateReadyVersion: string | null
  /** Menus from plugins, placed before Help. */
  pluginMenus: MenuSpec[]
}

const separator: MenuSpecItem = { type: 'separator' }

export function buildMenus(input: MenuInput): MenuSpec[] {
  const text = SHELL_TEXT.menu
  const recentItems: MenuSpecItem[] =
    input.recent.length > 0
      ? input.recent.map((item, index) => ({
          command: `${RECENT_PREFIX}${index}`,
          label: `${item.name}  (${item.root})`
        }))
      : [{ label: text.noRecent, enabled: false }]
  const help: MenuSpecItem[] = [
    { command: COMMAND.checkForUpdates, label: text.checkForUpdates },
    {
      command: COMMAND.checkAutomatically,
      type: 'checkbox',
      label: text.checkAutomatically,
      checked: input.checkForUpdates,
      enabled: input.updatesSupported
    }
  ]
  if (input.updateReadyVersion !== null) {
    help.push(separator, {
      command: COMMAND.restartToUpdate,
      label: fillText(text.restartToUpdate, { version: input.updateReadyVersion })
    })
  }
  return [
    {
      label: text.file,
      items: [
        { command: COMMAND.open, label: text.open, accelerator: 'CmdOrCtrl+O' },
        { command: COMMAND.create, label: text.create, accelerator: 'CmdOrCtrl+N' },
        { command: COMMAND.clone, label: CLONE_TEXT.menuItem },
        { label: text.openRecent, submenu: recentItems },
        {
          command: COMMAND.reopenOnStart,
          type: 'checkbox',
          label: text.reopenOnStart,
          checked: input.reopenLastWorkspace
        },
        separator,
        { command: COMMAND.close, label: text.close, enabled: input.workspaceOpen },
        separator,
        { command: COMMAND.exit, label: text.exit }
      ]
    },
    {
      label: text.view,
      items: [
        { command: COMMAND.reload, label: text.reload, accelerator: 'CmdOrCtrl+R' },
        { command: COMMAND.devTools, label: text.devTools, accelerator: 'CmdOrCtrl+Shift+I' },
        separator,
        { command: COMMAND.resetZoom, label: text.resetZoom, accelerator: 'CmdOrCtrl+0' },
        { command: COMMAND.zoomIn, label: text.zoomIn, accelerator: 'CmdOrCtrl+Plus' },
        { command: COMMAND.zoomOut, label: text.zoomOut, accelerator: 'CmdOrCtrl+-' },
        separator,
        { command: COMMAND.fullScreen, label: text.fullScreen, accelerator: 'F11' }
      ]
    },
    ...input.pluginMenus,
    { label: text.help, items: help }
  ]
}

interface Accelerator {
  control: boolean
  shift: boolean
  alt: boolean
  meta: boolean
  key: string
}

function parseAccelerator(accelerator: string, mac: boolean): Accelerator {
  const parts = accelerator.split('+')
  // "CmdOrCtrl+Plus" names the plus key by word, so a trailing "+" never appears.
  const key = parts.pop() ?? ''
  const parsed: Accelerator = { control: false, shift: false, alt: false, meta: false, key }
  for (const part of parts) {
    switch (part.toLowerCase()) {
      case 'cmdorctrl':
      case 'commandorcontrol':
        if (mac) parsed.meta = true
        else parsed.control = true
        break
      case 'ctrl':
      case 'control':
        parsed.control = true
        break
      case 'shift':
        parsed.shift = true
        break
      case 'alt':
      case 'option':
        parsed.alt = true
        break
      case 'cmd':
      case 'command':
      case 'meta':
      case 'super':
        parsed.meta = true
        break
    }
  }
  return parsed
}

/** An accelerator as the menu shows it: "CmdOrCtrl+Plus" becomes "Ctrl++". */
export function displayAccelerator(accelerator: string, mac = false): string {
  const parsed = parseAccelerator(accelerator, mac)
  const names: string[] = []
  if (parsed.control) names.push('Ctrl')
  if (parsed.alt) names.push(mac ? 'Option' : 'Alt')
  if (parsed.shift) names.push('Shift')
  if (parsed.meta) names.push(mac ? 'Cmd' : 'Win')
  names.push(parsed.key === 'Plus' ? '+' : parsed.key)
  return names.join('+')
}

/** A key press, as Electron's `before-input-event` reports it. */
export interface KeyInput {
  type: string
  key: string
  control: boolean
  shift: boolean
  alt: boolean
  meta: boolean
}

function keyMatches(accelerator: Accelerator, input: KeyInput): boolean {
  if (input.control !== accelerator.control) return false
  if (input.alt !== accelerator.alt || input.meta !== accelerator.meta) return false
  const pressed = input.key.toLowerCase()
  if (accelerator.key === 'Plus') {
    // "+" needs Shift on some layouts and has its own key on others; "=" is
    // the same key unshifted, as in browsers.
    return pressed === '+' || pressed === '='
  }
  return input.shift === accelerator.shift && pressed === accelerator.key.toLowerCase()
}

function* enabledItems(items: MenuSpecItem[]): Generator<MenuSpecItem> {
  for (const item of items) {
    if (item.enabled === false) continue
    if (item.submenu) yield* enabledItems(item.submenu)
    else yield item
  }
}

/** The command whose shortcut `input` is, or null. */
export function matchAccelerator(input: KeyInput, menus: MenuSpec[], mac = false): string | null {
  if (input.type !== 'keyDown') return null
  for (const menu of menus) {
    for (const item of enabledItems(menu.items)) {
      if (item.command === undefined || item.accelerator === undefined) continue
      if (keyMatches(parseAccelerator(item.accelerator, mac), input)) return item.command
    }
  }
  return null
}

function itemView(item: MenuSpecItem, mac: boolean): MenuItemView {
  if (item.type === 'separator') return { id: '', type: 'separator', label: '', enabled: false }
  const view: MenuItemView = {
    id: item.command ?? '',
    type: item.submenu ? 'submenu' : (item.type ?? 'normal'),
    label: item.label ?? '',
    enabled: item.enabled !== false
  }
  if (item.accelerator !== undefined) view.accelerator = displayAccelerator(item.accelerator, mac)
  if (item.type === 'checkbox') view.checked = item.checked === true
  if (item.submenu) view.submenu = item.submenu.map((child) => itemView(child, mac))
  return view
}

/** The menus as the title bar draws them. */
export function menuViews(menus: MenuSpec[], mac = false): MenuView[] {
  return menus.map((menu) => ({
    label: menu.label,
    items: menu.items.map((item) => itemView(item, mac))
  }))
}

/** The same menus as a native application menu template. */
export function nativeTemplate(
  menus: MenuSpec[],
  run: (command: string) => void
): MenuItemConstructorOptions[] {
  const convert = (item: MenuSpecItem): MenuItemConstructorOptions => {
    if (item.type === 'separator') return { type: 'separator' }
    const options: MenuItemConstructorOptions = {
      label: item.label,
      enabled: item.enabled !== false
    }
    if (item.accelerator !== undefined) options.accelerator = item.accelerator
    if (item.type === 'checkbox') {
      options.type = 'checkbox'
      options.checked = item.checked === true
    }
    if (item.submenu) options.submenu = item.submenu.map(convert)
    const command = item.command
    if (command !== undefined) options.click = () => run(command)
    return options
  }
  return menus.map((menu) => ({ label: menu.label, submenu: menu.items.map(convert) }))
}

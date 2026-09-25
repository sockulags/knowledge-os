// Draws the window chrome into the page a shell window shows: the title bar
// (app icon, in-app menu, page and knowledge base title, a free space for
// Windows' own window controls), notices, and dialogs. It lives in a closed
// shadow root, so the page's styles cannot change it. The page only makes
// room for it through the `--kos-titlebar-height` CSS variable on its root
// element.
//
// The main window's preload script draws it, from its isolated world, into
// both the start page and the reader (which the core serves and which knows
// nothing of the desktop app); menu commands, notice and dialog answers go
// to the main process, which owns the state and pushes it back (see
// src/main/windowChrome.ts). The clone and Referat windows have no menu:
// their own pages draw just the title bar, with no bridge.

import css from './chrome.css?inline'
import mark from '../../build/icon-small.svg?raw'
import {
  TITLE_BAR_HEIGHT,
  type ChromeAction,
  type ChromeDialog,
  type ChromeState,
  type ChromeTheme,
  type MenuItemView,
  type Notice
} from '../shared/chrome'
import { firstIndex, lastIndex, letterIndex, stepIndex, titleParts } from '../shared/menuNav'
import { SHELL_TEXT } from '../shared/shellText'

export interface ChromeBridge {
  getState: () => Promise<ChromeState>
  onState: (callback: (state: ChromeState) => void) => void
  command: (command: string) => void
  notice: (key: string, action: string) => void
  dialog: (id: number, action: string) => void
  theme: (theme: ChromeTheme) => void
}

const ICON = {
  check:
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
  chevron:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>',
  close:
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
}

/** Width Windows' controls take when their real width cannot be read. */
const FALLBACK_CONTROLS_WIDTH = 138

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (className !== undefined) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function actionButton(action: ChromeAction, small: boolean): HTMLButtonElement {
  const button = element(
    'button',
    `kos-btn kos-btn-${action.variant}${small ? ' kos-btn-sm' : ''}`,
    action.label
  )
  button.type = 'button'
  return button
}

/** A menu open under the title bar, or a submenu open beside one of its items. */
interface OpenMenu {
  items: MenuItemView[]
  buttons: Array<HTMLButtonElement | null>
  node: HTMLElement
  /** Where the menu hangs from: a title bar button, or a submenu's parent item. */
  anchor: HTMLButtonElement
  child: OpenMenu | null
}

interface WindowControlsOverlay extends EventTarget {
  visible: boolean
  getTitlebarAreaRect: () => DOMRect
}

class WindowChrome {
  private readonly host = element('div')
  private readonly root: ShadowRoot
  private readonly bar = element('div', 'bar')
  private readonly menubar = element('div', 'menubar')
  private readonly title = element('div', 'title')
  private readonly titleAction = element('button', 'title-action')
  private readonly gap = element('div', 'controls-gap')
  private readonly notices = element('div', 'notices')
  private readonly dialogLayer = element('div', 'dialog-layer')

  private state: ChromeState | null = null
  private topButtons: HTMLButtonElement[] = []
  private open: { top: number; menu: OpenMenu } | null = null
  /** The menubar has the keyboard focus (after Alt or F10), with or without a menu open. */
  private menubarActive = false
  private altArmed = false
  /** Where the focus goes back to when the menu or a dialog closes. */
  private restoreFocus: Element | null = null
  private shownDialog: number | null = null
  private inerted: Array<{ node: HTMLElement; inert: boolean }> = []
  private theme: ChromeTheme | null = null
  private zoom = 1

  constructor(private readonly bridge: ChromeBridge | null) {
    this.host.id = 'kos-window-chrome'
    this.root = this.host.attachShadow({ mode: 'closed' })
    const style = element('style')
    style.textContent = css
    const icon = element('span', 'icon')
    icon.innerHTML = mark
    this.menubar.setAttribute('role', 'menubar')
    this.titleAction.type = 'button'
    this.titleAction.hidden = true
    this.titleAction.addEventListener('click', (event) => {
      const action = this.state?.titleAction
      if (event.isTrusted && action) this.bridge?.command(action.command)
    })
    this.dialogLayer.hidden = true
    this.bar.append(icon, this.menubar, this.title, this.titleAction, this.gap)
    this.root.append(style, this.bar, this.notices, this.dialogLayer)
    ;(document.body ?? document.documentElement).append(this.host)

    this.root.addEventListener('keydown', (event) => this.onChromeKey(event as KeyboardEvent))
    window.addEventListener('keydown', (event) => this.onWindowKeyDown(event), true)
    window.addEventListener('keyup', (event) => this.onWindowKeyUp(event), true)
    window.addEventListener(
      'pointerdown',
      (event) => {
        if (this.open !== null && !event.composedPath().includes(this.host)) this.closeMenus(false)
      },
      true
    )
    window.addEventListener('blur', () => {
      this.closeMenus(false)
      this.altArmed = false
      this.showMnemonics(false)
      this.host.setAttribute('data-inactive', '')
    })
    window.addEventListener('focus', () => this.host.removeAttribute('data-inactive'))
    if (!document.hasFocus()) this.host.setAttribute('data-inactive', '')

    this.watchTitle()
    this.watchTheme()
    this.watchControls()
    this.renderTitle()

    if (bridge !== null) {
      bridge.onState((state) => this.apply(state))
      void bridge.getState().then((state) => this.apply(state))
    }
  }

  // --- State from the main process -------------------------------------

  private apply(state: ChromeState): void {
    const previous = this.state
    this.state = state
    this.menubar.setAttribute('aria-label', state.labels.menubar)
    if (state.zoomFactor !== this.zoom || state.fullScreen !== previous?.fullScreen) {
      this.zoom = state.zoomFactor
      this.host.style.setProperty('zoom', String(1 / this.zoom))
      setTitleBarInset(this.zoom)
      this.measureControls()
    }
    if (JSON.stringify(previous?.menus) !== JSON.stringify(state.menus)) this.renderMenubar()
    this.renderTitle()
    const action = state.titleAction
    this.titleAction.hidden = action === null
    this.titleAction.textContent = action?.label ?? ''
    if (JSON.stringify(previous?.notices) !== JSON.stringify(state.notices)) this.renderNotices()
    if ((previous?.dialog?.id ?? null) !== (state.dialog?.id ?? null))
      this.renderDialog(state.dialog)
  }

  // --- Title -----------------------------------------------------------

  private watchTitle(): void {
    const observer = new MutationObserver(() => this.renderTitle())
    const watch = (): void => {
      if (document.head) {
        observer.observe(document.head, { subtree: true, childList: true, characterData: true })
      }
    }
    watch()
  }

  private renderTitle(): void {
    const parts = titleParts(document.title, this.state?.workspace ?? null)
    const nodes: Node[] = []
    if (parts.page !== '') nodes.push(element('span', 'page', parts.page))
    if (parts.workspace !== '') {
      nodes.push(
        element('span', 'workspace', parts.page !== '' ? ` — ${parts.workspace}` : parts.workspace)
      )
    }
    if (nodes.length === 0) nodes.push(element('span', 'page', SHELL_TEXT.appName))
    this.title.replaceChildren(...nodes)
  }

  // --- Theme and window controls ---------------------------------------

  /** Follows the page: its `data-theme` choice (the reader's toggle), else the system. */
  private watchTheme(): void {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = (): void => {
      const chosen = document.documentElement.getAttribute('data-theme')
      const theme: ChromeTheme =
        chosen === 'dark' || chosen === 'light' ? chosen : media.matches ? 'dark' : 'light'
      if (theme === this.theme) return
      this.theme = theme
      this.host.setAttribute('data-theme', theme)
      this.bridge?.theme(theme)
    }
    media.addEventListener('change', update)
    new MutationObserver(update).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    })
    update()
  }

  private controls(): WindowControlsOverlay | null {
    const overlay = (navigator as Navigator & { windowControlsOverlay?: WindowControlsOverlay })
      .windowControlsOverlay
    return overlay ?? null
  }

  private watchControls(): void {
    this.controls()?.addEventListener('geometrychange', () => this.measureControls())
    window.addEventListener('resize', () => this.measureControls())
    this.measureControls()
  }

  /** Keeps the title bar's content clear of Windows' controls; none show in full screen. */
  private measureControls(): void {
    const overlay = this.controls()
    let width = FALLBACK_CONTROLS_WIDTH
    if (this.state?.fullScreen) width = 0
    else if (overlay !== null) {
      if (!overlay.visible) width = 0
      else {
        const area = overlay.getTitlebarAreaRect()
        // The area is in the page's CSS pixels; the chrome is drawn unzoomed.
        width = Math.max(0, (window.innerWidth - area.x - area.width) * this.zoom)
      }
    }
    this.gap.style.width = `${Math.round(width)}px`
  }

  // --- Menubar ---------------------------------------------------------

  private renderMenubar(): void {
    // The menus changed under an open one (a new recent entry, an update
    // became ready): close it rather than show stale items.
    this.closeMenus(this.menubarActive)
    const menus = this.state?.menus ?? []
    this.topButtons = menus.map((menu, index) => {
      const button = element('button')
      button.type = 'button'
      button.tabIndex = -1
      button.setAttribute('role', 'menuitem')
      button.setAttribute('aria-haspopup', 'menu')
      button.setAttribute('aria-expanded', 'false')
      const first = element('span', 'mnemonic', menu.label.slice(0, 1))
      button.append(first, menu.label.slice(1))
      button.addEventListener('pointerdown', (event) => {
        if (!event.isTrusted || event.button !== 0) return
        event.preventDefault()
        if (this.open?.top === index) this.closeMenus(true)
        else {
          this.rememberFocus()
          this.openTop(index, 'menu')
        }
      })
      button.addEventListener('pointerenter', () => {
        if (this.open !== null && this.open.top !== index) this.openTop(index, 'menu')
      })
      button.addEventListener('click', (event) => {
        // Keyboard activation (Enter, Space) arrives as a click with no pointer.
        if (event.isTrusted && event.detail === 0) this.openTop(index, 'first')
      })
      return button
    })
    this.menubar.replaceChildren(
      ...this.topButtons.map((button) => {
        // Each menu hangs from the slot around its button.
        const slot = element('span', 'slot')
        slot.setAttribute('role', 'none')
        slot.append(button)
        return slot
      })
    )
  }

  private rememberFocus(): void {
    if (this.menubarActive || this.open !== null) return
    const active = document.activeElement
    this.restoreFocus = active !== null && active !== this.host ? active : null
  }

  private enterMenubar(): void {
    if (this.topButtons.length === 0 || this.shownDialog !== null) return
    this.rememberFocus()
    this.menubarActive = true
    this.showMnemonics(true)
    this.topButtons[0].focus()
  }

  private showMnemonics(show: boolean): void {
    this.bar.toggleAttribute('data-mnemonics', show)
  }

  /** Closes every menu; `restore` returns the focus to where it was before. */
  private closeMenus(restore: boolean): void {
    if (this.open !== null) {
      this.open.menu.node.remove()
      this.topButtons[this.open.top]?.setAttribute('aria-expanded', 'false')
      this.open = null
    }
    this.menubarActive = false
    this.showMnemonics(false)
    if (restore) this.focusBack()
    else this.restoreFocus = null
  }

  private focusBack(): void {
    const target = this.restoreFocus
    this.restoreFocus = null
    if (target instanceof HTMLElement && target.isConnected) target.focus({ preventScroll: true })
    // Nothing had the focus (the page body): give it back to the page.
    if (this.root.activeElement instanceof HTMLElement) this.root.activeElement.blur()
  }

  /** Opens a top-level menu; `focus` says what gets the keyboard focus in it. */
  private openTop(index: number, focus: 'menu' | 'first' | 'last'): void {
    const view = this.state?.menus[index]
    const anchor = this.topButtons[index]
    if (view === undefined || anchor === undefined) return
    if (this.open !== null) {
      this.open.menu.node.remove()
      this.topButtons[this.open.top]?.setAttribute('aria-expanded', 'false')
    }
    this.menubarActive = true
    const menu = this.buildMenu(view.items, anchor, view.label)
    menu.node.style.left = '0'
    menu.node.style.top = 'calc(100% + 4px)'
    anchor.setAttribute('aria-expanded', 'true')
    this.open = { top: index, menu }
    anchor.parentElement?.append(menu.node)
    this.focusIn(menu, focus)
  }

  private focusIn(menu: OpenMenu, focus: 'menu' | 'first' | 'last'): void {
    const index =
      focus === 'first' ? firstIndex(menu.items) : focus === 'last' ? lastIndex(menu.items) : -1
    const target = index >= 0 ? menu.buttons[index] : null
    ;(target ?? menu.node).focus({ preventScroll: true })
  }

  private buildMenu(items: MenuItemView[], anchor: HTMLButtonElement, label: string): OpenMenu {
    const node = element('div', 'kos-menu')
    node.setAttribute('role', 'menu')
    node.setAttribute('aria-label', label)
    node.tabIndex = -1
    const menu: OpenMenu = { items, buttons: [], node, anchor, child: null }
    items.forEach((item, index) => {
      if (item.type === 'separator') {
        const line = element('div', 'separator')
        line.setAttribute('role', 'separator')
        node.append(line)
        menu.buttons.push(null)
        return
      }
      const button = element('button', 'kos-menu-item')
      button.type = 'button'
      button.tabIndex = -1
      button.disabled = !item.enabled
      button.setAttribute('role', item.type === 'checkbox' ? 'menuitemcheckbox' : 'menuitem')
      if (!item.enabled) button.setAttribute('aria-disabled', 'true')
      const check = element('span', 'check')
      if (item.type === 'checkbox') {
        button.setAttribute('aria-checked', String(item.checked === true))
        if (item.checked) check.innerHTML = ICON.check
      }
      button.append(check, element('span', 'label', item.label))
      if (item.accelerator) {
        button.append(element('span', 'shortcut', item.accelerator))
        button.setAttribute('aria-keyshortcuts', item.accelerator.replace(/\+\+$/, '+Plus'))
      }
      if (item.type === 'submenu') {
        button.setAttribute('aria-haspopup', 'menu')
        button.setAttribute('aria-expanded', 'false')
        const chevron = element('span', 'chevron')
        chevron.innerHTML = ICON.chevron
        button.append(chevron)
      }
      button.addEventListener('pointermove', () => {
        // The focus follows the pointer, so the keyboard continues from there.
        if (this.root.activeElement !== button) button.focus({ preventScroll: true })
        if (item.type === 'submenu') this.openSubmenu(menu, index, 'menu')
        else this.closeSubmenu(menu)
      })
      button.addEventListener('click', (event) => {
        if (!event.isTrusted) return
        if (item.type === 'submenu') this.openSubmenu(menu, index, 'first')
        else this.activate(item)
      })
      const slot = element('div', 'item-slot')
      slot.setAttribute('role', 'none')
      slot.append(button)
      node.append(slot)
      menu.buttons.push(button)
    })
    return menu
  }

  private openSubmenu(parent: OpenMenu, index: number, focus: 'menu' | 'first'): void {
    const item = parent.items[index]
    const anchor = parent.buttons[index]
    if (item.submenu === undefined || anchor === null) return
    if (parent.child?.anchor === anchor) {
      if (focus === 'first') this.focusIn(parent.child, 'first')
      return
    }
    this.closeSubmenu(parent)
    const child = this.buildMenu(item.submenu, anchor, item.label)
    child.node.style.left = 'calc(100% + 6px)'
    child.node.style.top = '-5px'
    anchor.setAttribute('aria-expanded', 'true')
    parent.child = child
    anchor.parentElement?.append(child.node)
    if (focus === 'first') this.focusIn(child, 'first')
  }

  private closeSubmenu(parent: OpenMenu): void {
    if (parent.child === null) return
    parent.child.node.remove()
    parent.child.anchor.setAttribute('aria-expanded', 'false')
    parent.child = null
  }

  private activate(item: MenuItemView): void {
    if (!item.enabled || item.id === '') return
    this.closeMenus(true)
    this.bridge?.command(item.id)
  }

  /** The innermost open menu and the index of its focused item (-1 for none). */
  private focusedMenu(): { menu: OpenMenu; index: number; parent: OpenMenu | null } | null {
    if (this.open === null) return null
    let parent: OpenMenu | null = null
    let menu = this.open.menu
    const active = this.root.activeElement
    while (menu.child !== null && menu.child.node.contains(active)) {
      parent = menu
      menu = menu.child
    }
    const index = menu.buttons.findIndex((button) => button !== null && button === active)
    return { menu, index, parent }
  }

  // --- Keyboard --------------------------------------------------------

  private onWindowKeyDown(event: KeyboardEvent): void {
    if (!event.isTrusted || this.bridge === null || this.shownDialog !== null) return
    const plain = !event.ctrlKey && !event.metaKey && !event.shiftKey
    if (event.key === 'Alt' && plain) {
      this.altArmed = true
      this.showMnemonics(true)
      return
    }
    this.altArmed = false
    if (event.key === 'F10' && plain && !event.altKey) {
      event.preventDefault()
      event.stopPropagation()
      if (this.menubarActive) this.closeMenus(true)
      else this.enterMenubar()
      return
    }
    if (event.altKey && !event.ctrlKey && !event.metaKey && event.key.length === 1) {
      const index = letterIndex(this.state?.menus.map(topEntry) ?? [], event.key)
      if (index < 0) return
      event.preventDefault()
      event.stopPropagation()
      this.rememberFocus()
      this.openTop(index, 'first')
    }
  }

  private onWindowKeyUp(event: KeyboardEvent): void {
    if (!event.isTrusted || event.key !== 'Alt') return
    if (!this.menubarActive) this.showMnemonics(false)
    if (!this.altArmed) return
    this.altArmed = false
    event.preventDefault()
    if (this.menubarActive) this.closeMenus(true)
    else this.enterMenubar()
  }

  /** Keys pressed inside the chrome never reach the page's own shortcuts. */
  private onChromeKey(event: KeyboardEvent): void {
    event.stopPropagation()
    if (!event.isTrusted) return
    if (this.shownDialog !== null) {
      this.onDialogKey(event)
      return
    }
    if (event.key === 'Alt') return
    const focused = this.focusedMenu()
    if (focused === null) this.onMenubarKey(event)
    else this.onMenuKey(event, focused)
  }

  private onMenubarKey(event: KeyboardEvent): void {
    const count = this.topButtons.length
    const current = this.topButtons.findIndex((button) => button === this.root.activeElement)
    if (current < 0 || count === 0) return
    let handled = true
    switch (event.key) {
      case 'ArrowRight':
        this.topButtons[(current + 1) % count].focus()
        break
      case 'ArrowLeft':
        this.topButtons[(current - 1 + count) % count].focus()
        break
      case 'ArrowDown':
      case 'Enter':
      case ' ':
        this.openTop(current, 'first')
        break
      case 'ArrowUp':
        this.openTop(current, 'last')
        break
      case 'Escape':
      case 'Tab':
        this.closeMenus(true)
        break
      default: {
        const index = letterIndex(this.state?.menus.map(topEntry) ?? [], event.key)
        if (index >= 0) this.openTop(index, 'first')
        else handled = false
      }
    }
    if (handled) event.preventDefault()
  }

  private onMenuKey(
    event: KeyboardEvent,
    focused: { menu: OpenMenu; index: number; parent: OpenMenu | null }
  ): void {
    const { menu, index, parent } = focused
    const item = index >= 0 ? menu.items[index] : null
    const focusAt = (next: number): void => {
      if (next >= 0) menu.buttons[next]?.focus({ preventScroll: true })
      this.closeSubmenu(menu)
    }
    const topCount = this.topButtons.length
    const top = this.open?.top ?? 0
    let handled = true
    switch (event.key) {
      case 'ArrowDown':
        focusAt(stepIndex(menu.items, index, 1))
        break
      case 'ArrowUp':
        focusAt(stepIndex(menu.items, index, -1))
        break
      case 'Home':
        focusAt(firstIndex(menu.items))
        break
      case 'End':
        focusAt(lastIndex(menu.items))
        break
      case 'ArrowRight':
        if (item?.type === 'submenu') this.openSubmenu(menu, index, 'first')
        else this.openTop((top + 1) % topCount, 'first')
        break
      case 'ArrowLeft':
        if (parent !== null) {
          this.closeSubmenu(parent)
          menu.anchor.focus({ preventScroll: true })
        } else this.openTop((top - 1 + topCount) % topCount, 'first')
        break
      case 'Enter':
      case ' ':
        if (item === null) break
        if (item.type === 'submenu') this.openSubmenu(menu, index, 'first')
        else this.activate(item)
        break
      case 'Escape':
        if (parent !== null) {
          this.closeSubmenu(parent)
          menu.anchor.focus({ preventScroll: true })
        } else {
          // Back to the menubar, as in Windows; a second Escape leaves it.
          const button = this.topButtons[top]
          this.open?.menu.node.remove()
          button?.setAttribute('aria-expanded', 'false')
          this.open = null
          button?.focus()
          this.showMnemonics(true)
        }
        break
      case 'Tab':
        this.closeMenus(true)
        break
      default: {
        const next = letterIndex(menu.items, event.key, index)
        if (next >= 0) focusAt(next)
        else handled = false
      }
    }
    if (handled) event.preventDefault()
  }

  // --- Notices ---------------------------------------------------------

  private renderNotices(): void {
    const notices = this.state?.notices ?? []
    this.notices.replaceChildren(...notices.map((notice) => this.noticeCard(notice)))
  }

  private noticeCard(notice: Notice): HTMLElement {
    const card = element('div', 'notice kos-overlay')
    card.setAttribute('role', notice.tone === 'warning' ? 'alert' : 'status')
    card.dataset.tone = notice.tone
    const body = element('div', 'notice-body')
    body.append(element('p', 'notice-message', notice.message))
    if (notice.detail) body.append(element('p', 'notice-detail', notice.detail))
    const answer = (action: string): void => {
      card.remove()
      this.bridge?.notice(notice.key, action)
    }
    if (notice.actions.length > 0) {
      const row = element('div', 'notice-actions')
      for (const action of notice.actions) {
        const button = actionButton(action, true)
        button.addEventListener('click', (event) => {
          if (event.isTrusted) answer(action.id)
        })
        row.append(button)
      }
      body.append(row)
    }
    const dismiss = element('button', 'kos-icon-btn')
    dismiss.type = 'button'
    dismiss.innerHTML = ICON.close
    dismiss.setAttribute('aria-label', this.state?.labels.dismiss ?? SHELL_TEXT.titleBar.dismiss)
    dismiss.title = dismiss.getAttribute('aria-label') ?? ''
    dismiss.addEventListener('click', (event) => {
      if (event.isTrusted) answer('dismiss')
    })
    card.append(body, dismiss)
    return card
  }

  // --- Dialogs ---------------------------------------------------------

  private renderDialog(dialog: ChromeDialog | null): void {
    if (dialog === null) {
      if (this.shownDialog === null) return
      this.shownDialog = null
      this.dialogLayer.hidden = true
      this.dialogLayer.replaceChildren()
      this.setPageInert(false)
      this.focusBack()
      return
    }
    this.closeMenus(false)
    if (this.shownDialog === null) {
      const active = document.activeElement
      this.restoreFocus = active !== null && active !== this.host ? active : null
    }
    this.shownDialog = dialog.id
    const scrim = element('div', 'scrim')
    scrim.addEventListener('click', (event) => {
      if (event.isTrusted) this.answer(dialog, dialog.cancelId)
    })
    const panel = element('div', 'dialog kos-overlay')
    panel.setAttribute('role', dialog.tone === 'warning' ? 'alertdialog' : 'dialog')
    panel.setAttribute('aria-modal', 'true')
    const heading = element('h2', undefined, dialog.title)
    heading.id = 'kos-dialog-title'
    const message = element('p', undefined, dialog.message)
    message.id = 'kos-dialog-message'
    panel.setAttribute('aria-labelledby', heading.id)
    panel.setAttribute('aria-describedby', message.id)
    panel.append(heading, message)
    if (dialog.detail) panel.append(element('p', undefined, dialog.detail))
    const row = element('div', 'dialog-actions')
    let cancel: HTMLButtonElement | null = null
    for (const action of dialog.actions) {
      const button = actionButton(action, false)
      button.addEventListener('click', (event) => {
        if (event.isTrusted) this.answer(dialog, action.id)
      })
      if (action.id === dialog.cancelId) cancel = button
      row.append(button)
    }
    panel.append(row)
    this.dialogLayer.replaceChildren(scrim, panel)
    this.dialogLayer.hidden = false
    this.setPageInert(true)
    // The safe choice gets the focus, so a stray Enter never discards anything.
    ;(cancel ?? row.querySelector('button'))?.focus()
  }

  private answer(dialog: ChromeDialog, action: string): void {
    if (this.shownDialog !== dialog.id) return
    this.renderDialog(null)
    this.bridge?.dialog(dialog.id, action)
  }

  private onDialogKey(event: KeyboardEvent): void {
    const dialog = this.state?.dialog
    if (dialog === null || dialog === undefined) return
    if (event.key === 'Escape') {
      event.preventDefault()
      this.answer(dialog, dialog.cancelId)
      return
    }
    if (event.key === 'Tab') {
      // Keep the focus on the dialog's buttons.
      const buttons = Array.from(this.dialogLayer.querySelectorAll('button'))
      const index = buttons.findIndex((button) => button === this.root.activeElement)
      const next = (index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length
      buttons[next]?.focus()
      event.preventDefault()
    }
  }

  /** While a dialog is open, the page and the menu cannot be reached. */
  private setPageInert(inert: boolean): void {
    if (inert) {
      if (this.inerted.length > 0) return
      const nodes = Array.from(document.body?.children ?? []).filter(
        (node): node is HTMLElement => node instanceof HTMLElement && node !== this.host
      )
      this.inerted = nodes.map((node) => ({ node, inert: node.inert }))
      for (const node of nodes) node.inert = true
      this.menubar.inert = true
    } else {
      for (const { node, inert: was } of this.inerted) node.inert = was
      this.inerted = []
      this.menubar.inert = false
    }
  }
}

function topEntry(menu: { label: string }): { label: string; type: string; enabled: boolean } {
  return { label: menu.label, type: 'normal', enabled: true }
}

/** Makes room for the title bar in the page: its layout reads this variable. */
function setTitleBarInset(zoom: number): void {
  document.documentElement?.style.setProperty(
    '--kos-titlebar-height',
    `${TITLE_BAR_HEIGHT / zoom}px`
  )
}

/**
 * Draws the window chrome once the page's document exists. `bridge` is the
 * main window's connection to the main process; windows without a menu pass
 * null.
 */
export function mountWindowChrome(bridge: ChromeBridge | null): void {
  setTitleBarInset(1)
  const start = (): void => {
    setTitleBarInset(1)
    new WindowChrome(bridge)
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true })
  } else start()
}

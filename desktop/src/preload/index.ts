// The main window's preload script. It exposes the workspace actions to the
// start page, which the main process rejects from any other page, and the
// sidebar width to the reader UI, which the main process answers only for
// the reader. It also draws the window chrome (title bar, menu, notices,
// dialogs) into whichever of the two pages the window shows; that part talks
// to the main process from this isolated world and is not exposed to the page.

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { CHROME_IPC, type ChromeState } from '../shared/chrome'
import { IPC, type DesktopApi, type ShellState } from '../shared/types'
import { mountWindowChrome } from '../chrome/windowChrome'

const api: DesktopApi = {
  onReaderCommand: (callback) => {
    const listener = (_event: IpcRendererEvent, command: string): void => callback(command)
    ipcRenderer.on(IPC.readerCommand, listener)
    return () => {
      ipcRenderer.removeListener(IPC.readerCommand, listener)
    }
  },
  getSidebarWidth: () => ipcRenderer.sendSync(IPC.getSidebarWidth),
  setSidebarWidth: (width) => ipcRenderer.send(IPC.setSidebarWidth, width),
  getState: () => ipcRenderer.invoke(IPC.getState),
  onStateChanged: (callback) => {
    const listener = (_event: IpcRendererEvent, state: ShellState): void => callback(state)
    ipcRenderer.on(IPC.stateChanged, listener)
    return () => {
      ipcRenderer.removeListener(IPC.stateChanged, listener)
    }
  },
  openWorkspace: () => ipcRenderer.invoke(IPC.openWorkspace),
  createWorkspace: () => ipcRenderer.invoke(IPC.createWorkspace),
  cloneWorkspace: () => ipcRenderer.invoke(IPC.cloneWorkspace),
  openRecent: (root) => ipcRenderer.invoke(IPC.openRecent, root),
  showStart: () => ipcRenderer.invoke(IPC.showStart),
  retry: () => ipcRenderer.invoke(IPC.retry),
  agent: {
    list: () => ipcRenderer.invoke(IPC.agentList),
    installAdapter: (providerId) => ipcRenderer.invoke(IPC.agentInstall, providerId),
    start: (providerId) => ipcRenderer.invoke(IPC.agentStart, providerId),
    prompt: (text) => ipcRenderer.invoke(IPC.agentPrompt, text),
    cancel: () => ipcRenderer.invoke(IPC.agentCancel),
    respondPermission: (requestId, optionId) =>
      ipcRenderer.invoke(IPC.agentPermission, requestId, optionId),
    restart: () => ipcRenderer.invoke(IPC.agentRestart),
    close: () => ipcRenderer.invoke(IPC.agentClose),
    conversations: () => ipcRenderer.invoke(IPC.agentConversations),
    conversation: (id) => ipcRenderer.invoke(IPC.agentConversationGet, id),
    saveConversation: (conversation) => ipcRenderer.invoke(IPC.agentConversationSave, conversation),
    deleteConversation: (id) => ipcRenderer.invoke(IPC.agentConversationDelete, id),
    onEvent: (callback) => {
      const listener = (_event: IpcRendererEvent, event: unknown): void => callback(event)
      ipcRenderer.on(IPC.agentEvent, listener)
      return () => {
        ipcRenderer.removeListener(IPC.agentEvent, listener)
      }
    }
  }
}

contextBridge.exposeInMainWorld('kosDesktop', api)

mountWindowChrome({
  getState: () => ipcRenderer.invoke(CHROME_IPC.getState),
  onState: (callback) => {
    ipcRenderer.on(CHROME_IPC.state, (_event, state: ChromeState) => callback(state))
  },
  command: (command) => ipcRenderer.send(CHROME_IPC.command, command),
  notice: (key, action) => ipcRenderer.send(CHROME_IPC.notice, key, action),
  dialog: (id, action) => ipcRenderer.send(CHROME_IPC.dialog, id, action),
  theme: (theme) => ipcRenderer.send(CHROME_IPC.theme, theme)
})

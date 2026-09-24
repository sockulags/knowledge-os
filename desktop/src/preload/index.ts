// Exposes the workspace actions to the start page, which the main process
// rejects from any other page, and the sidebar width to the reader UI,
// which the main process answers only for the reader.

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { IPC, type DesktopApi, type ShellState } from '../shared/types'

const api: DesktopApi = {
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
  retry: () => ipcRenderer.invoke(IPC.retry)
}

contextBridge.exposeInMainWorld('kosDesktop', api)

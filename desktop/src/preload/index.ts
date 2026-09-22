// Exposes only the workspace actions to the start page. The main process
// rejects these calls from any other page, including the reader UI.

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { IPC, type DesktopApi, type ShellState } from '../shared/types'

const api: DesktopApi = {
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
  openRecent: (root) => ipcRenderer.invoke(IPC.openRecent, root),
  showStart: () => ipcRenderer.invoke(IPC.showStart),
  retry: () => ipcRenderer.invoke(IPC.retry)
}

contextBridge.exposeInMainWorld('kosDesktop', api)

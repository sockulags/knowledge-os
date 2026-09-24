// Exposes only the clone calls to the Clone Knowledge Base window. The main
// process answers them only for that window.

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { CLONE_IPC, type CloneApi, type CloneProgress } from '../shared/clone'

const api: CloneApi = {
  defaults: () => ipcRenderer.invoke(CLONE_IPC.defaults),
  chooseParent: (current) => ipcRenderer.invoke(CLONE_IPC.chooseParent, current),
  start: (request) => ipcRenderer.invoke(CLONE_IPC.start, request),
  cancel: () => ipcRenderer.invoke(CLONE_IPC.cancel),
  onProgress: (callback) => {
    const listener = (_event: IpcRendererEvent, progress: CloneProgress): void => callback(progress)
    ipcRenderer.on(CLONE_IPC.progress, listener)
    return () => {
      ipcRenderer.removeListener(CLONE_IPC.progress, listener)
    }
  },
  open: (root) => ipcRenderer.invoke(CLONE_IPC.open, root),
  close: () => ipcRenderer.invoke(CLONE_IPC.close)
}

contextBridge.exposeInMainWorld('kosClone', api)

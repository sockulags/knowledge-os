// Exposes only the Referat import calls to the import window. The main
// process answers them only for that window.

import { contextBridge, ipcRenderer } from 'electron'
import { REFERAT_IPC, type ReferatApi } from '../shared/referat'

const api: ReferatApi = {
  context: () => ipcRenderer.invoke(REFERAT_IPC.context),
  listMeetings: () => ipcRenderer.invoke(REFERAT_IPC.listMeetings),
  preview: (meetingId, summaryId) => ipcRenderer.invoke(REFERAT_IPC.preview, meetingId, summaryId),
  importMeeting: (request) => ipcRenderer.invoke(REFERAT_IPC.importMeeting, request),
  retryFailed: () => ipcRenderer.invoke(REFERAT_IPC.retryFailed),
  launch: () => ipcRenderer.invoke(REFERAT_IPC.launch),
  openRecord: (id) => ipcRenderer.invoke(REFERAT_IPC.openRecord, id),
  close: () => ipcRenderer.invoke(REFERAT_IPC.close)
}

contextBridge.exposeInMainWorld('referat', api)

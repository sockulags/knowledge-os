// The shell's own wording for its window chrome, in one module: the in-app
// menu, the title bar, the update notices, the unsaved-changes dialog, and
// the Referat plugin's notices. The reader's wording stays in
// knowledge_os/reader/strings.py; the clone window's in cloneText.ts.

export const SHELL_TEXT = {
  appName: 'Knowledge OS',
  titleBar: {
    menubar: 'Application menu',
    dismiss: 'Dismiss',
    updateReady: 'Restart to update'
  },
  menu: {
    file: 'File',
    open: 'Open Knowledge Base…',
    create: 'New Knowledge Base…',
    openRecent: 'Open Recent',
    noRecent: 'No recent knowledge bases',
    reopenOnStart: 'Reopen the Last Knowledge Base on Start',
    close: 'Close Knowledge Base',
    exit: 'Exit',
    view: 'View',
    reload: 'Reload',
    devTools: 'Toggle Developer Tools',
    resetZoom: 'Actual Size',
    zoomIn: 'Zoom In',
    zoomOut: 'Zoom Out',
    fullScreen: 'Toggle Full Screen',
    help: 'Help',
    checkForUpdates: 'Check for Updates…',
    checkAutomatically: 'Check for Updates Automatically',
    restartToUpdate: 'Restart to Update ({version})'
  },
  update: {
    readyMessage: 'Knowledge OS {version} is ready to install.',
    readyDetail:
      'Restart now to update, or later from Help → Restart to Update. ' +
      'It is also installed the next time you quit.',
    restart: 'Restart to update',
    later: 'Later',
    onlyInstalled: 'Updates are only available in the installed app.',
    downloading: 'Knowledge OS {version} is downloading.',
    availableDownloading: 'Knowledge OS {version} is available and downloading.',
    downloadingDetail: 'You will be asked to restart when it is ready.',
    upToDate: 'Knowledge OS is up to date.',
    upToDateDetail: 'You have version {version}.',
    checkFailed: 'Could not check for updates.',
    downloadFailed: 'Could not download the update.',
    failedDetail: 'Check your internet connection and try again later.'
  },
  unsaved: {
    title: 'Unsaved changes',
    message: 'You have changes that are not saved.',
    detail: 'Leaving now discards them.',
    discard: 'Discard changes',
    keep: 'Keep editing'
  },
  referat: {
    menu: 'Referat',
    record: 'Record Meeting with Referat',
    import: 'Import Meeting from Referat…',
    alreadyRunning: 'Referat is already running.',
    alreadyRunningDetail: 'Switch to Referat to record the meeting.',
    notInstalledDetail:
      'Install Referat to record meetings. Meetings recorded with Referat can then be imported with Referat > Import Meeting from Referat.'
  }
} as const

/** Fill `{name}` placeholders. */
export function fillText(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match
  )
}

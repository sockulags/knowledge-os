// Build-time variables electron-vite bakes into the main process bundle.

interface ImportMetaEnv {
  /**
   * Local update tests only: a loopback URL that replaces the GitHub feed with
   * electron-updater's generic provider. Unset in release builds.
   */
  readonly MAIN_VITE_KOS_UPDATE_TEST_FEED?: string
}

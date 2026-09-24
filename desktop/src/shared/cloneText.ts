// Every user-facing string of Clone Knowledge Base, in one module: the File
// menu item, the start page's button, and the clone window. Messages that
// explain a failure come from the core (`kos clone`), which knows what went
// wrong; this module only titles them.

export const CLONE_TEXT = {
  menuItem: 'Clone Knowledge Base…',
  startButton: 'Clone from a URL…',
  windowTitle: 'Clone Knowledge Base',
  heading: 'Clone a knowledge base',
  intro:
    'Copy a knowledge base that lives in a Git repository to this computer, then open it. ' +
    'Git signs in with what is already set up here (a credential helper or an SSH key); ' +
    'the app never asks for or stores a password.',
  urlLabel: 'Repository address',
  urlPlaceholder: 'https://github.com/you/notes.git or git@github.com:you/notes.git',
  parentLabel: 'Save in',
  chooseParent: 'Choose…',
  chooseParentTitle: 'Choose where to save the knowledge base',
  chooseParentButton: 'Choose folder',
  nameLabel: 'Folder name',
  targetHint:
    'The knowledge base is cloned into {path}. The folder must not exist yet or be empty.',
  clone: 'Clone and open',
  cancel: 'Cancel',
  cancelling: 'Cancelling…',
  close: 'Close',
  tryAgain: 'Back to the form',
  openAnyway: 'Open anyway',
  phases: {
    starting: 'Starting Git…',
    clone: 'Downloading from the repository…',
    check: 'Checking that it is a knowledge base…',
    index: 'Building the search index…'
  },
  opening: 'Opening the knowledge base…',
  cancelled: 'The clone was cancelled. Nothing was kept.',
  lintTitle: 'Cloned, with problems',
  lintBody:
    'The knowledge base was cloned to {path}, but {count} of its files do not pass kos lint, so the ' +
    'search index was not built. Open it to see the problems.',
  errorTitles: {
    auth: 'Git could not sign in',
    network: 'The repository could not be reached',
    not_found: 'No repository at that address',
    timeout: 'The repository did not answer',
    bad_url: 'This address cannot be used',
    bad_name: 'This folder cannot be used',
    target_not_empty: 'The folder is not empty',
    not_a_knowledge_base: 'This repository is not a knowledge base',
    git_missing: 'Git is not installed',
    core: 'The clone could not start',
    failed: 'The clone did not finish'
  } as Record<string, string>,
  urlErrors: {
    empty: 'Enter the address of a Git repository.',
    spaces: 'A Git address cannot contain spaces or start with a dash.',
    scheme:
      'Use an https://, ssh://, git://, or file:// address, or git@host:owner/repository.git.',
    password:
      'Remove the password or token from the address. Sign in once with Git outside the app instead; the app never stores credentials.',
    shape:
      'This does not look like a Git address. Use https://host/owner/repository.git, git@host:owner/repository.git, or the full path of a folder.'
  },
  parentEmpty: 'Choose the folder to save the knowledge base in.',
  nameErrors: {
    empty: 'Enter a name for the new folder.',
    characters: 'A folder name cannot contain < > : " / \\ | ? * or end with a dot or space.',
    reserved: 'Windows reserves this name. Choose another.'
  }
} as const

/** Fill `{name}` placeholders. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match
  )
}

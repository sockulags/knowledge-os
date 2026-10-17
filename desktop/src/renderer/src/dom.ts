// Small DOM builders shared by the shell's own pages: the start page, the
// clone window, and the Referat import window.

export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (text !== undefined) node.textContent = text
  if (className !== undefined) node.className = className
  return node
}

export function button(
  label: string,
  action: () => void | Promise<void>,
  primary = false
): HTMLButtonElement {
  const node = element('button', label, primary ? 'primary' : undefined)
  node.type = 'button'
  node.addEventListener('click', () => {
    void action()
  })
  return node
}

/** A row of buttons. */
export function actions(...buttons: HTMLElement[]): HTMLElement {
  const row = element('div', undefined, 'actions')
  row.append(...buttons)
  return row
}

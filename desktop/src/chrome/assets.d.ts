// Vite's query imports the window chrome uses: a stylesheet as text and an
// SVG as markup, bundled into the preload script at build time.

declare module '*?inline' {
  const content: string
  export default content
}

declare module '*?raw' {
  const content: string
  export default content
}

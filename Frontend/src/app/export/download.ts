/** Saves a Blob as a file through a temporary link. */
export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoke after the click has been handled, or some browsers cancel the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

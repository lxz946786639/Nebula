export async function copyText(value: string) {
  const text = String(value || '')
  if (!text) throw new Error('Nothing to copy')

  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Fall through to the textarea fallback for browsers that expose the API but deny access.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  textarea.style.opacity = '0'

  const selection = document.getSelection()
  const selectedRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null

  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, textarea.value.length)

  let copied = false
  try {
    copied = document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
    if (selectedRange && selection) {
      selection.removeAllRanges()
      selection.addRange(selectedRange)
    }
  }

  if (!copied) throw new Error('Copy failed')
}

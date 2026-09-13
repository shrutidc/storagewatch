import { useState } from 'react'

// Browsers can't start programs on the visitor's Mac, so the closest thing to a
// one-click install is one click to copy, then a paste into Terminal.
function InstallCommand({ command }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
    } catch {
      // Clipboard blocked: the command is still shown below to copy by hand.
    }
  }

  return (
    <>
      <button className="explain-btn" onClick={copy}>
        {copied ? '✓ Copied — now paste it into Terminal' : 'Copy command'}
      </button>
      <pre className="command-box">{command}</pre>
      <ol className="install-steps">
        <li>Open Terminal: press ⌘ Space, type <strong>Terminal</strong>, press Return.</li>
        <li>Paste with ⌘ V and press Return.</li>
        <li>Click <strong>Connect</strong> when your browser asks.</li>
      </ol>
    </>
  )
}

export default InstallCommand

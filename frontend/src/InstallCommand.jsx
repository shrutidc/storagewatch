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
      <p className="section-sub">
        <a className="explain-btn" href="/StorageWatch-Mac.zip" download
           style={{ display: 'inline-block', textDecoration: 'none', marginRight: 10 }}>
          Download for Mac
        </a>
        No Terminal needed: unzip, move StorageWatch to Applications and open it (Apple
        silicon). The first time, allow it under System Settings → Privacy &amp; Security →
        Open Anyway.
      </p>
      <p className="section-sub">Or install from Terminal:</p>
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

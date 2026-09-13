// What StorageWatch collects, where it goes, and what it never touches.
//
// Written against the collector and the API rather than from a template: every
// claim below names something the code actually does, and the list of fields
// is the list the agent sends. If the collector changes, this changes with it.
function Privacy() {
  return (
    <div className="detail-section legal-page">
      <h2>Privacy</h2>
      <p className="section-sub">
        StorageWatch monitors storage, so almost everything it handles describes a disk.
        This page says exactly what that includes, because "storage data" could mean
        anything from a percentage to the contents of your files. It does not mean the
        second.
      </p>

      <h3>What the collector never reads</h3>
      <ul className="legal-list">
        <li><strong>The contents of any file.</strong> Nothing is opened, read or uploaded.</li>
        <li><strong>Individual file names.</strong> Sizes are measured with <code>du</code>,
          which reports totals per folder, not a listing.</li>
        <li><strong>Anything outside storage.</strong> No browsing, no keystrokes, no
          screen, no location, no other applications.</li>
      </ul>

      <h3>What it does send, every five seconds</h3>
      <ul className="legal-list">
        <li>Your Mac's hostname.</li>
        <li>Per mounted volume: the mount point, filesystem type, and total, used and
          free bytes.</li>
        <li>Read and write throughput, measured at the physical disk.</li>
      </ul>

      <h3>And about once a minute</h3>
      <ul className="legal-list">
        <li>Physical disks: model, capacity, bus, and SMART status.</li>
        <li>Block-level I/O error and retry counts, and average service time.</li>
        <li>APFS layout: container and volume names, identifiers, mount points, roles,
          and whether each is encrypted, sealed or FileVault-protected.</li>
        <li>Whether FileVault is on, and how many local Time Machine snapshots exist.</li>
        <li>Mounted network shares: the server address, the export path and the
          protocol version.</li>
        <li>Inode counts per filesystem.</li>
      </ul>

      <h3>Per-user sizing is off unless you turn it on</h3>
      <p className="legal-text">
        StorageWatch can also report how much each account's home directory holds, its
        quota, and the largest folders inside it — <strong>including those folder
        paths</strong>, which is the most personal thing it would ever send. Walking a
        home directory also makes macOS ask the agent for access to Documents, Desktop,
        Photos and Mail.
      </p>
      <p className="legal-text">
        Because of that it is disabled by default. A Mac only reports it if it is
        installed with <code>STORAGEWATCH_SIZE_HOMES=1</code>. Without that the section
        stays empty and no home directory is ever walked.
      </p>

      <h3>Where it goes</h3>
      <ul className="legal-list">
        <li><strong>The database.</strong> Telemetry is stored in Tiger Cloud
          (TimescaleDB) over an encrypted connection. Every row carries the account
          that owns it, and every query is filtered to the signed-in user — one
          administrator cannot see another's machines.</li>
        <li><strong>Auth0</strong> handles sign-in. StorageWatch receives your identity
          from it and never sees your password.</li>
        <li><strong>The assistant.</strong> This is the one place your data leaves our
          own services. When you ask <em>Ask Anything</em> a question, the current
          telemetry for the machine you are viewing is sent with it to Backboard, which
          routes it to Google Gemini. That is what lets it answer about your disk rather
          than in general. <strong>If you would rather no third party sees your
          telemetry, do not use the assistant</strong> — the rest of the dashboard does
          not call it.</li>
      </ul>

      <h3>What you control</h3>
      <ul className="legal-list">
        <li>Stop reporting at any time:
          {' '}<code>~/.storagewatch/venv/bin/python ~/.storagewatch/collector.py --uninstall</code>
        </li>
        <li>Leave per-user sizing off, which is the default.</li>
        <li>Avoid the assistant if you do not want telemetry sent onward.</li>
      </ul>

      <h3>Honest limitations</h3>
      <p className="legal-text">
        StorageWatch is a student project built for a filesystem-monitoring challenge,
        not a commercial service. There is no automatic deletion schedule, no data
        export, and no formal retention policy — if you want your rows removed, ask and
        they will be deleted from the database. Treat it accordingly.
      </p>
    </div>
  )
}

export default Privacy

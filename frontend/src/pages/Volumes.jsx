import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'

const NETWORK = ['nfs', 'smbfs', 'afpfs', 'webdav', 'cifs']

const statusOf = (percent) =>
  percent >= 90 ? ['Critical', 'bad'] : percent >= 80 ? ['Warning', 'warn'] : ['Healthy', 'good']

// Local volumes that aren't APFS — a USB drive formatted exFAT or HFS+, say.
// APFS volumes are covered by the APFS section and shares by Shared volumes, so
// listing them here as well would repeat the same numbers a third time.
function Volumes() {
  const { volumes } = useOutletContext()
  const other = volumes.filter(v => {
    const type = (v.filesystem_type || '').toLowerCase()
    return type !== 'apfs' && !NETWORK.includes(type)
  })
  if (!other.length) return null

  return (
    <div className="detail-section">
      <h2>Other volumes</h2>
      <div className="table-scroll">
        <table className="detail-table">
          <thead>
            <tr><th>Mount point</th><th>Type</th><th>Used</th><th>Free</th><th>Total</th><th>Status</th></tr>
          </thead>
          <tbody>
            {other.map(v => {
              const [label, cls] = statusOf(v.used_percent)
              return (
                <tr key={v.filesystem}>
                  <td><code>{v.filesystem}</code></td>
                  <td>{v.filesystem_type}</td>
                  <td>{bytes(v.used_bytes)} <span className="cell-note">{v.used_percent.toFixed(1)}%</span></td>
                  <td>{bytes(v.free_bytes)}</td>
                  <td>{bytes(v.total_bytes)}</td>
                  <td><span className={`pill ${cls}`}>{label}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Volumes

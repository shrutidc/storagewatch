import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'

// APFS containers and every volume in them. The boot container's capacity is the
// Storage card at the top, so it isn't repeated here; any other container's is.
function Apfs() {
  const { systemInfo } = useOutletContext()
  const containers = systemInfo?.apfs_containers || []
  if (!systemInfo || !containers.length) return null

  return (
    <div className="detail-section">
      <h2>APFS</h2>
      <p className="section-sub">
        From <code>diskutil apfs list</code> and <code>diskutil info</code> · FileVault{' '}
        {systemInfo.filevault_enabled ? 'on' : 'off'} · {systemInfo.snapshot_count} local
        snapshot{systemInfo.snapshot_count === 1 ? '' : 's'} · macOS-internal containers are omitted
      </p>

      {containers.map(c => {
        const used = c.capacity_ceiling - c.capacity_free
        // On a sealed system volume the Mac runs from a snapshot, not from the
        // volume, which is why that volume reports no mount point of its own.
        const booted = c.volumes.find(v => v.snapshot)?.snapshot
        // Older collectors send no mount point, seal state or snapshot at all.
        const stale = c.volumes.some(v => !('mount_point' in v))
        return (
          <div key={c.container_reference}>
            <h3>Container {c.container_reference}</h3>
            <p className="metric-detail">
              {!booted && <>{bytes(used)} in use of {bytes(c.capacity_ceiling)} · </>}
              backed by {c.physical_store || '—'}
              {c.physical_store_size ? ` (${bytes(c.physical_store_size)})` : ''}
              {c.uuid && <> · UUID <code>{c.uuid}</code></>}
            </p>
            {booted && (
              <p className="metric-detail">
                Booted from snapshot <code>{booted.device_identifier}</code> at{' '}
                <code>{booted.mount_point}</code>
                {booted.name && <> · <span className="wrap-anywhere">{booted.name}</span></>}
              </p>
            )}

            <div className="table-scroll">
              <table className="detail-table">
                <thead>
                  <tr>
                    <th>Name</th><th>Device</th><th>Mount point</th><th>Roles</th>
                    <th>In use</th><th>Encryption</th><th>FileVault</th><th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {c.volumes.map(v => (
                    <tr key={v.device_identifier || v.name}>
                      <td>{v.name}</td>
                      <td><code>{v.device_identifier || '—'}</code></td>
                      <td>
                        {v.mount_point ? (
                          <code>{v.mount_point}</code>
                        ) : v.snapshot ? (
                          <>
                            <code>{v.snapshot.mount_point}</code>
                            <span className="cell-note">via snapshot {v.snapshot.device_identifier}</span>
                          </>
                        ) : 'mount_point' in v ? (
                          <span className="cell-note">Not mounted</span>
                        ) : (
                          // The collector on this machine predates mount point
                          // reporting: it said nothing, not "unmounted".
                          <span className="cell-note">Not reported</span>
                        )}
                      </td>
                      <td>{v.roles.length ? v.roles.join(', ') : '—'}</td>
                      <td>{bytes(v.capacity_in_use)}</td>
                      <td>
                        <span className={`pill ${v.encrypted ? 'good' : ''}`}>
                          {v.encrypted ? 'Encrypted' : 'None'}
                        </span>
                      </td>
                      <td>
                        <span className={`pill ${v.filevault ? 'good' : ''}`}>
                          {v.filevault ? 'Protected' : '—'}
                        </span>
                      </td>
                      <td className="pill-stack">
                        {v.sealed && <span className="pill good">Sealed</span>}
                        {v.locked && <span className="pill bad">Locked</span>}
                        {/* Only meaningful for a mounted volume: diskutil
                            reports an unmounted one as unwritable either way. */}
                        {v.mount_point && !v.writable && <span className="pill">Read-only</span>}
                        {!v.sealed && !v.locked && (!v.mount_point || v.writable) && '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {stale && (
              <p className="section-sub toggle-status">
                Mount points, seal state and snapshots are blank because the collector on
                this Mac predates them. Re-run the installer on that Mac to fill them in.
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default Apfs

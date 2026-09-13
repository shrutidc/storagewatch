import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'

const us = (n) => (n == null ? '—' : `${Number(n).toFixed(0)} µs`)
const orDash = (n) => (n == null ? '—' : n)

// Physical disks and how healthy they are, one row each. SMART is diskutil's
// single word, which stays "Verified" until a disk is already failing; the error
// and retry counts come from the kernel's block storage driver and rise long
// before that.
function Disks() {
  const { systemInfo } = useOutletContext()
  if (!systemInfo) {
    return (
      <div className="detail-section">
        <h2>Physical disks</h2>
        <p className="section-sub">Waiting for the collector's first disk report (about a minute)…</p>
      </div>
    )
  }

  const disks = systemInfo.physical_disks || []
  const health = systemInfo.block_health || {}
  // Block devices the driver reports that diskutil doesn't list as a disk.
  const unlisted = Object.keys(health).filter(b => !disks.some(d => d.device_identifier === b))
  const rows = [
    ...disks.map(d => ({ bsd: d.device_identifier, disk: d, h: health[d.device_identifier] })),
    ...unlisted.map(b => ({ bsd: b, disk: null, h: health[b] })),
  ]

  return (
    <div className="detail-section">
      <h2>Physical disks</h2>
      <p className="section-sub">
        Errors are I/O the hardware failed to complete; retries are I/O it had to repeat —
        both rise long before SMART stops saying “Verified”. Counts and latency are since boot.
      </p>
      <div className="table-scroll">
        <table className="detail-table">
          <thead>
            <tr>
              <th>Disk</th><th>Model</th><th>Media</th><th>Capacity</th><th>SMART</th>
              <th>Errors R/W</th><th>Retries R/W</th><th>Avg latency R/W</th><th>IOPS R/W</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ bsd, disk, h }) => {
              const smart = disk?.smart_status || '—'
              return (
                <tr key={bsd}>
                  <td><code>{bsd}</code></td>
                  <td>{disk?.model || '—'}</td>
                  <td>
                    {disk
                      ? `${disk.solid_state ? 'SSD' : 'HDD'} · ${disk.protocol} · ${disk.internal ? 'internal' : 'external'}${disk.removable ? ' · removable' : ''}`
                      : '—'}
                  </td>
                  <td>{disk ? bytes(disk.size_bytes) : '—'}</td>
                  <td>
                    <span className={`pill ${smart === 'Verified' ? 'good' : smart === '—' || smart === 'Not Supported' ? '' : 'bad'}`}>
                      {smart}
                    </span>
                  </td>
                  {h ? (
                    <>
                      <td>
                        <span className={`pill ${h.read_errors + h.write_errors ? 'bad' : 'good'}`}>
                          {h.read_errors} / {h.write_errors}
                        </span>
                      </td>
                      <td>
                        <span className={`pill ${h.read_retries + h.write_retries ? 'warn' : 'good'}`}>
                          {h.read_retries} / {h.write_retries}
                        </span>
                      </td>
                      <td>{us(h.avg_read_latency_us)} / {us(h.avg_write_latency_us)}</td>
                      <td>{orDash(h.read_iops)} / {orDash(h.write_iops)}</td>
                    </>
                  ) : (
                    <td colSpan={4} className="cell-note">No block driver statistics reported</td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {disks.filter(d => d.partitions?.length).map(d => (
        <p key={d.device_identifier} className="metric-detail">
          {d.device_identifier} partitions: {d.partitions
            .map(p => `${p.identifier} ${p.content} ${bytes(p.size_bytes)}`).join(' · ')}
        </p>
      ))}
    </div>
  )
}

export default Disks

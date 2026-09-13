import { useOutletContext } from 'react-router-dom'

const us = (n) => `${Number(n).toFixed(0)} µs`
// Null until the collector has two readings to take a rate between, which is
// one system-info refresh after it starts.
const mbps = (n) => (n == null ? '—' : `${(n / 1e6).toFixed(1)} MB/s`)
const iops = (n) => (n == null ? '—' : n)

// The health of the block devices underneath the filesystems.
//
// diskutil's SMART status is one word and stays "Verified" until a disk is
// already failing. The kernel's block storage driver counts every I/O it had
// to retry or could not complete, and how long the hardware took to answer —
// the earliest warning a Mac gives without installing smartctl.
function BlockHealth() {
  const { systemInfo } = useOutletContext()
  const health = systemInfo?.block_health || {}
  const disks = systemInfo?.physical_disks || []
  const entries = Object.entries(health)

  if (!entries.length) return null

  // The driver reports by BSD name; everything human (model, bus, SMART) comes
  // from diskutil's inventory of the same disk.
  const describe = (bsd) => disks.find(d => d.device_identifier === bsd) || {}

  return (
    <div className="detail-section">
      <h2>Block storage health</h2>
      <p className="section-sub">
        Straight from the kernel's block storage driver. Errors are I/O the hardware
        failed to complete; retries are I/O it got wrong once and had to repeat — both
        rise long before SMART stops saying “Verified”.
      </p>
      <div className="table-scroll">
        <table className="detail-table">
          <thead>
            <tr>
              <th>Disk</th><th>Model</th><th>SMART</th>
              <th>Errors R/W</th><th>Retries R/W</th>
              <th>Avg latency R/W</th><th>IOPS R/W</th><th>Throughput R/W</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([bsd, h]) => {
              const disk = describe(bsd)
              const errors = h.read_errors + h.write_errors
              const retries = h.read_retries + h.write_retries
              const smart = disk.smart_status || '—'
              return (
                <tr key={bsd}>
                  <td><code>{bsd}</code></td>
                  <td>{disk.model || '—'}</td>
                  <td>
                    <span className={`pill ${smart === 'Verified' ? 'good' : smart === '—' ? '' : 'bad'}`}>
                      {smart}
                    </span>
                  </td>
                  <td>
                    <span className={`pill ${errors ? 'bad' : 'good'}`}>
                      {h.read_errors} / {h.write_errors}
                    </span>
                  </td>
                  <td>
                    <span className={`pill ${retries ? 'warn' : 'good'}`}>
                      {h.read_retries} / {h.write_retries}
                    </span>
                  </td>
                  <td>{us(h.avg_read_latency_us)} / {us(h.avg_write_latency_us)}</td>
                  <td>{iops(h.read_iops)} / {iops(h.write_iops)}</td>
                  <td>{mbps(h.read_bytes_per_sec)} / {mbps(h.write_bytes_per_sec)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="section-sub toggle-status">
        Latency is the average time one operation took since boot. IOPS and throughput
        are measured between system-info refreshes (~60s), so they show sustained load
        rather than the instantaneous rate on the graph above.
      </p>
    </div>
  )
}

export default BlockHealth

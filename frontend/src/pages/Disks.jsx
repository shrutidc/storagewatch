import { useOutletContext } from 'react-router-dom'

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`

function Disks() {
  const { systemInfo } = useOutletContext()
  const disks = systemInfo?.physical_disks || []

  if (!systemInfo) {
    return (
      <div className="detail-section">
        <h2>Physical Disks</h2>
        <p className="section-sub">Waiting for disk info from the collector (refreshes every ~60s)...</p>
      </div>
    )
  }

  return (
    <>
      <div className="detail-section">
        <h2>Physical Disks</h2>
        <p className="section-sub">
          {disks.length} physical disk{disks.length === 1 ? '' : 's'} detected ·
          {' '}reported by <code>diskutil</code> on {systemInfo.hostname}
        </p>
      </div>

      {disks.map(d => {
        const healthy = d.smart_status === 'Verified'
        const smartCls = healthy ? 'good' : (d.smart_status === 'Not Supported' ? '' : 'bad')
        return (
          <div key={d.device_identifier} className="detail-section">
            <h2>{d.model}</h2>
            <p className="section-sub">
              {d.device_node} · <span className={`pill ${smartCls}`}>SMART: {d.smart_status}</span>
            </p>

            <table className="detail-table kv-table">
              <tbody>
                <tr><td>Disk model</td><td>{d.model}</td></tr>
                <tr><td>Device identifier</td><td>{d.device_identifier}</td></tr>
                <tr><td>Device node</td><td>{d.device_node}</td></tr>
                <tr><td>Media type</td><td>{d.solid_state ? 'SSD (solid state)' : 'HDD (rotational)'}</td></tr>
                <tr><td>Protocol</td><td>{d.protocol}</td></tr>
                <tr><td>Location</td><td>{d.internal ? 'Internal' : 'External'}</td></tr>
                <tr><td>Removable</td><td>{d.removable ? 'Yes' : 'No'}</td></tr>
                <tr><td>Ejectable</td><td>{d.ejectable ? 'Yes' : 'No'}</td></tr>
                <tr><td>Capacity</td><td>{gb(d.size_bytes)} ({d.size_bytes.toLocaleString()} bytes)</td></tr>
                <tr><td>Block size</td><td>{d.block_size ? `${d.block_size} bytes` : '—'}</td></tr>
                <tr><td>Health status</td><td>{d.smart_status}</td></tr>
              </tbody>
            </table>

            {d.partitions?.length > 0 && (
              <>
                <h3>Partitions ({d.partitions.length})</h3>
                <div className="table-scroll">
                  <table className="detail-table">
                    <thead>
                      <tr><th>Identifier</th><th>Content type</th><th>Size</th></tr>
                    </thead>
                    <tbody>
                      {d.partitions.map(p => (
                        <tr key={p.identifier}>
                          <td>{p.identifier}</td>
                          <td>{p.content}</td>
                          <td>{gb(p.size_bytes)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )
      })}
    </>
  )
}

export default Disks

import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const tb = (bytes) => bytes >= 1e12 ? `${(bytes / 1e12).toFixed(2)} TB` : `${(bytes / 1e9).toFixed(1)} GB`

function stats(values) {
  if (!values.length) return { current: 0, avg: 0, peak: 0 }
  // history arrives newest-first from the API
  return {
    current: values[0],
    avg: values.reduce((a, b) => a + b, 0) / values.length,
    peak: Math.max(...values),
  }
}

function Performance() {
  const { history, metrics, systemInfo } = useOutletContext()
  const reads = history.map(h => parseFloat(h.read))
  const writes = history.map(h => parseFloat(h.write))
  const r = stats(reads)
  const w = stats(writes)
  const io = systemInfo?.io_totals || {}

  return (
    <>
      <div className="detail-section">
        <h2>I/O Performance</h2>
        <p className="section-sub">
          {history.length} samples · throughput is measured at the physical disk level
          (macOS exposes no per-volume I/O counters)
        </p>

        <div className="table-scroll">
          <table className="detail-table">
            <thead>
              <tr><th></th><th>Current</th><th>Average</th><th>Peak</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Read throughput</td>
                <td>{r.current.toFixed(1)} MB/s</td>
                <td>{r.avg.toFixed(1)} MB/s</td>
                <td>{r.peak.toFixed(1)} MB/s</td>
              </tr>
              <tr>
                <td>Write throughput</td>
                <td>{w.current.toFixed(1)} MB/s</td>
                <td>{w.avg.toFixed(1)} MB/s</td>
                <td>{w.peak.toFixed(1)} MB/s</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="detail-section">
        <h2>Performance Graph</h2>
        <p className="section-sub">Last {history.length} samples, collected every 5 seconds</p>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} />
              <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p>Loading chart data...</p>
        )}
      </div>

      <div className="detail-section">
        <h2>Cumulative I/O (since boot)</h2>
        <p className="section-sub">Totals reported by the kernel for {metrics.hostname}</p>
        <table className="detail-table kv-table">
          <tbody>
            <tr><td>Total bytes read</td><td>{io.read_bytes_total !== undefined ? tb(io.read_bytes_total) : '—'}</td></tr>
            <tr><td>Total bytes written</td><td>{io.write_bytes_total !== undefined ? tb(io.write_bytes_total) : '—'}</td></tr>
            <tr><td>Read operations</td><td>{io.read_count !== undefined ? io.read_count.toLocaleString() : '—'}</td></tr>
            <tr><td>Write operations</td><td>{io.write_count !== undefined ? io.write_count.toLocaleString() : '—'}</td></tr>
          </tbody>
        </table>
      </div>
    </>
  )
}

export default Performance

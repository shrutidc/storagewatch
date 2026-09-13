import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { bytes } from '../format.js'

const avg = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0)
const peak = (v) => (v.length ? Math.max(...v) : 0)

// Throughput over time. The current reading is in the cards above, so this adds
// only what they can't show: the trend, its average and peak, and the totals
// since boot. macOS counts I/O per physical disk, not per volume.
function Performance() {
  const { history, systemInfo } = useOutletContext()
  const reads = history.map(h => h.read)
  const writes = history.map(h => h.write)
  const io = systemInfo?.io_totals || {}

  return (
    <div className="detail-section">
      <h2>I/O performance</h2>
      <p className="section-sub">
        Last {history.length} samples, 5 s apart · read avg {avg(reads).toFixed(1)} MB/s,
        peak {peak(reads).toFixed(1)} · write avg {avg(writes).toFixed(1)} MB/s,
        peak {peak(writes).toFixed(1)}
      </p>
      {history.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Legend />
            {/* No animation: data refreshes every 5 s and would redraw each time. */}
            <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p>Loading chart data...</p>
      )}
      {io.read_bytes_total !== undefined && (
        <p className="metric-detail">
          Since boot: {bytes(io.read_bytes_total)} read in {io.read_count.toLocaleString()} operations
          · {bytes(io.write_bytes_total)} written in {io.write_count.toLocaleString()}
        </p>
      )}
    </div>
  )
}

export default Performance

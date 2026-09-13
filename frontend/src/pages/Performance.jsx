import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { bytes } from '../format.js'

const avg = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0)
const peak = (v) => (v.length ? Math.max(...v) : 0)

// The axis carries hours and minutes only — seconds on every tick was what
// made the row unreadable, and five seconds of precision is not what anyone
// reads off an axis. The tooltip still gives the exact second.
// Recharts spaces ticks by pixels, which with samples five seconds apart puts
// two in the same minute and prints the same label twice. Choosing the ticks
// from the data instead guarantees they are far enough apart to be distinct,
// whatever the width.
const TARGET_TICKS = 8
const pickTicks = (history) => {
  if (history.length <= TARGET_TICKS) return undefined
  const step = Math.ceil(history.length / TARGET_TICKS)
  const ticks = history.filter((_, i) => i % step === 0).map(h => h.time)
  const last = history[history.length - 1].time
  // The right-hand end is the most recent reading, so it always gets a label.
  if (ticks[ticks.length - 1] !== last) ticks.push(last)
  return ticks
}

const axisTime = (t) =>
  new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const exactTime = (t) =>
  new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })

// Throughput over time. The current reading is in the cards above, so this adds
// only what they can't show: the trend, its average and peak, and the totals
// since boot. macOS counts I/O per physical disk, not per volume.
function Performance() {
  const { history, systemInfo } = useOutletContext()
  const reads = history.map(h => h.read)
  const writes = history.map(h => h.write)
  const io = systemInfo?.io_totals || {}
  const ticks = pickTicks(history)

  return (
    <div className="detail-section">
      <h2>
        I/O performance
        {/* The chart redraws every five seconds; this says so without needing
            a timestamp that would itself be stale between polls. */}
        <span className="live-badge"><span className="live-dot" />Live</span>
      </h2>
      <p className="section-sub">
        Last {history.length} samples, 5 s apart · read avg {avg(reads).toFixed(1)} MB/s,
        peak {peak(reads).toFixed(1)} · write avg {avg(writes).toFixed(1)} MB/s,
        peak {peak(writes).toFixed(1)}
      </p>
      {history.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" />
            {/* minTickGap drops labels that would collide, so the number of
                ticks follows the width of the chart rather than the number of
                samples. */}
            <XAxis
              dataKey="time"
              tickFormatter={axisTime}
              ticks={ticks}
              interval="preserveStartEnd"
              minTickGap={56}
              tickMargin={10}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }}
              tick={{ fontSize: 12 }}
            />
            <Tooltip
              labelFormatter={exactTime}
              formatter={(v, name) => [`${v} MB/s`, name]}
            />
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

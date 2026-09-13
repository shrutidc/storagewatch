// Shared storage is measured in terabytes and petabytes, not gigabytes: a
// 40 TB NFS export rendered as "40000.0 GB" is technically true and useless.
const UNITS = [
  [1e15, 'PB'],
  [1e12, 'TB'],
  [1e9, 'GB'],
  [1e6, 'MB'],
  [1e3, 'kB'],
]

export function bytes(n) {
  if (n == null) return '—'
  const negative = n < 0
  const size = Math.abs(n)
  for (const [scale, unit] of UNITS) {
    if (size >= scale) {
      return `${negative ? '-' : ''}${(size / scale).toFixed(1)} ${unit}`
    }
  }
  return `${negative ? '-' : ''}${size.toFixed(0)} B`
}

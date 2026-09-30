import { useId } from 'react'

// A circular date postmark: the source name runs around the ring, the date sits in the middle.
export default function Postmark({ top, date, bottom = 'IMPORTED', className = 'postmark' }) {
  const id = useId().replace(/:/g, '')
  const label = (top || '').toUpperCase().slice(0, 22)
  const [day, rest] = splitDate(date)
  return (
    // Decorative: every postmark sits next to text that says the same thing.
    <svg className={className} viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        <path id={`t${id}`} d="M 16 50 A 34 34 0 0 1 84 50" />
        <path id={`b${id}`} d="M 14 52 A 36 36 0 0 0 86 52" />
      </defs>
      <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="3" fill="none" />
      <circle cx="50" cy="50" r="30" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <text fill="currentColor" fontFamily="Figtree Variable, Figtree, sans-serif" fontWeight="700" fontSize="11" letterSpacing="1.5">
        <textPath href={`#t${id}`} startOffset="50%" textAnchor="middle">{label}</textPath>
      </text>
      <text fill="currentColor" fontFamily="Figtree Variable, Figtree, sans-serif" fontWeight="600" fontSize="9" letterSpacing="2">
        <textPath href={`#b${id}`} startOffset="50%" textAnchor="middle">{bottom}</textPath>
      </text>
      <text x="50" y="50" textAnchor="middle" fill="currentColor" fontFamily="Figtree Variable, Figtree, sans-serif" fontWeight="700" fontSize="20">{day}</text>
      <text x="50" y="63" textAnchor="middle" fill="currentColor" fontFamily="Figtree Variable, Figtree, sans-serif" fontWeight="600" fontSize="10" letterSpacing="1">{rest}</text>
    </svg>
  )
}

function splitDate(iso) {
  if (!iso) return ['—', '']
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const mon = new Date(y, m - 1, d).toLocaleDateString('en-CA', { month: 'short' }).toUpperCase().replace('.', '')
  return [String(d), `${mon} ${y}`]
}

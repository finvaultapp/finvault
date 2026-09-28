// FinVault mark: a small sorting case, six pigeonholes, one holding a letter.
export default function Logo({ className = 'brand-mark' }) {
  return (
    <svg className={className} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect x="2.5" y="4.5" width="27" height="23" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M11.5 5v22M20.5 5v22M3 16h26" stroke="currentColor" strokeWidth="2" />
      <rect x="13.5" y="8.5" width="5" height="5" style={{ fill: "var(--tray)" }} />
    </svg>
  )
}

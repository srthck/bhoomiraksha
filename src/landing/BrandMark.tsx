/**
 * Bhoomi Raksha mark — a shield (raksha / protection) enclosing a leaf and
 * two terrain contours (bhoomi / land). Drawn rather than imported so it
 * renders at any size with no network dependency.
 */
export function BrandMark({ size = 42 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="brandLeaf" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#f7a93c" />
          <stop offset="0.52" stopColor="#5fbf6b" />
          <stop offset="1" stopColor="#1f8a52" />
        </linearGradient>
      </defs>
      <path
        d="M24 3.4 41.4 9.6v13.7c0 9.9-6.7 17.9-17.4 21.3C13.3 41.2 6.6 33.2 6.6 23.3V9.6Z"
        stroke="url(#brandLeaf)"
        strokeWidth="2.6"
        fill="rgba(47,161,94,0.10)"
      />
      <path
        d="M24 33.4c-6.6 0-10.6-4.4-10.6-9.9 0-1.4.3-2.7.8-3.8 3.2 2.6 6.5 3.3 9.8 3.3s6.6-.7 9.8-3.3c.5 1.1.8 2.4.8 3.8 0 5.5-4 9.9-10.6 9.9Z"
        fill="url(#brandLeaf)"
        opacity="0.92"
      />
      <path d="M24 33.4V20.6" stroke="#06210f" strokeWidth="1.6" strokeLinecap="round" opacity="0.55" />
      <path
        d="M14.6 15.2c3.2-3 6.4-4.4 9.4-4.4s6.2 1.4 9.4 4.4"
        stroke="#f7a93c"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

export function IndiaFlag() {
  return (
    <svg className="flag-chip" viewBox="0 0 30 21" aria-hidden="true">
      <rect width="30" height="7" fill="#f39325" />
      <rect y="7" width="30" height="7" fill="#f4f5ef" />
      <rect y="14" width="30" height="7" fill="#2fa15e" />
      <circle cx="15" cy="10.5" r="2.6" fill="none" stroke="#0d2f6b" strokeWidth="0.9" />
    </svg>
  )
}

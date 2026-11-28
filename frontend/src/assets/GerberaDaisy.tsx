interface Props {
  className?: string
}

// Original thin line-art gerbera daisy. Uses currentColor so it inherits from
// the parent's text color, making it easy to tint via Tailwind (e.g. text-brand/30).
export default function GerberaDaisy({ className }: Props) {
  // 16 narrow petals radiating from center.
  // Each ellipse is centered 27 units above the origin's center (50,50),
  // giving an inner gap of ~12 and an outer reach of ~42.
  const petals = Array.from({ length: 16 }, (_, i) => i * 22.5)

  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      {petals.map((angle) => (
        <ellipse
          key={angle}
          cx="50"
          cy="23"
          rx="2.5"
          ry="15"
          stroke="currentColor"
          strokeWidth="1.2"
          transform={`rotate(${angle} 50 50)`}
        />
      ))}
      {/* Outer disc ring */}
      <circle cx="50" cy="50" r="10" stroke="currentColor" strokeWidth="1.5" />
      {/* Inner disc detail */}
      <circle cx="50" cy="50" r="5.5" stroke="currentColor" strokeWidth="1" />
    </svg>
  )
}

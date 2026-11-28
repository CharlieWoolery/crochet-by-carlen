interface Props {
  className?: string
}

// Original thin line-art wildflowers (Texas field style): three 5-petal flowers
// on slightly curved stems with a few leaves. Uses currentColor for easy tinting.
export default function Wildflowers({ className }: Props) {
  return (
    <svg
      viewBox="0 0 140 90"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* ── Left flower ── */}
      <path d="M 25 85 C 24 68 21 52 25 20" stroke="currentColor" strokeWidth="1.2" />
      <path d="M 23 56 C 16 51 13 55 17 59" stroke="currentColor" strokeWidth="1" />
      <Flower cx={25} cy={20} />

      {/* ── Centre flower (taller) ── */}
      <path d="M 70 85 C 68 66 73 46 68 10" stroke="currentColor" strokeWidth="1.2" />
      <path d="M 70 55 C 76 50 79 54 75 58" stroke="currentColor" strokeWidth="1" />
      <path d="M 69 36 C 63 31 61 35 65 39" stroke="currentColor" strokeWidth="1" />
      <Flower cx={68} cy={10} />

      {/* ── Right flower ── */}
      <path d="M 115 85 C 114 68 119 52 114 24" stroke="currentColor" strokeWidth="1.2" />
      <path d="M 115 60 C 121 55 124 59 120 63" stroke="currentColor" strokeWidth="1" />
      <Flower cx={114} cy={24} />
    </svg>
  )
}

// Five-petal flower: narrow ellipses rotated 72° apart around the centre point.
function Flower({ cx, cy }: { cx: number; cy: number }) {
  return (
    <>
      {[0, 72, 144, 216, 288].map((angle) => (
        <ellipse
          key={angle}
          cx={cx}
          cy={cy - 5}
          rx="2.2"
          ry="5.5"
          stroke="currentColor"
          strokeWidth="1"
          transform={`rotate(${angle} ${cx} ${cy})`}
        />
      ))}
      <circle cx={cx} cy={cy} r="3" stroke="currentColor" strokeWidth="1" />
    </>
  )
}

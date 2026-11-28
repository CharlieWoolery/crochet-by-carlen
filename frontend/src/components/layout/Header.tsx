import { NavLink } from 'react-router-dom'

const NAV = [
  { label: 'Shop', to: '/shop' },
  { label: 'Past Work', to: '/past-work' },
  { label: 'Custom Requests', to: '/custom-request' },
  { label: 'About', to: '/about' },
]

export default function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-sm border-b border-blush">
      <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        <NavLink to="/" aria-label="Home">
          <img
            src="/logo.png"
            alt="Crochet by Carlen"
            className="h-9 w-auto"
          />
        </NavLink>

        {/* Scrollable on small phones so all labels stay visible */}
        <nav className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide">
          {NAV.map(({ label, to }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-blush text-brand-600'
                    : 'text-ink/60 hover:text-ink hover:bg-brand-50'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

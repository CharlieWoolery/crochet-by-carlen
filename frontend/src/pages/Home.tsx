import { Link } from 'react-router-dom'
import GerberaDaisy from '../assets/GerberaDaisy'

export default function Home() {
  return (
    <div>
      {/* Hero */}
      <section className="flex flex-col items-center justify-center px-4 py-16 text-center">
        <img
          src="/logo.png"
          alt="Crochet by Carlen"
          className="w-56 h-auto mb-6"
        />
        <h1 className="font-display italic font-light text-4xl sm:text-5xl text-ink mb-4">
          Handmade with love
        </h1>
        <p className="text-ink/60 text-sm max-w-xs leading-relaxed">
          Custom crochet pieces made just for you, one stitch at a time.
        </p>
        <Link
          to="/shop"
          className="mt-8 inline-block bg-brand text-white px-7 py-3 rounded-full text-sm font-semibold hover:bg-brand-600 transition-colors"
        >
          Shop Now
        </Link>
      </section>

      {/* Section divider with daisy */}
      <div className="flex items-center justify-center gap-4 py-2 text-brand/25">
        <span className="flex-1 max-w-24 h-px bg-blush" />
        <GerberaDaisy className="w-9 h-9" />
        <span className="flex-1 max-w-24 h-px bg-blush" />
      </div>

      {/* Current collection preview — wired up once public /api/collections is live */}
      <section className="max-w-4xl mx-auto px-4 py-10">
        <h2 className="font-display italic font-light text-2xl text-ink text-center mb-8">
          Current Collection
        </h2>
        <p className="text-center text-ink/35 py-16 text-sm">
          Products coming soon.
        </p>
      </section>
    </div>
  )
}

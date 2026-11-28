export default function Admin() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="font-display italic font-light text-3xl text-ink mb-6">
        Admin
      </h1>
      {/*
        Owner-only dashboard. Touch-friendly and mobile-first for iPhone/iPad use.
        Will include: products, collections, orders, custom requests, settings.
        Auth: session cookie from POST /api/admin/login.
      */}
      <p className="text-ink/35 text-sm">Admin dashboard coming soon.</p>
    </div>
  )
}

export default function CustomRequest() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <h1 className="font-display italic font-light text-3xl text-ink mb-3">
        Custom Request
      </h1>
      <p className="text-ink/60 text-sm mb-8 leading-relaxed">
        Have something specific in mind? Send a request and Carlen will get back
        to you with a quote.
      </p>
      {/*
        Form fields: name, email, description, optional reference image URL.
        POSTs to /api/custom-requests.
      */}
      <p className="text-ink/35 text-sm">Request form coming soon.</p>
    </div>
  )
}

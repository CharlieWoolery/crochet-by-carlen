import GerberaDaisy from '../assets/GerberaDaisy'

export default function About() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-12 text-center">
      <img
        src="/logo.png"
        alt="Crochet by Carlen"
        className="w-48 h-auto mx-auto mb-8"
      />

      <h1 className="font-display italic font-light text-4xl text-ink mb-6">
        Welcome to Crochet by Carlen
      </h1>

      <div className="flex justify-center mb-8 text-brand/40">
        <GerberaDaisy className="w-14 h-14" />
      </div>

      <div className="space-y-5 text-base text-ink/75 leading-relaxed text-left sm:text-center">
        <p>
          Hi, I'm Carly Woolery, a self-taught crocheter who loves creating both
          useful and lovable items for others. Crocheting brings me so much joy,
          and my hope is that each piece I make brings joy to you as well.
        </p>
        <p>
          In 2023, my mother was diagnosed with breast cancer. I began selling my
          creations to help support her battle. I'm so thankful to share that she
          is now healed and doing well! She has always been the ultimate crafter,
          and I strive every day to reach her level of talent and creativity. 🩷
        </p>
        <p>
          Now that she has kicked cancer's butt, I'm excited to continue funding
          my crochet passion while also giving back to causes close to my heart.
        </p>
        <p>
          Each order is custom-made just for you. Thank you for your patience as
          I take the time to ensure every piece is crafted with love and care.
        </p>
      </div>
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import Wildflowers from '../../assets/Wildflowers'
import { apiFetch } from '../../lib/api'

interface PublicSettings {
  instagram_url: string | null
  facebook_url: string | null
  tiktok_url: string | null
  contact_email: string | null
}

function usePublicSettings() {
  return useQuery({
    queryKey: ['public-settings'],
    queryFn: () => apiFetch<PublicSettings>('/settings/public'),
    staleTime: 1000 * 60 * 10, // social links rarely change
  })
}

export default function Footer() {
  const { data: settings } = usePublicSettings()

  return (
    <footer className="border-t border-blush bg-white mt-12">
      {/* Wildflower divider */}
      <div className="flex justify-center pt-6 pb-2 text-brand/25">
        <Wildflowers className="w-28 h-auto" />
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6 flex flex-col items-center gap-4 text-sm text-ink/50">
        <p className="font-display italic text-base text-ink/70">Crochet by Carlen</p>

        {/* Social links */}
        <div className="flex items-center gap-5">
          {settings?.instagram_url && (
            <a
              href={settings.instagram_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Instagram"
              className="hover:text-brand transition-colors"
            >
              Instagram
            </a>
          )}
          {settings?.facebook_url && (
            <a
              href={settings.facebook_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Facebook"
              className="hover:text-brand transition-colors"
            >
              Facebook
            </a>
          )}
          {settings?.tiktok_url && (
            <a
              href={settings.tiktok_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="TikTok"
              className="hover:text-brand transition-colors"
            >
              TikTok
            </a>
          )}
          {settings?.contact_email && (
            <a
              href={`mailto:${settings.contact_email}`}
              aria-label="Email"
              className="hover:text-brand transition-colors"
            >
              {settings.contact_email}
            </a>
          )}
        </div>

        <p>© {new Date().getFullYear()} Crochet by Carlen. All rights reserved.</p>
      </div>
    </footer>
  )
}

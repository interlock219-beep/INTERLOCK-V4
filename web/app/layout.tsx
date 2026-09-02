import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { AuthProvider } from '@/components/AuthProvider'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: "Interlock — Control, Contain, Recover AI Agent Actions",
  description:
    "Interlock is a recovery and control plane for AI agents, helping teams authorize, observe, contain, recover, and verify agent-driven changes.",
  openGraph: {
    title: "Interlock — Control, Contain, Recover AI Agent Actions",
    description:
      "Interlock is a recovery and control plane for AI agents, helping teams authorize, observe, contain, recover, and verify agent-driven changes.",
    type: "website",
  },
  viewport: {
    width: "device-width",
    initialScale: 1,
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-intent-bg text-intent-text antialiased">
          <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-emerald-500 focus:text-black">
            Skip to main content
          </a>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}

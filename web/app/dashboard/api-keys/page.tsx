"use client"

import { motion } from "framer-motion"
import { Shield, Key } from "lucide-react"
import { useAuth } from "@/components/AuthProvider"

export default function ApiKeysPage() {
  const { user } = useAuth()

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">API Keys</h1>
        <p className="text-intent-muted">Manage your workspace API keys for SDK and CLI access.</p>
      </motion.div>

      <div className="glass-panel rounded-xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
            <Key className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-semibold">Default API Key</h2>
            <p className="text-sm text-intent-muted">Use this key in the Python SDK or CLI.</p>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center text-center py-10">
          <Key className="w-8 h-8 text-intent-muted mb-3" />
          <p className="text-sm text-intent-muted">API keys are not yet available</p>
          <p className="text-xs text-intent-muted mt-1 max-w-sm">
            Programmatic API keys for SDK and CLI access are coming soon. Check back here once they are enabled for your workspace.
          </p>
        </div>
      </div>
    </div>
  )
}

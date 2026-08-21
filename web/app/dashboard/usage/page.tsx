"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Activity } from "lucide-react"
import { api, type Usage } from "@/lib/api"

export default function UsagePage() {
  const [usage, setUsage] = useState<Usage[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    api.billing.getUsage()
      .then(setUsage)
      .catch(() => {})
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">Usage</h1>
        <p className="text-intent-muted">Track your resource consumption across the current billing period.</p>
      </motion.div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="loader" />
        </div>
      ) : usage.length === 0 ? (
        <div className="glass-panel rounded-xl p-12 text-center">
          <Activity className="w-12 h-12 text-intent-muted mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No usage recorded yet</h3>
          <p className="text-intent-muted">Start using IntentLock to see your metrics here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {usage.map((item, i) => (
            <motion.div
              key={item.resource_type}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-panel rounded-xl p-6"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium capitalize">{item.resource_type.replace(/_/g, " ")}</h3>
                <span className="text-xs text-intent-muted">{item.percentage?.toFixed(1) ?? 0}%</span>
              </div>
              <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden mb-2">
                <div
                  className="h-full bg-cyan-500 rounded-full transition-all"
                  style={{ width: `${Math.min(item.percentage || 0, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-intent-muted">{item.current} used</span>
                <span className="text-intent-muted">{item.limit ?? "Unlimited"} limit</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

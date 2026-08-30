"use client"

import Link from "next/link"
import { Shield, ArrowRight, Server, GitBranch, AlertTriangle, RotateCcw } from "lucide-react"
import { motion } from "framer-motion"

const sections = [
  {
    title: "Agent Inventory",
    description: "Monitor all agents, their trust levels, risk scores, and lineage.",
    href: "/dashboard/control-center/agents",
    icon: Server,
    color: "cyan",
  },
  {
    title: "Authority Explorer",
    description: "Visualize and drill into authority grants across the hierarchy.",
    href: "/dashboard/control-center/authority",
    icon: GitBranch,
    color: "purple",
  },
  {
    title: "Incident Center",
    description: "Investigate suspicious activity and initiate containment.",
    href: "/dashboard/control-center/incidents",
    icon: AlertTriangle,
    color: "red",
  },
  {
    title: "Recovery Center",
    description: "Review reversibility and execute recovery plans.",
    href: "/dashboard/control-center/recovery",
    icon: RotateCcw,
    color: "amber",
  },
]

export default function ControlCenterPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">Control Center</h1>
        <p className="text-intent-muted">
          Security operations hub for agent governance, authority management, and incident response.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sections.map((section, index) => (
          <motion.div
            key={section.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
          >
            <Link
              href={section.href}
              className="block glass-panel rounded-xl p-6 hover:bg-white/[0.05] transition-colors group"
            >
              <div className="flex items-start justify-between mb-4">
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    section.color === "cyan"
                      ? "bg-cyan-500/10 text-cyan-400"
                      : section.color === "purple"
                        ? "bg-purple-500/10 text-purple-400"
                        : section.color === "red"
                          ? "bg-red-500/10 text-red-400"
                          : "bg-amber-500/10 text-amber-400"
                  }`}
                >
                  <section.icon className="w-5 h-5" />
                </div>
                <ArrowRight className="w-4 h-4 text-intent-muted group-hover:text-intent-text transition-colors" />
              </div>
              <h3 className="font-semibold mb-1">{section.title}</h3>
              <p className="text-sm text-intent-muted">{section.description}</p>
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

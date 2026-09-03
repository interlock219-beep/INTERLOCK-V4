"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import {
  Server,
  Search,
  Filter,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  AlertTriangle,
  ChevronDown,
  X,
  RefreshCcw,
} from "lucide-react"
import { api, type Agent } from "@/lib/api"
import { useAuth } from "@/components/AuthProvider"

const statusConfig: Record<string, { label: string; color: string; icon: typeof ShieldCheck }> = {
  active: { label: "Active", color: "text-cyan-400 bg-cyan-500/10", icon: ShieldCheck },
  inactive: { label: "Inactive", color: "text-intent-muted bg-white/5", icon: ShieldOff },
  compromised: { label: "Compromised", color: "text-red-400 bg-red-500/10", icon: ShieldAlert },
  quarantined: { label: "Quarantined", color: "text-amber-400 bg-amber-500/10", icon: Shield },
}

const riskClassificationToScore = (classification: string): number => {
  switch (classification) {
    case "low": return 25
    case "medium": return 50
    case "high": return 75
    case "critical": return 90
    default: return 0
  }
}

const trustLevelToPercent = (level: string): number => {
  switch (level) {
    case "verified": return 90
    case "unverified": return 50
    case "discovered": return 30
    default: return 0
  }
}

const riskConfig = [
  { min: 0, max: 25, label: "Low", color: "text-cyan-400 bg-cyan-500/10" },
  { min: 25, max: 50, label: "Medium", color: "text-amber-400 bg-amber-500/10" },
  { min: 50, max: 75, label: "High", color: "text-orange-400 bg-orange-500/10" },
  { min: 75, max: 100, label: "Critical", color: "text-red-400 bg-red-500/10" },
]

function getRiskConfig(risk: number) {
  return riskConfig.find((r) => risk >= r.min && risk < r.max) || riskConfig[riskConfig.length - 1]
}

function getRiskScore(agent: Agent): { min: number; max: number; label: string; color: string } {
  return getRiskConfig(riskClassificationToScore(agent.risk_classification))
}

function formatRelativeTime(timestamp: string) {
  const diff = Date.now() - new Date(timestamp).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function AgentsPage() {
  const { user } = useAuth()
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [riskFilter, setRiskFilter] = useState<string>("all")
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    let active = true
    api.agents
      .list()
      .then((data) => active && setAgents(data))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setIsLoading(false))
    return () => {
      active = false
    }
  }, [])

  const filtered = agents.filter((agent) => {
    if (search && !agent.name.toLowerCase().includes(search.toLowerCase()) && !agent.agent_id.toLowerCase().includes(search.toLowerCase())) {
      return false
    }
    if (statusFilter !== "all" && agent.status !== statusFilter) {
      return false
    }
    if (riskFilter !== "all") {
      const riskConf = getRiskScore(agent)
      if (riskConf.label.toLowerCase() !== riskFilter.toLowerCase()) {
        return false
      }
    }
    return true
  })

  const handleUpdateStatus = async (agentId: string, status: string) => {
    try {
      const updated = await api.agents.update(agentId, { status })
      setAgents((prev) => prev.map((a) => (a.agent_id === agentId ? updated : a)))
      if (selectedAgent?.agent_id === agentId) {
        setSelectedAgent(updated)
      }
    } catch (err) {
      console.error("Failed to update agent:", err)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold mb-1">Agent Inventory</h1>
          <p className="text-intent-muted text-sm">
            {agents.length} agents registered to tenant
          </p>
        </div>
        <button
          onClick={() => {
            setIsLoading(true)
            api.agents
              .list()
              .then(setAgents)
              .catch((err) => setError(err.message))
              .finally(() => setIsLoading(false))
          }}
          className="p-2 rounded-lg hover:bg-white/5 text-intent-muted"
          title="Refresh"
        >
          <RefreshCcw className="w-4 h-4" />
        </button>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-intent-muted" />
          <input
            type="text"
            placeholder="Search by name or agent ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors"
          />
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
            showFilters ? "border-cyan-500/50 bg-cyan-500/10" : "border-white/10 hover:bg-white/5"
          }`}
        >
          <Filter className="w-4 h-4" />
          Filters
          {(statusFilter !== "all" || riskFilter !== "all") && (
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
          )}
        </button>
      </div>

      {showFilters && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex items-center gap-4 p-4 rounded-lg bg-white/5 border border-white/10"
        >
          <div className="flex items-center gap-2">
            <label className="text-sm text-intent-muted">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 rounded-md bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
            >
              <option value="all">All</option>
              {Object.keys(statusConfig).map((status) => (
                <option key={status} value={status}>
                  {statusConfig[status].label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-intent-muted">Risk</label>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="px-3 py-1.5 rounded-md bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
            >
              <option value="all">All</option>
              {riskConfig.map((r) => (
                <option key={r.label} value={r.label}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          {(statusFilter !== "all" || riskFilter !== "all") && (
            <button
              onClick={() => {
                setStatusFilter("all")
                setRiskFilter("all")
              }}
              className="flex items-center gap-1 text-sm text-intent-muted hover:text-red-400 transition-colors"
            >
              <X className="w-3 h-3" />
              Clear filters
            </button>
          )}
        </motion.div>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="loader" />
        </div>
      ) : (
        <div className="rounded-xl border border-white/10 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-white/5">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Agent</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Trust</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Risk</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Last Activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-intent-muted">
                      {agents.length === 0 ? "No agents registered yet." : "No agents match your filters."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((agent) => {
                    const statusConf = statusConfig[agent.status] || statusConfig.inactive
                    const riskConf = getRiskScore(agent)
                    const StatusIcon = statusConf.icon
                    return (
                      <tr
                        key={agent.agent_id}
                        onClick={() => setSelectedAgent(agent)}
                        className="hover:bg-white/5 cursor-pointer transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                              <Server className="w-4 h-4 text-cyan-400" />
                            </div>
                            <div>
                              <p className="font-medium">{agent.name}</p>
                              <p className="text-xs text-intent-muted font-mono">{agent.agent_id}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-intent-muted capitalize">{agent.agent_type}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs ${statusConf.color}`}>
                            <StatusIcon className="w-3 h-3" />
                            {statusConf.label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 rounded-full bg-white/10 overflow-hidden">
                              <div
                                className="h-full bg-cyan-400"
                                style={{ width: `${trustLevelToPercent(agent.trust_level)}%` }}
                              />
                            </div>
                            <span className="text-xs text-intent-muted w-8">{trustLevelToPercent(agent.trust_level)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs ${riskConf.color}`}>
                            {riskConf.label === "High" || riskConf.label === "Critical" ? (
                              <AlertTriangle className="w-3 h-3" />
                            ) : null}
                            {agent.risk_classification} · {riskConf.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-intent-muted">
                          {agent.last_activity_at ? formatRelativeTime(agent.last_activity_at) : "Never"}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedAgent && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => setSelectedAgent(null)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg glass-panel rounded-xl p-6"
          >
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                  <Server className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <h2 className="font-semibold">{selectedAgent.name}</h2>
                  <p className="text-xs text-intent-muted font-mono">{selectedAgent.agent_id}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedAgent(null)}
                className="p-1 rounded-lg hover:bg-white/5 text-intent-muted"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Type</p>
                  <p className="text-sm capitalize">{selectedAgent.agent_type}</p>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Status</p>
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs ${statusConfig[selectedAgent.status]?.color}`}>
                    {statusConfig[selectedAgent.status]?.label || selectedAgent.status}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Trust Level</p>
                  <p className="text-sm">{selectedAgent.trust_level}</p>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Risk</p>
                  <p className="text-sm">{selectedAgent.risk_classification}</p>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-white/5">
                <p className="text-xs text-intent-muted mb-1">Last Activity</p>
                <p className="text-sm">
                  {selectedAgent.last_activity_at
                    ? new Date(selectedAgent.last_activity_at).toLocaleString()
                    : "Never"}
                </p>
              </div>

              <div className="flex items-center gap-2 pt-4 border-t border-white/10">
                <p className="text-xs text-intent-muted mr-auto">Quick Actions</p>
                {["active", "inactive", "quarantined"].map((status) => (
                  <button
                    key={status}
                    onClick={() => handleUpdateStatus(selectedAgent.agent_id, status)}
                    disabled={selectedAgent.status === status}
                    className={`px-3 py-1.5 rounded-md text-xs capitalize transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      status === "active"
                        ? "bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20"
                        : status === "inactive"
                          ? "bg-white/5 text-intent-muted hover:bg-white/10"
                          : "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  )
}

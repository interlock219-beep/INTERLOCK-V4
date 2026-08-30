"use client"

import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  AlertTriangle,
  Search,
  RefreshCcw,
  Play,
  Shield,
  ShieldOff,
  ShieldCheck,
  X,
  CheckCircle,
  Loader,
  ChevronRight,
  FlaskConical,
  Send,
  AlertCircle,
} from "lucide-react"
import { api, type Incident, type ContainmentResult, type RecoverySimulation } from "@/lib/api"

const severityConfig = {
  low: { label: "Low", color: "text-cyan-400 bg-cyan-500/10" },
  medium: { label: "Medium", color: "text-amber-400 bg-amber-500/10" },
  high: { label: "High", color: "text-orange-400 bg-orange-500/10" },
  critical: { label: "Critical", color: "text-red-400 bg-red-500/10" },
}

const statusConfig = {
  open: { label: "Open", color: "text-red-400 bg-red-500/10", icon: AlertCircle },
  investigating: { label: "Investigating", color: "text-amber-400 bg-amber-500/10", icon: Search },
  contained: { label: "Contained", color: "text-cyan-400 bg-cyan-500/10", icon: ShieldCheck },
  resolved: { label: "Resolved", color: "text-intent-muted bg-white/5", icon: CheckCircle },
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

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [severityFilter, setSeverityFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
  const [blastRadius, setBlastRadius] = useState<{
    child_agents: string[]
    affected_resources: Record<string, string[]>
  } | null>(null)
  const [isLoadingBlast, setIsLoadingBlast] = useState(false)
  const [containmentMode, setContainmentMode] = useState(false)
  const [containmentAction, setContainmentAction] = useState("quarantine")
  const [containmentReason, setContainmentReason] = useState("")
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [preview, setPreview] = useState<RecoverySimulation | null>(null)
  const [isExecuting, setIsExecuting] = useState(false)
  const [result, setResult] = useState<ContainmentResult | null>(null)

  useEffect(() => {
    let active = true
    api.actions
      .list()
      .then((actions) => {
        if (!active) return
        const mapped = actions.map((action) => ({
          incident_id: action.action_id,
          agent_id: action.agent_id,
          agent_name: action.tool,
          severity: action.risk_score >= 0.75 ? "critical" : action.risk_score >= 0.5 ? "high" : action.risk_score >= 0.25 ? "medium" : "low",
          status: action.status === "suspicious" || action.risk_score >= 0.5 ? "open" : action.status,
          description: `${action.action_type} on ${action.resource}`,
          created_at: action.created_at,
          updated_at: action.created_at,
          blast_radius: [],
        }))
        setIncidents(mapped)
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setIsLoading(false))
    return () => {
      active = false
    }
  }, [])

  const filtered = incidents.filter((incident) => {
    if (search && !incident.agent_name.toLowerCase().includes(search.toLowerCase()) && !incident.description.toLowerCase().includes(search.toLowerCase())) {
      return false
    }
    if (severityFilter !== "all" && incident.severity !== severityFilter) {
      return false
    }
    if (statusFilter !== "all" && incident.status !== statusFilter) {
      return false
    }
    return true
  })

  const handleSelectIncident = async (incident: Incident) => {
    setSelectedIncident(incident)
    setBlastRadius(null)
    setContainmentMode(false)
    setPreview(null)
    setResult(null)
    setIsLoadingBlast(true)
    try {
      const data = await api.control.getBlastRadius(incident.agent_id)
      setBlastRadius({
        child_agents: data.child_agents,
        affected_resources: data.affected_resources,
      })
    } catch (err) {
      console.error("Failed to load blast radius:", err)
    } finally {
      setIsLoadingBlast(false)
    }
  }

  const handlePreview = async () => {
    if (!selectedIncident) return
    setIsPreviewing(true)
    setPreview(null)
    try {
      const data = await api.control.simulateRecovery({
        incident_action_id: selectedIncident.incident_id,
      })
      setPreview(data)
    } catch (err) {
      console.error("Preview failed:", err)
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleExecuteContainment = async () => {
    if (!selectedIncident) return
    setIsExecuting(true)
    setResult(null)
    try {
      const res = await api.control.createContainment({
        target_agent_id: selectedIncident.agent_id,
        mode: containmentAction,
        dry_run: false,
        reason: containmentReason,
      })
      setResult(res)
      setIncidents((prev) =>
        prev.map((inc) =>
          inc.incident_id === selectedIncident.incident_id ? { ...inc, status: "contained" } : inc
        )
      )
    } catch (err) {
      console.error("Containment failed:", err)
    } finally {
      setIsExecuting(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold mb-1">Incident Center</h1>
          <p className="text-intent-muted text-sm">
            {incidents.length} suspicious activities detected
          </p>
        </div>
        <button
          onClick={() => {
            setIsLoading(true)
            api.actions
              .list()
              .then((actions) => {
                const mapped = actions.map((action) => ({
                  incident_id: action.action_id,
                  agent_id: action.agent_id,
                  agent_name: action.tool,
                  severity: action.risk_score >= 0.75 ? "critical" : action.risk_score >= 0.5 ? "high" : action.risk_score >= 0.25 ? "medium" : "low",
                  status: action.status === "suspicious" || action.risk_score >= 0.5 ? "open" : action.status,
                  description: `${action.action_type} on ${action.resource}`,
                  created_at: action.created_at,
                  updated_at: action.created_at,
                  blast_radius: [],
                }))
                setIncidents(mapped)
              })
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
            placeholder="Search incidents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors"
          />
        </div>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
        >
          <option value="all">All Severities</option>
          {Object.keys(severityConfig).map((s) => (
            <option key={s} value={s}>
              {severityConfig[s as keyof typeof severityConfig].label}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
        >
          <option value="all">All Statuses</option>
          {Object.keys(statusConfig).map((s) => (
            <option key={s} value={s}>
              {statusConfig[s as keyof typeof statusConfig].label}
            </option>
          ))}
        </select>
      </div>

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
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Severity</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Agent</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Description</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-intent-muted">
                      {incidents.length === 0 ? "No incidents found." : "No incidents match your filters."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((incident) => {
                    const sevConf = severityConfig[incident.severity as keyof typeof severityConfig] || severityConfig.low
                    const statConf = statusConfig[incident.status as keyof typeof statusConfig] || statusConfig.open
                    const StatIcon = statConf.icon
                    return (
                      <tr
                        key={incident.incident_id}
                        onClick={() => handleSelectIncident(incident)}
                        className={`hover:bg-white/5 cursor-pointer transition-colors ${
                          selectedIncident?.incident_id === incident.incident_id ? "bg-cyan-500/5" : ""
                        }`}
                      >
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${sevConf.color}`}>
                            {incident.severity === "critical" || incident.severity === "high" ? (
                              <AlertTriangle className="w-3 h-3 mr-1" />
                            ) : null}
                            {sevConf.label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded bg-white/5 flex items-center justify-center">
                              <Shield className="w-3 h-3 text-intent-muted" />
                            </div>
                            <span className="text-sm">{incident.agent_name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-intent-muted max-w-xs truncate">{incident.description}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs ${statConf.color}`}>
                            <StatIcon className="w-3 h-3" />
                            {statConf.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-intent-muted">
                          {formatRelativeTime(incident.created_at)}
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

      {selectedIncident && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => {
            setSelectedIncident(null)
            setContainmentMode(false)
            setPreview(null)
            setResult(null)
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl glass-panel rounded-xl p-6 max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <h2 className="font-semibold">Incident {selectedIncident.incident_id}</h2>
                  <p className="text-xs text-intent-muted">{selectedIncident.description}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedIncident(null)
                  setContainmentMode(false)
                  setPreview(null)
                  setResult(null)
                }}
                className="p-1 rounded-lg hover:bg-white/5 text-intent-muted"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Agent</p>
                  <p className="text-sm">{selectedIncident.agent_name}</p>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Severity</p>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${severityConfig[selectedIncident.severity as keyof typeof severityConfig]?.color}`}>
                    {severityConfig[selectedIncident.severity as keyof typeof severityConfig]?.label}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Status</p>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${statusConfig[selectedIncident.status as keyof typeof statusConfig]?.color}`}>
                    {statusConfig[selectedIncident.status as keyof typeof statusConfig]?.label}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Created</p>
                  <p className="text-sm">{new Date(selectedIncident.created_at).toLocaleString()}</p>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-white/5">
                <h3 className="text-sm font-medium mb-3">Blast Radius</h3>
                {isLoadingBlast ? (
                  <div className="flex items-center justify-center py-6">
                    <Loader className="w-5 h-5 text-intent-muted animate-spin" />
                  </div>
                ) : blastRadius ? (
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs text-intent-muted mb-1">Affected Agents</p>
                      <div className="flex flex-wrap gap-1">
                        {blastRadius.child_agents.length > 0 ? blastRadius.child_agents.map((agent, i) => (
                          <span key={i} className="px-2 py-1 rounded bg-white/5 text-xs font-mono">
                            {agent}
                          </span>
                        )) : (
                          <span className="text-xs text-intent-muted">None</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-intent-muted mb-1">Resources</p>
                      <div className="flex flex-wrap gap-1">
                        {Object.keys(blastRadius.affected_resources).length > 0 ? Object.keys(blastRadius.affected_resources).map((resource, i) => (
                          <span key={i} className="px-2 py-1 rounded bg-red-500/10 text-xs text-red-400 font-mono">
                            {resource}
                          </span>
                        )) : (
                          <span className="text-xs text-intent-muted">None</span>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-intent-muted">No blast radius data available.</p>
                )}
              </div>

              {!containmentMode ? (
                <div className="pt-4 border-t border-white/10">
                  <button
                    onClick={() => setContainmentMode(true)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-sm"
                  >
                    <Shield className="w-4 h-4" />
                    Initiate Containment
                  </button>
                </div>
              ) : (
                <div className="space-y-4 pt-4 border-t border-white/10">
                  <h3 className="text-sm font-medium">Containment Configuration</h3>

                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-intent-muted block mb-1">Action</label>
                      <select
                        value={containmentAction}
                        onChange={(e) => setContainmentAction(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
                      >
                        <option value="quarantine">Quarantine</option>
                        <option value="revoke">Revoke Authority</option>
                        <option value="disable">Disable Agent</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-intent-muted block mb-1">Reason</label>
                      <textarea
                        value={containmentReason}
                        onChange={(e) => setContainmentReason(e.target.value)}
                        placeholder="Enter containment reason..."
                        rows={3}
                        className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 resize-none"
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handlePreview}
                      disabled={isPreviewing}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm hover:bg-white/10 transition-colors disabled:opacity-50"
                    >
                      {isPreviewing ? (
                        <Loader className="w-4 h-4 animate-spin" />
                      ) : (
                        <FlaskConical className="w-4 h-4" />
                      )}
                      Dry Run Preview
                    </button>
                    <button
                      onClick={handleExecuteContainment}
                      disabled={isExecuting || !containmentReason.trim()}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-sm disabled:opacity-50"
                    >
                      {isExecuting ? (
                        <Loader className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                      Execute Containment
                    </button>
                  </div>
                </div>
              )}

              <AnimatePresence>
                {preview && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="p-4 rounded-lg bg-amber-500/5 border border-amber-500/20"
                  >
                    <h4 className="text-sm font-medium text-amber-400 mb-2">Dry Run Preview</h4>
                    <div className="space-y-2 text-sm">
                      <p className="text-intent-muted">
                        <span className="text-intent-text">Affected actions:</span> {preview.affected_actions_count}
                      </p>
                      <div>
                        <p className="text-intent-muted mb-1">Irreversible actions:</p>
                        <div className="flex flex-wrap gap-1">
                          {preview.irreversible_actions.length > 0 ? preview.irreversible_actions.map((action, i) => (
                            <span key={i} className="px-2 py-0.5 rounded bg-white/5 text-xs font-mono">
                              {action}
                            </span>
                          )) : (
                            <span className="text-xs text-intent-muted">None</span>
                          )}
                        </div>
                      </div>
                      {preview.warnings.length > 0 && (
                        <div>
                          <p className="text-intent-muted mb-1">Warnings:</p>
                          <ul className="space-y-1">
                            {preview.warnings.map((warning, i) => (
                              <li key={i} className="flex items-center gap-2 text-xs text-amber-400">
                                <ChevronRight className="w-3 h-3" />
                                {warning}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <AnimatePresence>
                {result && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20"
                  >
                    <h4 className="text-sm font-medium text-cyan-400 mb-2">Containment Executed</h4>
                    <div className="space-y-1 text-sm">
                      <p className="text-intent-muted">
                        <span className="text-intent-text">ID:</span> {result.containment_id}
                      </p>
                      <p className="text-intent-muted">
                        <span className="text-intent-text">Status:</span> {result.status}
                      </p>
                      <p className="text-intent-muted">
                        <span className="text-intent-text">Blast radius:</span> {result.affected_agent_ids.length} agents, {result.affected_action_ids.length} actions affected
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  )
}

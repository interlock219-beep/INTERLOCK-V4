"use client"

import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  RotateCcw,
  Search,
  RefreshCcw,
  FlaskConical,
  Send,
  CheckCircle,
  Loader,
  X,
  ShieldCheck,
  ShieldX,
  ShieldQuestion,
  ChevronRight,
  Clock,
  AlertTriangle,
  UserCheck,
} from "lucide-react"
import { api, type ActionEntry, type RecoverySimulation, type RecoveryPlan } from "@/lib/api"

const reversibilityConfig = {
  reversible: { label: "Reversible", color: "text-cyan-400 bg-cyan-500/10", icon: ShieldCheck },
  irreversible: { label: "Irreversible", color: "text-red-400 bg-red-500/10", icon: ShieldX },
  unknown: { label: "Unknown", color: "text-intent-muted bg-white/5", icon: ShieldQuestion },
}

const statusConfig = {
  pending: { label: "Pending", color: "text-amber-400 bg-amber-500/10" },
  approved: { label: "Approved", color: "text-cyan-400 bg-cyan-500/10" },
  executed: { label: "Executed", color: "text-intent-muted bg-white/5" },
  failed: { label: "Failed", color: "text-red-400 bg-red-500/10" },
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

export default function RecoveryPage() {
  const [actions, setActions] = useState<ActionEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [reversibilityFilter, setReversibilityFilter] = useState<string>("all")
  const [selectedAction, setSelectedAction] = useState<ActionEntry | null>(null)
  const [simulation, setSimulation] = useState<RecoverySimulation | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)
  const [isExecuting, setIsExecuting] = useState(false)
  const [recoveryResult, setRecoveryResult] = useState<RecoveryPlan | null>(null)
  const [approvalNotes, setApprovalNotes] = useState("")
  const [approver, setApprover] = useState("")

  useEffect(() => {
    let active = true
    api.actions
      .list()
      .then((data) => active && setActions(data))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setIsLoading(false))
    return () => {
      active = false
    }
  }, [])

  const filtered = actions.filter((action) => {
    if (search && !action.action_type.toLowerCase().includes(search.toLowerCase()) && !action.resource.toLowerCase().includes(search.toLowerCase())) {
      return false
    }
    return true
  })

  const getReversibility = (simulation: RecoverySimulation): "reversible" | "irreversible" | "unknown" => {
    if (simulation.irreversible_actions.length > 0) return "irreversible"
    if (simulation.approval_required_actions.length > 0) return "unknown"
    return "reversible"
  }

  const handleSimulate = async (action: ActionEntry) => {
    setSelectedAction(action)
    setSimulation(null)
    setRecoveryResult(null)
    setIsSimulating(true)
    try {
      const data = await api.control.simulateRecovery({
        incident_action_id: action.action_id,
        recovery_steps: [],
      })
      setSimulation(data)
    } catch (err) {
      console.error("Simulation failed:", err)
    } finally {
      setIsSimulating(false)
    }
  }

  const handleExecuteRecovery = async () => {
    if (!simulation || !selectedAction) return
    if (!approver.trim()) return
    setIsExecuting(true)
    setRecoveryResult(null)
    try {
      const data = await api.control.executeRecovery({
        plan_id: simulation.plan_id,
        approved_by: approver,
      })
      setRecoveryResult(data)
      setActions((prev) => prev.filter((a) => a.action_id !== selectedAction.action_id))
    } catch (err) {
      console.error("Recovery execution failed:", err)
    } finally {
      setIsExecuting(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Recovery Center</h1>
        <p className="text-intent-muted text-sm">
          Review reversibility classifications and execute recovery plans with approval workflow.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-intent-muted" />
          <input
            type="text"
            placeholder="Search by action type or target..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors"
          />
        </div>
        <button
          onClick={() => {
            setIsLoading(true)
            api.actions
              .list()
              .then(setActions)
              .catch((err) => setError(err.message))
              .finally(() => setIsLoading(false))
          }}
          className="p-2 rounded-lg hover:bg-white/5 text-intent-muted"
          title="Refresh"
        >
          <RefreshCcw className="w-4 h-4" />
        </button>
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
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Action</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Agent</th>
                   <th className="text-left px-4 py-3 font-medium text-intent-muted">Resource</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Reversibility</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Risk</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Timestamp</th>
                  <th className="text-left px-4 py-3 font-medium text-intent-muted">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-intent-muted">
                      {actions.length === 0 ? "No actions found." : "No actions match your search."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((action) => {
                    const rev = getReversibility(action)
                    const revConf = reversibilityConfig[rev]
                    const RevIcon = revConf.icon
                    return (
                      <tr
                        key={action.action_id}
                        className="hover:bg-white/5 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded bg-white/5 flex items-center justify-center">
                              <RotateCcw className="w-3 h-3 text-intent-muted" />
                            </div>
                            <span className="font-medium capitalize">{action.action_type}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-intent-muted">{action.agent_id}</td>
                        <td className="px-4 py-3 font-mono text-xs">{action.resource}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs ${revConf.color}`}>
                            <RevIcon className="w-3 h-3" />
                            {revConf.label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs ${
                            action.risk_score >= 0.75 ? "text-red-400 bg-red-500/10" :
                            action.risk_score >= 0.5 ? "text-orange-400 bg-orange-500/10" :
                            action.risk_score >= 0.25 ? "text-amber-400 bg-amber-500/10" :
                            "text-cyan-400 bg-cyan-500/10"
                          }`}>
                            {action.risk_score}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-intent-muted">
                          {formatRelativeTime(action.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleSimulate(action)}
                            className="p-1.5 rounded-lg hover:bg-white/5 text-intent-muted hover:text-cyan-400 transition-colors"
                            title="Simulate recovery"
                          >
                            <FlaskConical className="w-4 h-4" />
                          </button>
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

      {selectedAction && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => {
            setSelectedAction(null)
            setSimulation(null)
            setRecoveryResult(null)
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
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <RotateCcw className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <h2 className="font-semibold">Recovery: {selectedAction.action_type}</h2>
                  <p className="text-xs text-intent-muted font-mono">{selectedAction.action_id}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedAction(null)
                  setSimulation(null)
                  setRecoveryResult(null)
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
                  <p className="text-sm">{selectedAction.agent_id}</p>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Resource</p>
                  <p className="text-sm font-mono">{selectedAction.resource}</p>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Reversibility</p>
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs ${reversibilityConfig[getReversibility(selectedAction)].color}`}>
                    {reversibilityConfig[getReversibility(selectedAction)].label}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-intent-muted mb-1">Risk</p>
                  <p className="text-sm capitalize">{selectedAction.risk}</p>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10">
                <button
                  onClick={() => handleSimulate(selectedAction)}
                  disabled={isSimulating}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm hover:bg-white/10 transition-colors disabled:opacity-50"
                >
                  {isSimulating ? (
                    <Loader className="w-4 h-4 animate-spin" />
                  ) : (
                    <FlaskConical className="w-4 h-4" />
                  )}
                  Simulate Recovery
                </button>
              </div>

              <AnimatePresence>
                {simulation && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-4"
                  >
                    <div className="p-4 rounded-lg bg-white/5">
                      <h4 className="text-sm font-medium mb-3">Recovery Plan</h4>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-intent-muted">Affected Actions</span>
                          <span className="text-intent-text">{simulation.affected_actions_count}</span>
                        </div>
                        <div>
                          <p className="text-xs text-intent-muted mb-1">Recovery Order</p>
                          <div className="space-y-1">
                            {simulation.recovery_order.map((actionId: string, i: number) => (
                              <div key={i} className="p-2 rounded bg-white/5">
                                <p className="text-xs font-mono">{actionId}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                        {simulation.warnings.length > 0 && (
                          <div>
                            <p className="text-xs text-intent-muted mb-1">Warnings</p>
                            <ul className="space-y-1">
                              {simulation.warnings.map((warning, i) => (
                                <li key={i} className="flex items-center gap-2 text-xs text-amber-400">
                                  <AlertTriangle className="w-3 h-3" />
                                  {warning}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>

                    {!recoveryResult ? (
                      <div className="p-4 rounded-lg bg-white/5 space-y-3">
                        <h4 className="text-sm font-medium">Approval Required</h4>
                        <div>
                          <label className="text-xs text-intent-muted block mb-1">Approver</label>
                          <input
                            type="text"
                            value={approver}
                            onChange={(e) => setApprover(e.target.value)}
                            placeholder="Enter approver name or email..."
                            className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-intent-muted block mb-1">Approval Notes</label>
                          <textarea
                            value={approvalNotes}
                            onChange={(e) => setApprovalNotes(e.target.value)}
                            placeholder="Add approval notes..."
                            rows={2}
                            className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 resize-none"
                          />
                        </div>
                        <button
                          onClick={handleExecuteRecovery}
                          disabled={isExecuting || !approver.trim()}
                          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors text-sm disabled:opacity-50"
                        >
                          {isExecuting ? (
                            <Loader className="w-4 h-4 animate-spin" />
                          ) : (
                            <Send className="w-4 h-4" />
                          )}
                          Execute Recovery
                        </button>
                      </div>
                    ) : (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20"
                      >
                        <h4 className="text-sm font-medium text-cyan-400 mb-2">Recovery Executed</h4>
                        <div className="space-y-1 text-sm">
                          <p className="text-intent-muted">
                            <span className="text-intent-text">Plan ID:</span> {recoveryResult.plan_id}
                          </p>
                          <p className="text-intent-muted">
                            <span className="text-intent-text">Status:</span> {recoveryResult.status}
                          </p>
                          <p className="text-intent-muted">
                            <span className="text-intent-text">Approved By:</span> {recoveryResult.approved_by}
                          </p>
                          <p className="text-intent-muted">
                            <span className="text-intent-text">Actions:</span> {recoveryResult.steps.length} steps
                          </p>
                        </div>
                      </motion.div>
                    )}
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

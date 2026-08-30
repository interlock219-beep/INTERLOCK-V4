"use client"

import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  GitBranch,
  ChevronRight,
  ChevronDown,
  Shield,
  ShieldCheck,
  ShieldX,
  Eye,
  EyeOff,
  Search,
  RefreshCcw,
  Lock,
  Unlock,
} from "lucide-react"
import { api, type AuthorityGrant, type GrantLineage } from "@/lib/api"

const scopeColors: Record<string, { bg: string; text: string; border: string }> = {
  read: { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/20" },
  write: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
  execute: { bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/20" },
  admin: { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/20" },
}

function ScopeBadge({ scope }: { scope: string }) {
  const conf = scopeColors[scope.toLowerCase()] || scopeColors.read
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs border ${conf.bg} ${conf.text} ${conf.border}`}>
      {scope.toLowerCase() === "admin" ? <ShieldX className="w-3 h-3" /> : <Shield className="w-3 h-3" />}
      {scope}
    </span>
  )
}

function TreeNode({
  node,
  depth,
  selected,
  onSelect,
  expanded,
  onToggle,
}: {
  node: { grant_id: string; scope: string; target_type: string; target_id: string; granted_by: string; granted_at: string; depth: number; children: any[] }
  depth: number
  selected: boolean
  onSelect: () => void
  expanded: boolean
  onToggle: () => void
}) {
  const hasChildren = node.children && node.children.length > 0
  const conf = scopeColors[node.scope.toLowerCase()] || scopeColors.read

  return (
    <div className="select-none">
      <div
        className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
          selected ? conf.bg : "hover:bg-white/5"
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={onSelect}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggle()
            }}
            className="p-0.5 rounded hover:bg-white/10"
          >
            {expanded ? (
              <ChevronDown className="w-3 h-3 text-intent-muted" />
            ) : (
              <ChevronRight className="w-3 h-3 text-intent-muted" />
            )}
          </button>
        ) : (
          <span className="w-4" />
        )}
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <span className="text-xs font-medium capitalize truncate">{node.target_type}</span>
          <span className="text-xs text-intent-muted font-mono truncate">{node.target_id}</span>
        </div>
        <ScopeBadge scope={node.scope} />
      </div>
      {hasChildren && expanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.grant_id}
              node={child}
              depth={depth + 1}
              selected={false}
              onSelect={() => {}}
              expanded={false}
              onToggle={() => {}}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function AuthorityPage() {
  const [grants, setGrants] = useState<AuthorityGrant[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [selectedGrant, setSelectedGrant] = useState<AuthorityGrant | null>(null)
  const [lineage, setLineage] = useState<GrantLineage | null>(null)
  const [isLoadingLineage, setIsLoadingLineage] = useState(false)
  const [showGraph, setShowGraph] = useState(false)
  const [scopeFilter, setScopeFilter] = useState<string>("all")

  useEffect(() => {
    let active = true
    api.authority
      .list()
      .then((data) => active && setGrants(data))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setIsLoading(false))
    return () => {
      active = false
    }
  }, [])

  const filtered = grants.filter((grant) => {
    if (search && !grant.resource.toLowerCase().includes(search.toLowerCase()) && !grant.grantee_agent_id.toLowerCase().includes(search.toLowerCase())) {
      return false
    }
    if (scopeFilter !== "all" && grant.scope.toLowerCase() !== scopeFilter.toLowerCase()) {
      return false
    }
    return true
  })

  const handleSelectGrant = async (grant: AuthorityGrant) => {
    setSelectedGrant(grant)
    setLineage(null)
    setIsLoadingLineage(true)
    try {
      const data = await api.authority.getLineage(grant.grant_id)
      setLineage(data)
    } catch (err) {
      console.error("Failed to load lineage:", err)
    } finally {
      setIsLoadingLineage(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Authority Explorer</h1>
        <p className="text-intent-muted text-sm">
          Visualize authority grants across human, agent, sub-agent, tool, and action hierarchy.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-intent-muted" />
          <input
            type="text"
            placeholder="Search by target or agent name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors"
          />
        </div>
        <select
          value={scopeFilter}
          onChange={(e) => setScopeFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm focus:outline-none focus:border-cyan-500/50"
        >
          <option value="all">All Scopes</option>
          {Object.keys(scopeColors).map((scope) => (
            <option key={scope} value={scope}>
              {scope.charAt(0).toUpperCase() + scope.slice(1)}
            </option>
          ))}
        </select>
        <button
          onClick={() => {
            setIsLoading(true)
            api.authority
              .list()
              .then(setGrants)
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-white/10 overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="loader" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-white/5">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Target</th>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Scope</th>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Grantee Agent</th>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Scope</th>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Grantor Agent</th>
                    <th className="text-left px-4 py-3 font-medium text-intent-muted">Expires</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-intent-muted">
                        {grants.length === 0 ? "No authority grants found." : "No grants match your filters."}
                      </td>
                    </tr>
                  ) : (
                    filtered.map((grant) => (
                      <tr
                        key={grant.grant_id}
                        onClick={() => handleSelectGrant(grant)}
                        className={`hover:bg-white/5 cursor-pointer transition-colors ${
                          selectedGrant?.grant_id === grant.grant_id ? "bg-cyan-500/5" : ""
                        }`}
                      >
                         <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded bg-white/5 flex items-center justify-center">
                              <GitBranch className="w-3 h-3 text-intent-muted" />
                            </div>
                            <div>
                              <p className="font-medium capitalize">{grant.scope}</p>
                              <p className="text-xs text-intent-muted font-mono">{grant.resource}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-intent-muted">{grant.grantee_agent_id}</td>
                        <td className="px-4 py-3">
                          <ScopeBadge scope={grant.scope} />
                        </td>
                        <td className="px-4 py-3 text-intent-muted">{grant.grantor_agent_id}</td>
                        <td className="px-4 py-3 text-intent-muted">
                          {grant.expires_at ? new Date(grant.expires_at).toLocaleDateString() : "Never"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <AnimatePresence mode="wait">
            {selectedGrant ? (
              <motion.div
                key="detail"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="glass-panel rounded-xl p-5 space-y-4"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-sm">Grant Details</h3>
                  <ScopeBadge scope={selectedGrant.scope} />
                </div>

                <div className="space-y-3">
                  <div className="p-3 rounded-lg bg-white/5">
                    <p className="text-xs text-intent-muted mb-1">Resource</p>
                    <p className="text-sm font-medium">{selectedGrant.resource}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-white/5">
                      <p className="text-xs text-intent-muted mb-1">Grantor Agent</p>
                      <p className="text-sm">{selectedGrant.grantor_agent_id}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5">
                      <p className="text-xs text-intent-muted mb-1">Grantee Agent</p>
                      <p className="text-sm">{selectedGrant.grantee_agent_id}</p>
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5">
                    <p className="text-xs text-intent-muted mb-1">Created</p>
                    <p className="text-sm">{new Date(selectedGrant.created_at).toLocaleString()}</p>
                  </div>
                </div>

                <div className="pt-3 border-t border-white/10">
                  <button
                    onClick={() => setShowGraph(!showGraph)}
                    className="flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    {showGraph ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    {showGraph ? "Hide" : "Show"} lineage tree
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="glass-panel rounded-xl p-6 text-center"
              >
                <GitBranch className="w-8 h-8 text-intent-muted mx-auto mb-3" />
                <p className="text-sm text-intent-muted">Select a grant to view lineage</p>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {showGraph && selectedGrant && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="glass-panel rounded-xl p-5 overflow-hidden"
              >
                <h3 className="font-semibold text-sm mb-3">Lineage Tree</h3>
                {isLoadingLineage ? (
                  <div className="flex items-center justify-center py-8">
                    <div className="loader" />
                  </div>
                ) : lineage ? (
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs text-intent-muted mb-1">Ancestors ({lineage.ancestors.length})</p>
                      <div className="space-y-1">
                        {lineage.ancestors.length === 0 ? (
                          <p className="text-xs text-intent-muted">None</p>
                        ) : lineage.ancestors.map((node, i) => (
                          <div key={i} className="flex items-center gap-2 p-2 rounded-lg hover:bg-white/5">
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium">{node.grantor_agent_id} → {node.grantee_agent_id}</p>
                              <p className="text-xs text-intent-muted font-mono">{node.resource}</p>
                            </div>
                            <ScopeBadge scope={node.scope} />
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-intent-muted mb-1">Descendants ({lineage.descendants_count})</p>
                      <div className="space-y-1">
                        {lineage.descendants.length === 0 ? (
                          <p className="text-xs text-intent-muted">None</p>
                        ) : lineage.descendants.map((node, i) => (
                          <div key={i} className="flex items-center gap-2 p-2 rounded-lg hover:bg-white/5">
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium">{node.grantor_agent_id} → {node.grantee_agent_id}</p>
                              <p className="text-xs text-intent-muted font-mono">{node.resource}</p>
                            </div>
                            <ScopeBadge scope={node.scope} />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-intent-muted">No lineage data available.</p>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {selectedGrant && (
            <div className="glass-panel rounded-xl p-5">
              <h3 className="font-semibold text-sm mb-3">Color Legend</h3>
              <div className="space-y-2">
                {Object.entries(scopeColors).map(([scope, conf]) => (
                  <div key={scope} className="flex items-center gap-2">
                    <span className={`w-3 h-3 rounded ${conf.bg} ${conf.border} border`} />
                    <span className="text-xs capitalize">{scope}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

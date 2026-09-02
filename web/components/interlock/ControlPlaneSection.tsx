"use client"

import { motion } from "framer-motion"
import {
  Users,
  GitBranch,
  Target,
  GaugeCircle,
  PauseOctagon,
  ClipboardList,
  FileCode,
  RotateCw,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface Capability {
  title: string
  description: string
  detail: string
  icon: ElementType
}

const capabilities: Capability[] = [
  {
    title: "Agents",
    description: "Registered agents with trust levels, risk classification, environment, and lineage.",
    detail:
      "agent_id, trust_level, risk_classification, parent_agent_id, model_provider — tracked as first-class records.",
    icon: Users,
  },
  {
    title: "Agent sessions",
    description: "Active sessions tracked for live inspection and containment targeting.",
    detail:
      "Sessions are frozen during containment so in-flight execution stops immediately.",
    icon: ClipboardList,
  },
  {
    title: "Authority grants",
    description: "Delegation chains from human sponsors through agent hierarchies.",
    detail:
      "grantor → grantee, with scope, resource, conditions, and delegation_depth enforced at authorization.",
    icon: GitBranch,
  },
  {
    title: "Action control",
    description: "Every tool action is authorized, evaluated, and journaled before execution.",
    detail:
      "Actions carry tool, resource, action_type, reversibility, risk_score, and correlation_id.",
    icon: Target,
  },
  {
    title: "Risk evaluation",
    description: "Deterministic policy and signal-based risk scoring.",
    detail:
      "YAML policy-as-code, regex destructive-SQL detection, and transfer limits feed the risk score.",
    icon: GaugeCircle,
  },
  {
    title: "Containment",
    description: "Quarantine the affected agent and revoke authority across its delegation chain.",
    detail:
      "Blast radius is calculated across agents, authorities, sessions, tokens, and actions.",
    icon: PauseOctagon,
  },
  {
    title: "Incident tracking",
    description: "Correlated audit trail of actions and decisions for an incident.",
    detail:
      "correlation_id and parent_action_id attribute every mutation to the originating action.",
    icon: ClipboardList,
  },
  {
    title: "Recovery evidence",
    description: "Immutable evidence captured at the domain boundary for every protected action.",
    detail:
      "Before/after state, compensation payload, idempotency key, and evidence hash.",
    icon: FileCode,
  },
  {
    title: "Recovery execution",
    description: "Dependency-ordered, durable, resumable recovery against real systems.",
    detail:
      "Reverse-topological order with idempotent steps and partial-recovery tracking.",
    icon: RotateCw,
  },
]

export function ControlPlaneSection() {
  return (
    <section id="control" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Control plane"
          title="Authorize, observe, contain, recover, verify."
          description="A single plane for governing agent-driven changes, from intent verification through post-incident recovery."
          align="center"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {capabilities.map((c, i) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.05 }}
              className={cn(
                "group relative rounded-2xl border border-white/5 bg-white/[0.03] p-7",
                "transition-colors hover:border-emerald-500/20",
              )}
            >
              <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-white/5 bg-white/[0.03] text-emerald-400 group-hover:scale-110 transition-transform">
                <c.icon className="h-6 w-6" />
              </div>
              <h3 className="text-xl font-semibold tracking-tight mb-2">{c.title}</h3>
              <p className="text-sm text-intent-muted leading-relaxed mb-3">{c.description}</p>
              <p className="text-xs text-intent-muted/60 italic leading-relaxed">{c.detail}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

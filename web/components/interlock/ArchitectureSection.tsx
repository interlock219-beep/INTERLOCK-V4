"use client"

import { motion } from "framer-motion"
import {
  Bot,
  ShieldCheck,
  Target,
  Eye,
  PauseOctagon,
  FileInput,
  RotateCw,
  SearchCheck,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface Stage {
  label: string
  description: string
  icon: ElementType
}

const stages: Stage[] = [
  {
    label: "AI AGENTS",
    description: "Agents invoke tools against production systems.",
    icon: Bot,
  },
  {
    label: "AUTHORIZATION",
    description: "ALLOW, DENY, or REQUIRE_HITL per service, action, and resource.",
    icon: ShieldCheck,
  },
  {
    label: "ACTION CONTROL",
    description: "Tool calls are gated by execution tokens and policy.",
    icon: Target,
  },
  {
    label: "OBSERVABILITY",
    description: "Every action is journaled with recovery evidence.",
    icon: Eye,
  },
  {
    label: "CONTAINMENT",
    description: "Quarantine agents, revoke authority, freeze sessions.",
    icon: PauseOctagon,
  },
  {
    label: "RECOVERY PLANNING",
    description: "Dependency-aware plan in reverse-topological order.",
    icon: FileInput,
  },
  {
    label: "RECOVERY EXECUTION",
    description: "Idempotent adapter compensation, resumable and partial-safe.",
    icon: RotateCw,
  },
  {
    label: "CONTINUOUS VERIFICATION",
    description: "Independent state comparison before success is reported.",
    icon: SearchCheck,
  },
]

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.16, delayChildren: 0.1 },
  },
}

const child = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
}

export function ArchitectureSection() {
  return (
    <section id="architecture" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="How it works"
          title="From intent to verified recovery."
          description="A single pass through Interlock: an agent's intent is authorized and recorded, the blast is contained, and any change is recovered and independently verified."
          align="center"
        />

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="inline-flex flex-col md:flex-row items-center justify-center gap-2 md:gap-1.5"
        >
          {stages.map((stage, i) => (
            <motion.span
              key={stage.label}
              variants={child}
              transition={{ duration: 0.4 }}
              className="flex items-center"
            >
            <motion.span
              whileHover={{ scale: 1.05 }}
                transition={{ type: "tween", duration: 0.2 }}
                className={cn(
                  "relative flex h-16 w-16 items-center justify-center",
                  "rounded-2xl border border-white/5 bg-white/[0.03]",
                  "text-emerald-400",
                  "transition-colors hover:border-emerald-500/20 hover:bg-emerald-500/5",
                )}
              >
                <stage.icon className="h-6 w-6" />
                {i < stages.length - 1 && (
                  <span className="pointer-events-none absolute -right-3 md:-right-4 top-1/2 -translate-y-1/2 text-emerald-500/30">
                    <ArrowRightIcon className="h-4 w-4" />
                  </span>
                )}
              </motion.span>
              <div className="sr-only md:not-sr-only md:ml-3 md:block">
                <span className="block text-xs font-medium tracking-widest uppercase text-emerald-300/60">
                  {stage.label}
                </span>
                <span className="block text-xs text-intent-muted mt-0.5 max-w-32">
                  {stage.description}
                </span>
              </div>
              {i < stages.length - 1 && (
                <span className="md:hidden text-emerald-500/30 mt-4 mb-2 flex justify-center">
                  <ArrowDownIcon className="h-4 w-4" />
                </span>
              )}
            </motion.span>
          ))}
        </motion.div>

        <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-16 rounded-2xl border border-white/5 bg-white/[0.03] p-6 md:p-8"
        >
          <p className="text-sm text-intent-muted leading-relaxed">
            The gateway is layered FastAPI (presentation) over use cases, domain
            services, and infrastructure adapters; Ed25519 execution tokens are
            consumed once against Redis (fail-closed), and durable state —
            approvals, audit, and recovery plans — is committed to PostgreSQL.
            Agentic runtimes integrate through the SDK at
            <span className="mx-1 text-emerald-300">`</span>
            /intent/verify
            <span className="mx-1 text-emerald-300">`</span> and
            <span className="mx-1 text-emerald-300">`</span>
            /intent/execute
            <span className="mx-1 text-emerald-300">`</span>.
          </p>
        </motion.div>
      </div>
    </section>
  )
}

function ArrowRightIcon(props: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("inline-block", props.className)}
    >
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="13 16 19 12 13 8" />
    </svg>
  )
}

function ArrowDownIcon(props: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("inline-block", props.className)}
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <polyline points="19 12 12 19 5 12" />
    </svg>
  )
}

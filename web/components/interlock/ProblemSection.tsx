"use client"

import { motion } from "framer-motion"
import { FileInput, Database, Settings, Workflow, Globe, Eye, Shield, Zap } from "lucide-react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

const capabilities = [
  { label: "CONTROL", icon: Shield, text: "Authorize and gate agent actions before execution." },
  { label: "CONTAIN", icon: Zap, text: "Quarantine agents, revoke authority, freeze sessions." },
  { label: "RECOVER", icon: Shield, text: "Classified, ordered compensation of agent-driven changes." },
  { label: "VERIFY", icon: Eye, text: "Independent confirmation of the resulting state." },
]

const mutationTypes = [
  { icon: FileInput, label: "Modify files" },
  { icon: Database, label: "Change databases" },
  { icon: Settings, label: "Alter configuration" },
  { icon: Workflow, label: "Trigger infrastructure" },
  { icon: Globe, label: "Call external systems" },
]

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
}

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
}

export function ProblemSection() {
  return (
    <section id="problem" className="relative pt-28 pb-24 sm:pt-32 sm:pb-28">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="The new failure mode"
          title={
            <>
              AI agents don't just generate text.
              <span className="gradient-text-emerald"> They can take action.</span>
            </>
          }
          description="Without a control plane between intent and execution, an agent can mutate files, databases, configuration, infrastructure, and external systems. Traditional monitoring can tell you that something happened."
          align="center"
        />

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-16"
        >
          {mutationTypes.map((m) => (
            <motion.div
              key={m.label}
              variants={item}
              className="flex flex-col items-center gap-3 rounded-xl bg-white/[0.03] border border-white/5 p-4 sm:p-5 text-center"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10">
                <m.icon className="h-5 w-5 text-emerald-400" />
              </div>
              <span className="text-sm text-intent-muted">{m.label}</span>
            </motion.div>
          ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mb-12 text-center"
        >
          <p className="text-sm font-medium tracking-widest uppercase text-intent-muted">
            Interlock focuses on
          </p>
        </motion.div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          {capabilities.map((c) => (
            <motion.div
              key={c.label}
              variants={item}
              className={cn(
                "group relative rounded-2xl border border-white/5 bg-white/[0.03] p-8 text-center",
                "transition-colors hover:border-emerald-500/20",
              )}
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-emerald-500/20 bg-emerald-500/10 group-hover:scale-110 transition-transform">
                <c.icon className="h-6 w-6 text-emerald-400" />
              </div>
              <h3 className="text-2xl font-bold tracking-tight mb-2">{c.label}</h3>
              <p className="text-sm text-intent-muted leading-relaxed">{c.text}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}

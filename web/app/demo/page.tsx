"use client"

import { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowRight, Play, RotateCcw, Github, Mail, Shield, ShieldCheck, ShieldAlert, ShieldX, ShieldQuestion, Container, FileSearch, FileText, CheckCircle2, Loader2 } from "lucide-react"
import { InterlockBrand } from "@/components/interlock/Brand"
import { cn } from "@/lib/utils"

const DEMO_STAGES = [
  {
    id: "agent-action",
    title: "AGENT ACTION",
    subtitle: "AI coding agent attempts to modify a production configuration file",
    fields: [
      { label: "Agent", value: "code-assistant-v3" },
      { label: "Tool", value: "filesystem.edit" },
      { label: "Resource", value: "/etc/production/config.yaml" },
      { label: "Action", value: "WRITE (overwrite)" },
      { label: "Risk level", value: "HIGH", color: "text-red-400" },
    ],
    icon: ShieldAlert,
    status: "observed",
    log: "[13:42:07.291] EVENT   agent_action.observed\n[13:42:07.291] ATTR    agent_id=code-assistant-v3\n[13:42:07.292] ATTR    tool=filesystem.edit\n[13:42:07.292] ATTR    resource=/etc/production/config.yaml\n[13:42:07.292] ATTR    action=WRITE\n[13:42:07.293] ATTR    risk=HIGH",
  },
  {
    id: "action-observed",
    title: "ACTION OBSERVED",
    subtitle: "Interlock records the action and attribution",
    fields: [
      { label: "Correlation ID", value: "evt_8f3a2c91d4e7b506" },
      { label: "Session ID", value: "ses_k2m4n6p8q1r5" },
      { label: "Authority", value: "delegated:ops-team" },
      { label: "Attribution", value: "code-assistant-v3 / user_8842" },
      { label: "Timestamp", value: "2026-09-04T13:42:07.291Z" },
    ],
    icon: FileSearch,
    status: "recorded",
    log: "[13:42:07.295] AUDIT   action.recorded\n[13:42:07.295] STORE   postgresql://audit/events\n[13:42:07.296] ATTR    correlation_id=evt_8f3a2c91d4e7b506\n[13:42:07.296] ATTR    session_id=ses_k2m4n6p8q1r5\n[13:42:07.297] ATTR    authority=delegated:ops-team",
  },
  {
    id: "risk-detected",
    title: "RISK DETECTED",
    subtitle: "The action is classified as high risk",
    fields: [
      { label: "Risk score", value: "0.94 / 1.0" },
      { label: "Classifier", value: "production_filesystem_write" },
      { label: "Policy", value: "restricted_paths.production" },
      { label: "Impact", value: "Potential service degradation" },
      { label: "Classification", value: "HIGH_RISK", color: "text-red-400" },
    ],
    icon: ShieldAlert,
    status: "classified",
    log: "[13:42:07.301] EVAL    risk.classified\n[13:42:07.302] POLICY  restricted_paths.production\n[13:42:07.302] RESULT  HIGH_RISK\n[13:42:07.303] SCORE   0.94\n[13:42:07.303] ACTION  containment.initiated",
  },
  {
    id: "session-contained",
    title: "SESSION CONTAINED",
    subtitle: "Agent quarantined, session frozen, authority revoked",
    fields: [
      { label: "Agent", value: "QUARANTINED" },
      { label: "Session", value: "FROZEN" },
      { label: "Authority", value: "REVOKED" },
      { label: "Blast radius", value: "Contained to agent change set" },
      { label: "Fail state", value: "CLOSED (no action executed)" },
    ],
    icon: Container,
    status: "contained",
    log: "[13:42:07.310] CONTAIN agent.quarantined\n[13:42:07.311] CONTAIN session.frozen\n[13:42:07.311] CONTAIN authority.revoked\n[13:42:07.312] STATUS  fail_closed\n[13:42:07.312] RESULT  No production state modified",
  },
  {
    id: "evidence-captured",
    title: "EVIDENCE CAPTURED",
    subtitle: "Before state, after state, correlation ID, recovery evidence, idempotency key",
    fields: [
      { label: "Before state", value: "config.yaml @ 13:42:07.290Z" },
      { label: "After state", value: "config.yaml @ 13:42:07.291Z (staged)" },
      { label: "Correlation ID", value: "evt_8f3a2c91d4e7b506" },
      { label: "Recovery evidence", value: "Captured (sha256: a3f8...)" },
      { label: "Idempotency key", value: "idem_7b2c9f1e4d6a" },
    ],
    icon: FileText,
    status: "captured",
    log: "[13:42:07.320] EVIDENCE before.state.hash=sha256:a3f8...\n[13:42:07.321] EVIDENCE after.state.hash=sha256:b7e2...\n[13:42:07.321] EVIDENCE correlation_id=evt_8f3a2c91d4e7b506\n[13:42:07.322] EVIDENCE idempotency_key=idem_7b2c9f1e4d6a\n[13:42:07.322] STATUS  evidence.complete",
  },
  {
    id: "recovery-plan",
    title: "RECOVERY PLAN GENERATED",
    subtitle: "Dependency-aware recovery plan in reverse-topological order",
    fields: [
      { label: "Adapter", value: "filesystem" },
      { label: "Strategy", value: "revert_file" },
      { label: "Dependencies", value: "[] (leaf resource)" },
      { label: "Plan steps", value: "1 step" },
      { label: "Risk", value: "REVERSIBLE" },
    ],
    icon: ShieldCheck,
    status: "planned",
    log: "[13:42:07.330] PLAN    recovery.plan.generated\n[13:42:07.331] ADAPTER filesystem.revert_file\n[13:42:07.331] DEPS    [] (leaf)\n[13:42:07.332] STEPS   1\n[13:42:07.332] RESULT  REVERSIBLE",
  },
  {
    id: "recovery-executed",
    title: "RECOVERY EXECUTED",
    subtitle: "Simulated recovery operation completed",
    fields: [
      { label: "Operation", value: "filesystem.revert_file" },
      { label: "Before", value: "config.yaml (modified)" },
      { label: "After", value: "config.yaml (restored)" },
      { label: "Duration", value: "142ms" },
      { label: "Status", value: "SUCCESS" },
    ],
    icon: RotateCcw,
    status: "executed",
    log: "[13:42:07.400] RECOVER filesystem.revert_file\n[13:42:07.401] EXEC    before=config.yaml(modified)\n[13:42:07.402] EXEC    after=config.yaml(restored)\n[13:42:07.542] DURATION 142ms\n[13:42:07.543] STATUS  SUCCESS",
  },
  {
    id: "verification",
    title: "INDEPENDENT VERIFICATION",
    subtitle: "Expected recovered state compared with actual state",
    fields: [
      { label: "Expected hash", value: "sha256:a3f8..." },
      { label: "Actual hash", value: "sha256:a3f8..." },
      { label: "Match", value: "YES" },
      { label: "Verification", value: "INDEPENDENT" },
      { label: "Status", value: "VERIFIED" },
    ],
    icon: CheckCircle2,
    status: "verified",
    log: "[13:42:07.550] VERIFY  state.comparison\n[13:42:07.551] EXPECTED sha256:a3f8...\n[13:42:07.551] ACTUAL   sha256:a3f8...\n[13:42:07.552] MATCH    true\n[13:42:07.552] RESULT  VERIFIED",
  },
  {
    id: "complete",
    title: "RECOVERY VERIFIED",
    subtitle: "The demonstration is simulated. No real production systems were modified.",
    fields: [
      { label: "Outcome", value: "SUCCESS" },
      { label: "Verification", value: "Independent state comparison passed" },
      { label: "Evidence", value: "Preserved in audit log" },
      { label: "Idempotency", value: "Key idem_7b2c9f1e4d6a reusable" },
      { label: "Note", value: "SIMULATED DEMO" },
    ],
    icon: ShieldCheck,
    status: "complete",
    log: "[13:42:07.560] RESULT  recovery.verified\n[13:42:07.561] STATUS  SUCCESS\n[13:42:07.561] AUDIT   event.closed\n[13:42:07.562] NOTE    SIMULATED_DEMO\n[13:42:07.562] END     Demonstration complete",
  },
]

export default function DemoPage() {
  const [currentStage, setCurrentStage] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [showEndCta, setShowEndCta] = useState(false)

  const addLogs = useCallback((stageLogs: string[]) => {
    setLogs((prev) => [...prev, ...stageLogs])
  }, [])

  const advanceStage = useCallback(() => {
    setCurrentStage((prev) => {
      if (prev < DEMO_STAGES.length - 1) {
        const next = prev + 1
        addLogs(DEMO_STAGES[next].log.split("\n"))
        return next
      }
      return prev
    })
  }, [addLogs])

  const startDemo = useCallback(() => {
    setCurrentStage(0)
    setLogs(DEMO_STAGES[0].log.split("\n"))
    setIsPlaying(true)
    setShowEndCta(false)
  }, [])

  const resetDemo = useCallback(() => {
    setCurrentStage(0)
    setLogs([])
    setIsPlaying(false)
    setShowEndCta(false)
  }, [])

  useEffect(() => {
    if (!isPlaying) return
    if (currentStage >= DEMO_STAGES.length - 1) {
      setIsPlaying(false)
      setShowEndCta(true)
      return
    }
    const timer = setTimeout(() => {
      advanceStage()
    }, 2000)
    return () => clearTimeout(timer)
  }, [isPlaying, currentStage, advanceStage])

  const stage = DEMO_STAGES[currentStage]

  return (
    <div className="min-h-screen bg-intent-bg text-intent-text antialiased">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-intent-bg/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <a href="/" className="flex items-center">
            <InterlockBrand size="md" />
          </a>
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-medium tracking-widest uppercase">
              Simulated Demo
            </span>
          </div>
        </div>
      </header>

      <main className="pt-24 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          {/* Title area */}
          <div className="text-center mb-12">
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight mb-4 text-balance"
            >
              Interactive Product Demo
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="text-lg text-intent-muted max-w-2xl mx-auto mb-6"
            >
              See how Interlock responds when an AI agent performs a dangerous action.
            </motion.p>
            <div className="flex items-center justify-center gap-2 text-sm text-intent-muted">
              <Shield className="w-4 h-4 text-emerald-400" />
              <span>No real production systems are modified during this demonstration.</span>
            </div>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
            {!isPlaying && currentStage === 0 && logs.length === 0 && (
              <motion.button
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                onClick={startDemo}
                className="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold transition-colors"
              >
                <Play className="w-4 h-4" />
                Start Demo
              </motion.button>
            )}
            {isPlaying && (
              <div className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-white/5 border border-white/10 text-intent-muted">
                <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                <span className="text-sm font-medium">Playing automatically...</span>
              </div>
            )}
            {(logs.length > 0 || currentStage > 0) && (
              <motion.button
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                onClick={resetDemo}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-white/10 hover:border-emerald-500/30 text-intent-text font-medium transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Restart Demo
              </motion.button>
            )}
            {!isPlaying && logs.length > 0 && currentStage < DEMO_STAGES.length - 1 && (
              <motion.button
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                onClick={advanceStage}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-white/10 hover:border-emerald-500/30 text-intent-text font-medium transition-colors"
              >
                Next Stage
                <ArrowRight className="w-4 h-4" />
              </motion.button>
            )}
          </div>

          {/* Stage indicators */}
          <div className="flex flex-wrap items-center justify-center gap-2 mb-10">
            {DEMO_STAGES.map((s, i) => (
              <button
                key={s.id}
                onClick={() => {
                  if (i <= currentStage || !isPlaying) {
                    setCurrentStage(i)
                    setLogs(s.log.split("\n"))
                    if (i === DEMO_STAGES.length - 1) {
                      setShowEndCta(true)
                    } else {
                      setShowEndCta(false)
                    }
                  }
                }}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium tracking-wider uppercase transition-colors",
                  i === currentStage
                    ? "bg-emerald-500/20 border border-emerald-500/30 text-emerald-300"
                    : i < currentStage
                    ? "bg-white/5 border border-white/5 text-intent-muted hover:text-emerald-300"
                    : "bg-white/[0.02] border border-white/5 text-intent-muted/50 cursor-not-allowed",
                )}
              >
                {s.title}
              </button>
            ))}
          </div>

          {/* Main demo area */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
            {/* Stage details */}
            <AnimatePresence mode="wait">
              <motion.div
                key={stage.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3 }}
                className="rounded-2xl border border-white/5 bg-white/[0.03] p-6 md:p-8"
              >
                <div className="flex items-center gap-4 mb-6">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/5 bg-white/[0.03] text-emerald-400">
                    <stage.icon className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight">{stage.title}</h2>
                    <p className="text-sm text-intent-muted">{stage.subtitle}</p>
                  </div>
                </div>
                <div className="space-y-3">
                  {stage.fields.map((field) => (
                    <div
                      key={field.label}
                      className="flex items-center justify-between py-2 border-b border-white/5 last:border-0"
                    >
                      <span className="text-sm text-intent-muted">{field.label}</span>
                      <span
                        className={cn(
                          "text-sm font-mono font-medium",
                          field.color || "text-intent-text",
                        )}
                      >
                        {field.value}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            </AnimatePresence>

            {/* Event log / terminal */}
            <div className="rounded-2xl border border-white/5 bg-black/40 p-6 overflow-hidden flex flex-col">
              <div className="flex items-center gap-2 mb-4 text-xs text-intent-muted">
                <span className="flex h-3 w-3 rounded-full bg-emerald-500/60" />
                <span>interlock-event.log</span>
                <span className="ml-auto text-intent-muted/50">
                  {logs.length} events
                </span>
              </div>
              <div className="flex-1 overflow-y-auto font-mono text-xs leading-relaxed space-y-0.5 max-h-[400px]">
                <AnimatePresence>
                  {logs.map((log, i) => (
                    <motion.div
                      key={`${currentStage}-${i}`}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2 }}
                      className={cn(
                        "whitespace-pre",
                        log.includes("EVENT") && "text-emerald-300",
                        log.includes("ATTR") && "text-intent-muted",
                        log.includes("AUDIT") && "text-cyan-300",
                        log.includes("STORE") && "text-intent-muted",
                        log.includes("EVAL") && "text-amber-300",
                        log.includes("POLICY") && "text-intent-muted",
                        log.includes("RESULT") && "text-emerald-300",
                        log.includes("CONTAIN") && "text-red-300",
                        log.includes("STATUS") && "text-intent-muted",
                        log.includes("EVIDENCE") && "text-cyan-300",
                        log.includes("PLAN") && "text-emerald-300",
                        log.includes("ADAPTER") && "text-intent-muted",
                        log.includes("DEPS") && "text-intent-muted",
                        log.includes("STEPS") && "text-intent-muted",
                        log.includes("RECOVER") && "text-emerald-300",
                        log.includes("EXEC") && "text-amber-300",
                        log.includes("DURATION") && "text-intent-muted",
                        log.includes("VERIFY") && "text-cyan-300",
                        log.includes("EXPECTED") && "text-intent-muted",
                        log.includes("ACTUAL") && "text-intent-muted",
                        log.includes("MATCH") && "text-emerald-300",
                        log.includes("NOTE") && "text-amber-300",
                        log.includes("END") && "text-intent-muted",
                      )}
                    >
                      {log}
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          </div>

          {/* End-of-demo CTA */}
          <AnimatePresence>
            {showEndCta && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-8 md:p-12 text-center"
              >
                <h3 className="text-2xl md:text-3xl font-bold tracking-tight mb-4">
                  See Interlock on your own agent stack.
                </h3>
                <p className="text-lg text-intent-muted max-w-2xl mx-auto mb-8">
                  Get a live walkthrough of authorization, containment, surgical recovery, and independent verification.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <a
                    href="https://mail.google.com/mail/?view=cm&fs=1&to=interlock677@gmail.com&su=Interlock%20V4%20Demo%20Request&body=Hi%2C%0A%0AI'd%20like%20to%20schedule%20a%20live%20Interlock%20V4%20demo.%0A%0AName%3A%0ACompany%3A%0ARole%3A%0A%0AI'm%20interested%20in%20learning%20how%20Interlock%20can%20help%20secure%20and%20recover%20AI-agent%20actions.%0A%0ABest%2C%0A%5BName%5D"
                    className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold transition-colors"
                  >
                    Book a Live Demo
                    <ArrowRight className="h-4 w-4" />
                  </a>
                  <a
                    href="https://github.com/interlock219-beep/INTERLOCK-V4"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl border border-white/10 hover:border-emerald-500/30 text-intent-text font-medium transition-colors"
                  >
                    <Github className="h-4 w-4" />
                    View GitHub
                  </a>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <InterlockBrand size="sm" />
          <p className="text-sm text-intent-muted">
            © {new Date().getFullYear()} Interlock. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}

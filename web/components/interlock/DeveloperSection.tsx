"use client"

import { motion } from "framer-motion"
import { Terminal, BookOpen, Github, Rocket } from "lucide-react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

const langChainLines = [
  { text: "from sdk.langchain_adapter import IntentLockLangChainTool", c: "text-emerald-300/80" },
  { text: "from sdk.intentlock import IntentLockGuard", c: "text-emerald-300/80" },
  { text: "", c: "" },
  { text: "client = IntentLockGuard(", c: "" },
  { text: '    base_url="http://localhost:8000/api/v1/intent/verify",', c: "text-emerald-400/90" },
  { text: '    execute_url="http://localhost:8000/api/v1/intent/execute",', c: "text-emerald-400/90" },
  { text: '    auth_token="your-access-token",', c: "text-emerald-400/90" },
  { text: ")", c: "" },
  { text: "", c: "" },
  { text: "tool = IntentLockLangChainTool(", c: "" },
  { text: '    tool=my_tool,', c: "" },
  { text: '    base_url="http://localhost:8000/api/v1/intent/verify",', c: "text-emerald-400/90" },
  { text: '    auth_token="your-access-token",', c: "text-emerald-400/90" },
  { text: ")", c: "" },
  { text: "", c: "" },
  { text: "# Every call is verified before the wrapped tool runs.", c: "text-intent-muted/70" },
]

const resources = [
  { label: "Quickstart", href: "https://github.com/interlock677-debug/intentlock/blob/master/docs/developer/QUICKSTART.md", icon: Rocket },
  { label: "Examples", href: "https://github.com/interlock677-debug/intentlock/blob/master/docs/developer/EXAMPLES.md", icon: Terminal },
  { label: "SDK reference", href: "https://github.com/interlock677-debug/intentlock/blob/master/sdk/README.md", icon: BookOpen },
  { label: "Architecture", href: "https://github.com/interlock677-debug/intentlock/blob/master/docs/architecture/ARCHITECTURE.md", icon: Github },
]

export function DeveloperSection() {
  return (
    <section id="developer" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="For developers"
          title="Drop into existing agent runtimes."
          description="The Python SDK and LangChain wrapper protect tools with no changes to agent code. Integration is a single verify/execute boundary."
          align="center"
        />

        <div className="mx-auto max-w-3xl">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="rounded-2xl border border-white/5 bg-black/40 p-6 overflow-x-auto"
          >
            <div className="flex items-center gap-2 mb-4 text-xs text-intent-muted">
              <span className="flex h-3 w-3 rounded-full bg-emerald-500/60" />
              <span>example.py</span>
            </div>
            <pre className="text-sm leading-[1.6]"><code className="text-intent-text">
              {langChainLines.map((line, i) => (
                <span key={i} className={cn(line.c)}>
                  {line.text || "\u00A0"}
                  {"\n"}
                </span>
              ))}
            </code></pre>
          </motion.div>
        </div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto"
          >
          {resources.map((r, i) => (
            <motion.a
              key={r.label}
              href={r.href}
              target="_blank"
              rel="noopener noreferrer"
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              whileHover={{ x: 4 }}
              className={cn(
                "flex items-center gap-4 rounded-xl border border-white/5 bg-white/[0.03] p-5",
                "text-intent-muted hover:text-emerald-300 hover:border-emerald-500/20 transition-colors",
              )}
            >
              <r.icon className="h-5 w-5" />
              <span className="text-sm font-medium">{r.label}</span>
            </motion.a>
          ))}
        </motion.div>
      </div>
    </section>
  )
}

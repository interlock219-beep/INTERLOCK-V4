"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Settings, Save, Loader2 } from "lucide-react"
import { ApiError, api } from "@/lib/api"
import { useAuth } from "@/components/AuthProvider"

type MessageType = "info" | "error" | "success"

export default function SettingsPage() {
  const [email, setEmail] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState("")
  const [messageType, setMessageType] = useState<MessageType>("info")
  const { user } = useAuth()

  useEffect(() => {
    if (user?.email) setEmail(user.email)
  }, [user])

  const handleSave = async () => {
    setIsSaving(true)
    setMessage("")
    try {
      await api.auth.updateProfile({ email })
      setMessage("Profile updated successfully.")
      setMessageType("success")
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
        setMessage(
          "Profile updates are coming soon. Your changes haven't been saved yet.",
        )
        setMessageType("info")
      } else {
        setMessage(err instanceof Error ? err.message : "Unable to save profile")
        setMessageType("error")
      }
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-intent-muted">Manage your account and workspace preferences.</p>
      </motion.div>

      <div className="glass-panel rounded-xl p-6 space-y-6">
        <div>
          <h2 className="font-semibold mb-4">Profile</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 focus:border-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Role</label>
              <input
                type="text"
                value={user?.role || "viewer"}
                disabled
                className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-intent-muted"
              />
            </div>
          </div>
        </div>

        {message && (
          <div
            className={`p-4 rounded-lg text-sm ${
              messageType === "error"
                ? "bg-red-500/10 border border-red-500/20 text-red-400"
                : messageType === "success"
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                  : "bg-cyan-500/10 border border-cyan-500/20 text-cyan-300"
            }`}
          >
            {message}
          </div>
        )}

        <div className="pt-4 border-t border-white/10">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition-all duration-200 disabled:opacity-50"
          >
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}

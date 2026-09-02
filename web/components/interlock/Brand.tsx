"use client"

import { cn } from "@/lib/utils"

interface InterlockBrandProps {
  size?: "sm" | "md" | "lg"
  className?: string
}

export function InterlockBrand({ size = "md", className }: InterlockBrandProps) {
  const weights = {
    sm: "text-xl font-semibold",
    md: "text-2xl font-bold",
    lg: "text-4xl font-extrabold tracking-tight",
  }

  return (
    <span
      className={cn(
        "text-emerald-50 select-none",
        weights[size],
        className,
      )}
    >
      <span className="text-emerald-300/50">Inter</span>
      <span className="text-emerald-400">lock</span>
    </span>
  )
}

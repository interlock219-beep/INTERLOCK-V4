const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1"

export interface User {
  id: string
  email: string
  is_active: boolean
  role: string
  tenant_id: string | null
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Plan {
  id: string
  name: string
  tier: string
  price_monthly_cents: number
  price_yearly_cents: number
  currency: string
  features: Record<string, unknown>
  limits: Record<string, number>
}

export interface Subscription {
  id: string
  plan_id: string
  plan_name: string
  tier: string
  status: string
  interval: string
  current_period_start: string
  current_period_end: string
  cancel_at_period_end: boolean
}

export interface Usage {
  resource_type: string
  current: number
  limit: number | null
  period_start: string
  period_end: string
  percentage: number | null
}

export interface BillingOverview {
  plan: Plan | null
  subscription: Subscription | null
  usage: Usage[]
}

export interface ActivityEvent {
  event_type: string
  timestamp: string
  details: Record<string, unknown>
}

export interface PortalSession {
  url: string
  expires_at: string
}

export interface RecordUsageResult {
  allowed: boolean
  reason: string
  current?: number
  limit?: number
  resource_type?: string
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

let authToken: string | null = null

export function setAuthToken(token: string | null) {
  authToken = token
}

export function getAuthToken() {
  return authToken
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(response.status, error.detail || error.message || "Request failed")
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const api = {
  auth: {
    register: (data: { email: string; password: string }) =>
      request<AuthResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    login: (data: { email: string; password: string }) =>
      request<AuthResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    me: () => request<User>("/auth/me"),
    updateProfile: (data: { email?: string; password?: string }) =>
      request<User>("/auth/profile", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },
  billing: {
    listPlans: () => request<Plan[]>("/billing/plans"),
    getSubscription: () => request<Subscription | null>("/billing/subscription"),
    getUsage: () => request<Usage[]>("/billing/usage"),
    getOverview: () => request<BillingOverview>("/billing/overview"),
    createCheckout: (data: { plan_id: string; interval?: string; success_url: string; cancel_url: string }) =>
      request<{ session_id: string; url: string }>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    createPortal: () => request<PortalSession>("/billing/portal", { method: "POST" }),
    recordUsage: (data: { resource_type: string; quantity: number }) =>
      request<RecordUsageResult>("/billing/usage", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    cancelSubscription: () =>
      request<{ subscription_id: string; canceled_at: string; access_until: string }>("/billing/cancel", {
        method: "POST",
      }),
    getPublishableKey: () => request<{ publishableKey: string | null }>("/billing/publishable-key"),
  },
  activity: {
    list: () => request<ActivityEvent[]>("/activity/me"),
  },
}

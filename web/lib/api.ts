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

export interface Agent {
  agent_id: string
  tenant_id: string
  name: string
  description: string
  agent_type: string
  status: string
  trust_level: string
  risk_classification: string
  parent_agent_id: string | null
  model_provider: string | null
  model_name: string | null
  environment: string
  version: string
  creator: string | null
  registration_method: string
  root_human_sponsor: string | null
  owner_user_id: string | null
  connected_tools: string[]
  expires_at: string | null
  last_activity_at: string | null
  created_at: string
  updated_at: string
}

export interface AuthorityGrant {
  grant_id: string
  tenant_id: string
  grantor_agent_id: string
  grantee_agent_id: string
  scope: string
  resource: string
  conditions: Record<string, string>
  expires_at: string | null
  delegation_depth: number
  parent_authority_id: string | null
  root_authority_id: string | null
  status: string
  revoked_at: string | null
  created_at: string
  updated_at: string
}

export interface GrantLineage {
  grant_id: string
  root_authority_id: string | null
  ancestors: AuthorityGrant[]
  descendants_count: number
  descendants: AuthorityGrant[]
}

export interface BlastRadius {
  agent_id: string
  status: string
  risk_classification: string
  direct_authorities: number
  child_agents: string[]
  child_agents_count: number
  affected_resources: Record<string, string[]>
  blast_radius_score: number
  active_sessions: unknown[]
  active_sessions_count: number
  active_execution_tokens: unknown[]
  active_execution_tokens_count: number
  pending_approvals: unknown[]
  pending_approvals_count: number
  pending_actions: unknown[]
  pending_actions_count: number
}

export interface ContainmentRequest {
  target_agent_id: string
  mode: string
  target_authority_id?: string
  reason: string
  dry_run: boolean
}

export interface ContainmentResult {
  containment_id: string
  tenant_id: string
  target_agent_id: string
  target_authority_id: string | null
  mode: string
  status: string
  dry_run: boolean
  affected_agent_ids: string[]
  affected_authority_ids: string[]
  affected_session_ids: string[]
  affected_token_ids: string[]
  affected_action_ids: string[]
  result_details: Record<string, string>
  created_at: string
  completed_at: string | null
}

export interface RecoverySimulation {
  plan_id: string
  affected_actions_count: number
  irreversible_actions: string[]
  approval_required_actions: string[]
  recovery_order: string[]
  topological_order: string[]
  estimated_blast_radius: number
  connector_availability: string
  warnings: string[]
  adapter_results: Record<string, unknown>
  surgical_simulation_results: Record<string, unknown>
}

export interface RecoveryPlan {
  plan_id: string
  tenant_id: string
  incident_action_id: string
  status: string
  outcome: string
  simulation_result: Record<string, unknown>
  steps: Record<string, string>[]
  approved_by: string | null
  executed_by: string | null
  created_at: string
  updated_at: string
  executed_at: string | null
}

export interface ActionEntry {
  action_id: string
  tenant_id: string
  agent_id: string
  tool: string
  resource: string
  action_type: string
  status: string
  risk_score: number
  reversibility: string
  authority_grant_id: string | null
  correlation_id: string
  parent_action_id: string | null
  workflow_id: string | null
  decision_reason: string
  created_at: string
  evaluated_at: string | null
  executed_at: string | null
}

export interface ActionGraph {
  action_id: string
  upstream: Record<string, unknown>[]
  downstream: Record<string, unknown>[]
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
  agents: {
    list: () => request<{ items: Agent[] }>("/agents/").then((r) => r.items),
    get: (agentId: string) => request<Agent>(`/agents/${encodeURIComponent(agentId)}`),
    update: (agentId: string, data: { status?: string; trust_level?: string }) =>
      request<Agent>(`/agents/${encodeURIComponent(agentId)}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },
  authority: {
    list: () => request<{ items: AuthorityGrant[] }>("/authority/").then((r) => r.items),
    getLineage: (grantId: string) => request<GrantLineage>(`/authority/${encodeURIComponent(grantId)}/lineage`),
  },
  control: {
    getBlastRadius: (agentId: string) =>
      request<BlastRadius>(
        `/control/containment/agent/${encodeURIComponent(agentId)}`
      ),
    createContainment: (data: ContainmentRequest) =>
      request<ContainmentResult>("/control/containment", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    simulateRecovery: (data: { incident_action_id: string; recovery_steps?: Record<string, string>[] }) =>
      request<RecoverySimulation>("/control/recovery/simulate", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    executeRecovery: (data: { plan_id: string; approved_by: string }) =>
      request<RecoveryPlan>("/control/recovery/execute", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    getRecoveryPlan: (planId: string) => request<RecoveryPlan>(`/control/recovery/${encodeURIComponent(planId)}`),
  },
  actions: {
    list: () => request<{ items: ActionEntry[] }>("/actions/").then((r) => r.items),
    getUpstream: (actionId: string) =>
      request<ActionGraph>(`/actions/${encodeURIComponent(actionId)}/upstream`),
    getDownstream: (actionId: string) =>
      request<ActionGraph>(`/actions/${encodeURIComponent(actionId)}/downstream`),
    getGraph: (actionId: string) =>
      request<ActionGraph>(`/actions/${encodeURIComponent(actionId)}/graph`),
  },
}

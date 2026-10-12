/** 与 docs/API.md 对应的前端类型（字段一一对应后端 schemas） */

export interface User {
  id: number
  username: string
  role: 'admin' | 'teacher' | 'student'
  real_name: string
  class_id: number | null
  status: string
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Task {
  id: number
  title: string
  description: string
  class_id: number
  created_by: number
  mode: 'personal' | 'team'
  status: 'draft' | 'published' | 'closed'
  initial_fund_cents: number
  market_heat: number
  competition_level: number
  strict_mode: boolean
  weight_config: Record<string, unknown>
  agent_assignments: Array<{ agent_id: number; agent_name: string; instructions: string }>
}

export interface Session {
  id: number
  task_id: number
  owner_id: number
  team_id: number | null
  name: string
  status: 'preparing' | 'live' | 'paused' | 'ended' | 'submitted'
  fund_balance_cents: number
  research: Record<string, unknown> | null
  plan: Record<string, unknown> | null
  script: { segments?: ScriptSegment[]; adopted_notes?: unknown[] } | null
  room_config: Record<string, unknown> | null
  metrics: Record<string, number | string | null>
}

export interface ScriptSegment {
  stage: string
  item_id?: number | null
  duration_min: number
  speech: string
  actions: string[]
}

export interface Product {
  id: number
  name: string
  brand: string
  category: string
  cost_cents: number
  market_price_cents: number
  heat: number
  stock: number
  images: string[]
  selling_points: string[]
  description: string
  status: string
}

export interface CartItem {
  id: number
  session_id: number
  product_id: number | null
  name: string
  role: 'traffic' | 'profit' | 'image'
  status: 'editing' | 'listed'
  title: string
  selling_points: string[]
  list_price_cents: number
  live_price_cents: number
  stock: number
  purchased_qty: number
  cost_cents: number
  market_price_cents: number
  sort: number
}

export interface Cart {
  session_id: number
  fund_balance_cents: number
  total_cost_cents: number
  items: CartItem[]
}

export interface PreflightItem {
  key: string
  label: string
  required: boolean
  passed: boolean
  reason: string
  entry: string
}

export interface Preflight {
  session_id: number
  strict_mode: boolean
  passed: boolean
  items: PreflightItem[]
}

export interface Snapshot {
  online: number
  viewers: number
  peak_online: number
  likes: number
  comments: number
  item_clicks: number
  orders: number
  gmv_cents: number
  tick_count: number
  current_item_id: number | null
  updated_at: string | null
}

export interface LiveEvent {
  id: number
  session_id: number
  type: string
  ts: string
  payload: Record<string, any>
  source: string | null
}

export interface LiveState {
  session_id: number
  status: string
  snapshot: Snapshot
  latest_event_id: number
}

export interface LiveTickResult extends LiveState {
  new_events: LiveEvent[]
}

export interface Order {
  id: number
  order_no: string
  product_name: string
  qty: number
  amount_cents: number
  buyer_name: string
  status: 'pending_ship' | 'shipping' | 'signed' | 'closed'
  logistics_node: string | null
  logistics_history: Array<{ node: string; at: string; note: string }>
  created_at: string
}

export interface AfterSale {
  id: number
  order_id: number
  type: string
  reason: string
  amount_cents: number
  status: 'pending' | 'approved' | 'rejected' | 'closed'
  handler_note: string
}

export interface Report {
  id: number
  session_id: number
  content: Record<string, any>
  source: 'llm' | 'rule'
  generated_at: string | null
  improvement_plan: string
  status: 'draft' | 'submitted' | 'returned' | 'scored'
  locked: boolean
  submitted_at: string | null
  returned_reason: string
}

export interface Score {
  session_id: number
  objective_score: number
  objective_detail: Record<string, any>
  subjective_score: number | null
  comprehensive_score: number | null
  comment: string
}

export interface Metrics {
  session_id: number
  view: string
  data: Record<string, any>
  notes: string[]
}

export interface Agent {
  id: number
  name: string
  position_type: string
  duty: string
  instructions: string
  skills: string[]
  tools: string[]
  knowledge_cards: string[]
  completeness: number
  scope: 'builtin' | 'class' | 'personal'
  class_id: number | null
  owner_id: number | null
  status: 'draft' | 'pending' | 'published' | 'rejected'
  review_note: string
}

export interface AgentRun {
  id: number
  agent_id: number
  session_id: number | null
  input: { prompt: string; context: Record<string, unknown> }
  output: { result?: string; evidence?: string[]; caveats?: string[] }
  source: 'llm' | 'rule'
  trace: Array<Record<string, unknown>>
  latency_ms: number
  model: string
  rating_score: number | null
  rating_comment: string
  adopted_target: string | null
}

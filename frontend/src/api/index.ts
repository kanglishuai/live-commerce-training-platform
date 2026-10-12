import client from './client'
import type {
  AfterSale, Agent, AgentRun, Cart, CartItem, LiveEvent, LiveState, LiveTickResult,
  Metrics, Order, Page, Preflight, Product, Report, Score, Session, Snapshot, Task, User
} from './types'

/** 接口封装：路径与 docs/API.md 一一对应 */
export const api = {
  auth: {
    login: (username: string, password: string) =>
      client.post<{ token: string; user: User }>('/auth/login', { username, password }).then((r) => r.data),
    me: () => client.get<User>('/auth/me').then((r) => r.data)
  },
  tasks: {
    list: (params: Record<string, unknown> = {}) =>
      client.get<Page<Task>>('/tasks', { params }).then((r) => r.data),
    get: (id: number) => client.get<Task>(`/tasks/${id}`).then((r) => r.data),
    create: (payload: Record<string, unknown>) => client.post<Task>('/tasks', payload).then((r) => r.data),
    publish: (id: number) => client.post<Task>(`/tasks/${id}/publish`).then((r) => r.data)
  },
  sessions: {
    createForTask: (taskId: number, payload: Record<string, unknown> = {}) =>
      client.post<Session>(`/tasks/${taskId}/sessions`, payload).then((r) => r.data),
    list: (params: Record<string, unknown> = {}) =>
      client.get<Page<Session>>('/sessions', { params }).then((r) => r.data),
    get: (id: number) => client.get<Session>(`/sessions/${id}`).then((r) => r.data),
    saveResearch: (id: number, payload: Record<string, unknown>) =>
      client.put<Session>(`/sessions/${id}/research`, payload).then((r) => r.data),
    savePlan: (id: number, payload: Record<string, unknown>) =>
      client.put<Session>(`/sessions/${id}/plan`, payload).then((r) => r.data),
    getScript: (id: number) =>
      client.get<{ segments?: unknown[]; adopted_notes?: unknown[] }>(`/sessions/${id}/script`).then((r) => r.data),
    saveScript: (id: number, payload: Record<string, unknown>) =>
      client.put(`/sessions/${id}/script`, payload).then((r) => r.data),
    getRoom: (id: number) =>
      client.get<Record<string, any>>(`/sessions/${id}/room`).then((r) => r.data),
    saveRoom: (id: number, payload: Record<string, unknown>) =>
      client.put<Record<string, any>>(`/sessions/${id}/room`, payload).then((r) => r.data),
    preflight: (id: number) => client.get<Preflight>(`/sessions/${id}/preflight`).then((r) => r.data)
  },
  products: {
    list: (params: Record<string, unknown> = {}) =>
      client.get<Page<Product>>('/products', { params }).then((r) => r.data)
  },
  cart: {
    get: (sessionId: number) => client.get<Cart>(`/sessions/${sessionId}/cart`).then((r) => r.data),
    add: (sessionId: number, productId: number, role: string) =>
      client.post<CartItem>(`/sessions/${sessionId}/cart/items`, { product_id: productId, role }).then((r) => r.data),
    patch: (sessionId: number, itemId: number, payload: Record<string, unknown>) =>
      client.patch<CartItem>(`/sessions/${sessionId}/cart/items/${itemId}`, payload).then((r) => r.data),
    remove: (sessionId: number, itemId: number) =>
      client.delete(`/sessions/${sessionId}/cart/items/${itemId}`).then((r) => r.data),
    pricing: (sessionId: number, itemId: number, payload: { list_price_cents: number; live_price_cents: number; stock: number }) =>
      client.put<CartItem>(`/sessions/${sessionId}/cart/items/${itemId}/pricing`, payload).then((r) => r.data),
    purchase: (sessionId: number, payload: { item_id: number; qty: number; supplier?: string; unit_cost_cents?: number }) =>
      client.post(`/sessions/${sessionId}/purchases`, payload).then((r) => r.data),
    fundTxns: (sessionId: number) => client.get(`/sessions/${sessionId}/fund-txns`).then((r) => r.data)
  },
  adPlans: {
    list: (sessionId: number) => client.get(`/sessions/${sessionId}/ad-plans`).then((r) => r.data),
    create: (sessionId: number, payload: Record<string, unknown>) =>
      client.post(`/sessions/${sessionId}/ad-plans`, payload).then((r) => r.data),
    activate: (planId: number) => client.post(`/ad-plans/${planId}/activate`).then((r) => r.data),
    stop: (planId: number) => client.post(`/ad-plans/${planId}/stop`).then((r) => r.data)
  },
  live: {
    start: (sessionId: number) => client.post<LiveState>(`/sessions/${sessionId}/live/start`).then((r) => r.data),
    pause: (sessionId: number) => client.post<LiveState>(`/sessions/${sessionId}/live/pause`).then((r) => r.data),
    resume: (sessionId: number) => client.post<LiveState>(`/sessions/${sessionId}/live/resume`).then((r) => r.data),
    stop: (sessionId: number) => client.post<LiveState>(`/sessions/${sessionId}/live/stop`).then((r) => r.data),
    tick: (sessionId: number) => client.post<LiveTickResult>(`/sessions/${sessionId}/live/tick`).then((r) => r.data),
    state: (sessionId: number) => client.get<LiveState>(`/sessions/${sessionId}/live/state`).then((r) => r.data),
    events: (sessionId: number, sinceId = 0, type?: string) =>
      client
        .get<{ events: LiveEvent[]; latest_event_id: number }>(`/sessions/${sessionId}/live/events`, {
          params: { since_id: sinceId, type }
        })
        .then((r) => r.data),
    speech: (sessionId: number, text: string, source = 'manual') =>
      client.post(`/sessions/${sessionId}/live/speech`, { text, source }).then((r) => r.data),
    behavior: (sessionId: number, faceDetected: boolean, smileCoef: number) =>
      client
        .post<LiveEvent>(`/sessions/${sessionId}/live/behavior`, { face_detected: faceDetected, smile_coef: smileCoef })
        .then((r) => r.data),
    control: (sessionId: number, action: string, payload: Record<string, unknown> = {}) =>
      client.post<LiveEvent>(`/sessions/${sessionId}/live/control`, { action, payload }).then((r) => r.data),
    suggestReply: (sessionId: number, commentEventId: number) =>
      client
        .post<{ text: string; source: string }>(`/sessions/${sessionId}/live/replies/suggest`, {
          comment_event_id: commentEventId
        })
        .then((r) => r.data)
  },
  orders: {
    list: (sessionId: number, params: Record<string, unknown> = {}) =>
      client.get<Page<Order>>(`/sessions/${sessionId}/orders`, { params }).then((r) => r.data),
    ship: (orderId: number) => client.post<Order>(`/orders/${orderId}/ship`, {}).then((r) => r.data),
    advance: (orderId: number, node: string) =>
      client.post<Order>(`/orders/${orderId}/logistics/advance`, { node }).then((r) => r.data)
  },
  afterSales: {
    list: (sessionId: number) => client.get<AfterSale[]>(`/sessions/${sessionId}/after-sales`).then((r) => r.data),
    create: (sessionId: number, payload: { order_id: number; type: string; reason: string }) =>
      client.post<AfterSale>(`/sessions/${sessionId}/after-sales`, payload).then((r) => r.data),
    resolve: (afterSaleId: number, action: 'approve' | 'reject', note = '') =>
      client.post<AfterSale>(`/after-sales/${afterSaleId}/resolve`, { action, note }).then((r) => r.data)
  },
  reviews: {
    metrics: (sessionId: number, view: string) =>
      client.get<Metrics>(`/sessions/${sessionId}/metrics`, { params: { view } }).then((r) => r.data),
    generateReport: (sessionId: number) => client.post<Report>(`/sessions/${sessionId}/report/generate`).then((r) => r.data),
    getReport: (sessionId: number) => client.get<Report>(`/sessions/${sessionId}/report`).then((r) => r.data),
    updateReport: (sessionId: number, improvement: string) =>
      client.put<Report>(`/sessions/${sessionId}/report`, { improvement_plan: improvement }).then((r) => r.data),
    submitReport: (sessionId: number) => client.post<Report>(`/sessions/${sessionId}/report/submit`).then((r) => r.data),
    returnReport: (sessionId: number, reason: string) =>
      client.post<Report>(`/sessions/${sessionId}/report/return`, { reason }).then((r) => r.data),
    score: (sessionId: number, subjective: number, comment: string) =>
      client.post<Score>(`/sessions/${sessionId}/score`, { subjective_score: subjective, comment }).then((r) => r.data),
    getScore: (sessionId: number) => client.get<Score>(`/sessions/${sessionId}/score`).then((r) => r.data)
  },
  classes: {
    list: () => client.get<Array<Record<string, any>>>('/classes').then((r) => r.data),
    report: (classId: number) => client.get(`/classes/${classId}/report`).then((r) => r.data),
    patrol: (classId: number) => client.get(`/classes/${classId}/patrol`).then((r) => r.data)
  },
  agents: {
    list: (params: Record<string, unknown> = {}) =>
      client.get<Page<Agent>>('/agents', { params }).then((r) => r.data),
    create: (payload: Record<string, unknown>) => client.post<Agent>('/agents', payload).then((r) => r.data),
    run: (agentId: number, prompt: string, sessionId?: number | null) =>
      client
        .post<AgentRun>(`/agents/${agentId}/run`, { prompt, context: sessionId ? { session_id: sessionId } : {} })
        .then((r) => r.data),
    rehearse: (agentId: number, prompt: string) =>
      client.post(`/agents/${agentId}/rehearse`, { prompt, context: {} }).then((r) => r.data),
    adopt: (runId: number, target: 'script' | 'report') =>
      client.post(`/agent-runs/${runId}/adopt`, { target }).then((r) => r.data),
    submit: (agentId: number) => client.post<Agent>(`/agents/${agentId}/submit`).then((r) => r.data),
    review: (agentId: number, action: 'approve' | 'reject', note = '') =>
      client.post<Agent>(`/agents/${agentId}/review`, { action, note }).then((r) => r.data)
  },
  files: {
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return client.post<{ file_id: string; url: string }>('/files', form).then((r) => r.data)
    }
  }
}

/** 分 → 元 展示 */
export function yuan(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '-'
  return (cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export type { Snapshot }

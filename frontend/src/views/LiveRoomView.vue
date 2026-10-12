<template>
  <div class="live-room">
    <div class="card">
      <div class="row">
        <h3 style="margin:0">直播工作台 · 场次 #{{ sessionId }}</h3>
        <span class="tag" :class="status === 'live' ? 'live' : status === 'paused' ? 'warn' : 'ended'">{{ statusLabel }}</span>
        <div class="spacer" />
        <button v-if="status === 'preparing'" class="btn" @click="startLive">开始直播</button>
        <template v-else-if="status === 'live'">
          <button class="btn ghost sm" @click="pauseLive">暂停</button>
          <button class="btn danger sm" @click="stopLive">下播</button>
        </template>
        <template v-else-if="status === 'paused'">
          <button class="btn ok sm" @click="resumeLive">恢复直播</button>
          <button class="btn danger sm" @click="stopLive">下播</button>
        </template>
        <button v-else class="btn sm" @click="goReview">去复盘</button>
      </div>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
      <p class="muted" style="margin:8px 0 0">
        仿真节奏：前端每 {{ tickIntervalMs / 1000 }} 秒调用一次 tick 推进（观众/点击/订单/成交为教学模拟数据）。
        <label style="margin-left:8px"><input v-model="autoTick" type="checkbox" /> 自动推进</label>
      </p>
    </div>

    <div class="grid grid-4" style="margin-bottom:16px">
      <div class="metric"><div class="num">{{ snapshot.online }}</div><div class="label">在线人数</div></div>
      <div class="metric"><div class="num">{{ snapshot.viewers }}</div><div class="label">累计观看</div></div>
      <div class="metric"><div class="num">{{ snapshot.item_clicks }}</div><div class="label">商品点击</div></div>
      <div class="metric"><div class="num">{{ snapshot.orders }}</div><div class="label">成交订单</div></div>
      <div class="metric"><div class="num">{{ yuan(snapshot.gmv_cents) }}</div><div class="label">成交金额（元）</div></div>
      <div class="metric"><div class="num">{{ snapshot.likes }}</div><div class="label">点赞</div></div>
      <div class="metric"><div class="num">{{ snapshot.comments }}</div><div class="label">弹幕</div></div>
      <div class="metric"><div class="num">{{ snapshot.tick_count }}</div><div class="label">仿真周期</div></div>
    </div>

    <div class="grid grid-2">
      <div class="card">
        <h3>口播与互动</h3>
        <div class="row">
          <select v-model="speechSource" class="select" style="max-width:160px">
            <option value="manual">手动补录</option>
            <option value="browser_asr">浏览器识别</option>
            <option value="server_asr">服务端识别</option>
          </select>
          <span class="muted">口播按时间顺序保存为场次证据；试音文本不落库</span>
        </div>
        <textarea v-model="speechText" class="textarea" placeholder="输入/修正口播文本（命中敏感词会记录违规）"></textarea>
        <div class="row" style="margin-top:8px">
          <button class="btn sm" :disabled="!speechText.trim()" @click="sendSpeech">提交口播</button>
          <button class="btn ghost sm" :disabled="status !== 'live'" @click="sendBehavior">提交一次出镜采样</button>
          <span class="muted">出镜采样为骨架占位：未接入人脸模型，仅验证接口链路</span>
        </div>

        <h3 style="margin-top:18px">直播中控</h3>
        <div class="row">
          <select v-model.number="switchItemId" class="select" style="max-width:220px">
            <option :value="0">— 切换讲解商品 —</option>
            <option v-for="item in listedItems" :key="item.id" :value="item.id">{{ item.name }}（{{ yuan(item.live_price_cents) }} 元）</option>
          </select>
          <button class="btn sm" :disabled="!switchItemId" @click="switchItem">切换</button>
          <input v-model="announceText" class="input" style="max-width:220px" placeholder="公告内容" />
          <button class="btn ghost sm" :disabled="!announceText.trim()" @click="sendAnnouncement">发公告</button>
        </div>
        <div class="feed" style="margin-top:14px">
          <div v-for="ev in events" :key="ev.id" class="feed-item">
            <div>{{ renderEvent(ev) }}</div>
            <div class="meta">#{{ ev.id }} · {{ ev.type }} · 来源 {{ ev.source || '-' }} · {{ ev.ts }}</div>
            <div class="row" v-if="ev.type === 'comment'" style="margin-top:6px">
              <button class="btn sm ghost" @click="suggest(ev)">AI 回复建议</button>
              <button class="btn sm" @click="replyTo(ev)">回复该评论</button>
            </div>
          </div>
          <div v-if="!events.length" class="muted">暂无事件：开播后点击「推进仿真」或勾选自动推进</div>
        </div>
      </div>

      <div class="card">
        <h3>本场信息</h3>
        <table class="table">
          <tbody>
            <tr><th>资金余额</th><td>{{ yuan(session?.fund_balance_cents) }} 元</td></tr>
            <tr><th>投流花费</th><td>{{ yuan(Number(session?.metrics?.ad_spend_cents || 0)) }} 元</td></tr>
            <tr><th>当前讲解</th><td>{{ currentItemName || '—' }}</td></tr>
            <tr><th>开播时间</th><td>{{ session?.metrics?.updated_at || '—' }}</td></tr>
          </tbody>
        </table>
        <h3 style="margin-top:18px">订单动态</h3>
        <div class="feed">
          <div v-for="ev in events.filter((e) => e.type === 'order')" :key="`o-${ev.id}`" class="feed-item">
            {{ ev.payload?.product_name }} × {{ ev.payload?.qty }} · {{ yuan(ev.payload?.amount_cents) }} 元
          </div>
          <div v-if="!events.some((e) => e.type === 'order')" class="muted">暂无成交</div>
        </div>
        <button class="btn ghost sm" style="margin-top:12px" @click="manualTick">手动推进一次仿真</button>
      </div>
    </div>

    <PromptDialog
      :show="promptState.show"
      :title="promptState.title"
      :default-value="promptState.value"
      :with-input="promptState.withInput"
      @confirm="onPromptConfirm"
      @cancel="promptState.show = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, yuan } from '../api'
import type { CartItem, LiveEvent, Session, Snapshot } from '../api/types'
import PromptDialog from '../components/PromptDialog.vue'

const route = useRoute()
const router = useRouter()
const sessionId = Number(route.params.sessionId)

const session = ref<Session | null>(null)
const status = ref('preparing')
const snapshot = ref<Snapshot>({
  online: 0, viewers: 0, peak_online: 0, likes: 0, comments: 0, item_clicks: 0,
  orders: 0, gmv_cents: 0, tick_count: 0, current_item_id: null, updated_at: null
})
const events = ref<LiveEvent[]>([])
const listedItems = ref<CartItem[]>([])
const error = ref('')
const speechText = ref('')
const speechSource = ref('manual')
const switchItemId = ref(0)
const announceText = ref('')
const autoTick = ref(false)
const tickIntervalMs = 2500

let timer: number | null = null
let lastEventId = 0

const statusLabel = computed(() => {
  const map: Record<string, string> = { preparing: '准备中', live: '直播中', paused: '已暂停', ended: '已下播', submitted: '已提交' }
  return map[status.value] || status.value
})
const currentItemName = computed(() => {
  const id = Number(snapshot.value.current_item_id || 0)
  return listedItems.value.find((i) => i.id === id)?.name || ''
})

function goReview() {
  router.push({ name: 'review', params: { sessionId } })
}

function renderEvent(ev: LiveEvent): string {
  const p = ev.payload || {}
  switch (ev.type) {
    case 'comment': return `💬 [${p.persona || '观众'}] ${p.text}`
    case 'reply': return `📣 主播回复：${p.text}`
    case 'speech': return `🎙️ 口播：${p.text}`
    case 'order': return `🧾 成交：${p.product_name} × ${p.qty} = ${yuan(p.amount_cents)} 元`
    case 'violation': return `⚠️ 违规：命中 ${(p.words || []).join('、')}`
    case 'control': return `🎛️ 中控：${p.action} ${p.detail?.item_name || p.detail?.text || ''}`
    case 'ai_decision': return `🤖 AI 观众决策（${ev.source}）：生成 ${(p.result || []).length} 条弹幕，${p.created_orders || 0} 单成交`
    case 'behavior': return `📷 出镜采样：入镜 ${p.face_detected ? '是' : '否'}，微笑系数 ${p.smile_coef}`
    case 'metric': return `📈 指标：在线 ${p.online}，本周期成交 ${p.orders_this_tick} 单`
    case 'system': return `ℹ️ ${p.text}`
    default: return JSON.stringify(p)
  }
}

async function loadState() {
  const state = await api.live.state(sessionId)
  status.value = state.status
  snapshot.value = state.snapshot
  session.value = await api.sessions.get(sessionId)
  const cart = await api.cart.get(sessionId)
  listedItems.value = cart.items.filter((i) => i.status === 'listed')
  if (!lastEventId) lastEventId = Math.max(0, state.latest_event_id - 30)
  await pullEvents()
}

async function pullEvents() {
  const data = await api.live.events(sessionId, lastEventId)
  if (data.events.length) {
    events.value = [...data.events, ...events.value].slice(0, 120)
    lastEventId = data.events[data.events.length - 1].id
  }
}

async function manualTick() {
  error.value = ''
  try {
    const result = await api.live.tick(sessionId)
    status.value = result.status
    snapshot.value = result.snapshot
    if (result.new_events.length) await pullEvents()
  } catch (e) {
    error.value = (e as Error).message
  }
}

let ticking = false

/** 串行推进：上一次 tick 未返回前不发起下一次（接入大模型后单次 tick 可能变慢） */
async function tickOnce() {
  if (ticking) return
  ticking = true
  try {
    const result = await api.live.tick(sessionId)
    status.value = result.status
    snapshot.value = result.snapshot
    if (result.new_events.length) await pullEvents()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    ticking = false
  }
}

function startTimer() {
  stopTimer()
  timer = window.setInterval(() => {
    if (status.value !== 'live' || !autoTick.value) return
    void tickOnce()
  }, tickIntervalMs)
}

function stopTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

async function startLive() {
  error.value = ''
  try {
    const state = await api.live.start(sessionId)
    status.value = state.status
    autoTick.value = true
    await pullEvents()
  } catch (e) { error.value = (e as Error).message }
}

async function pauseLive() {
  const state = await api.live.pause(sessionId)
  status.value = state.status
}

async function resumeLive() {
  const state = await api.live.resume(sessionId)
  status.value = state.status
}

async function stopLive() {
  openConfirm('确认下播？下播后将进入订单履约与数据复盘，不能再开播。', async () => {
    const state = await api.live.stop(sessionId)
    status.value = state.status
    autoTick.value = false
    await pullEvents()
  })
}

async function sendSpeech() {
  error.value = ''
  try {
    const resp = await api.live.speech(sessionId, speechText.value.trim(), speechSource.value)
    speechText.value = ''
    if (resp.violation) error.value = '口播已保存，但命中敏感词并记录违规'
    await pullEvents()
  } catch (e) { error.value = (e as Error).message }
}

async function sendBehavior() {
  error.value = ''
  try {
    await api.live.behavior(sessionId, true, 0.5)
    await pullEvents()
  } catch (e) { error.value = (e as Error).message }
}

async function switchItem() {
  error.value = ''
  try {
    await api.live.control(sessionId, 'switch_item', { item_id: switchItemId.value })
    await loadState()
  } catch (e) { error.value = (e as Error).message }
}

async function sendAnnouncement() {
  error.value = ''
  try {
    await api.live.control(sessionId, 'announcement', { text: announceText.value.trim() })
    announceText.value = ''
    await pullEvents()
  } catch (e) { error.value = (e as Error).message }
}

async function suggest(ev: LiveEvent) {
  error.value = ''
  try {
    const data = await api.live.suggestReply(sessionId, ev.id)
    openPrompt(`回复建议（来源：${data.source}，可直接发送或修改后发送）`, data.text, async (text) => {
      await api.live.reply(sessionId, ev.id, text)
      await pullEvents()
    })
  } catch (e) { error.value = (e as Error).message }
}

function replyTo(ev: LiveEvent) {
  openPrompt('输入回复内容（客服/主播回复将记入场次证据）', '亲，感谢关注～', async (text) => {
    await api.live.reply(sessionId, ev.id, text)
    await pullEvents()
  })
}

// 内置浏览器/嵌入式 WebView 不支持 window.prompt（直接抛错），统一走应用内对话框
const promptState = ref<{ show: boolean; title: string; value: string; withInput: boolean; onOk: (text: string) => Promise<void> }>({
  show: false, title: '', value: '', withInput: true, onOk: async () => {}
})
function openPrompt(title: string, value: string, onOk: (text: string) => Promise<void>) {
  promptState.value = { show: true, title, value, withInput: true, onOk }
}
// 原生 confirm 在部分嵌入式环境会阻塞页面脚本，同样走应用内确认
function openConfirm(title: string, onOk: () => Promise<void>) {
  promptState.value = { show: true, title, value: '', withInput: false, onOk: async () => { await onOk() } }
}
async function onPromptConfirm(text: string) {
  const run = promptState.value.onOk
  promptState.value.show = false
  try { await run(text) } catch (e) { error.value = (e as Error).message }
}

onMounted(async () => {
  try {
    await loadState()
    startTimer()
  } catch (e) {
    error.value = (e as Error).message
  }
})

onBeforeUnmount(stopTimer)
</script>

<style scoped>
.live-room { min-width: 0; }
</style>

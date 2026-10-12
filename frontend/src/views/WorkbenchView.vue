<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">经营准备 · {{ session?.name || `场次 #${sessionId}` }}</h3>
        <span class="tag" :class="statusClass">{{ statusLabel }}</span>
        <div class="spacer" />
        <span class="muted">资金余额：<b>{{ yuan(session?.fund_balance_cents) }} 元</b></span>
        <button class="btn ghost sm" @click="loadAll">刷新</button>
      </div>
      <p v-if="readOnly" class="muted" style="margin:10px 0 0">
        教师只读视角：以下是该学生场次的经营数据快照（调研/货盘/定价/装修），写入操作请用学生账号。
      </p>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
      <p v-if="notice" class="ok-text" style="margin:10px 0 0">{{ notice }}</p>
    </div>

    <div class="tabs">
      <button v-for="t in tabs" :key="t.key" class="tab" :class="{ active: tab === t.key }" @click="tab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- 调研 -->
    <div v-show="tab === 'research'" class="card">
      <h3>市场调研纪要 <span class="muted">（目标人群与选品理由为必填）</span></h3>
      <div class="grid grid-2">
        <div><label class="muted">目标人群 *</label><input v-model="research.target_audience" class="input" /></div>
        <div><label class="muted">价格带</label><input v-model="research.price_band" class="input" /></div>
        <div><label class="muted">竞品情况</label><input v-model="research.competitors" class="input" /></div>
        <div><label class="muted">推荐开播时段</label><input v-model="research.recommended_slot" class="input" /></div>
      </div>
      <label class="muted" style="display:block;margin-top:10px">选品理由 / 调研结论 *</label>
      <textarea v-model="research.reasons" class="textarea"></textarea>
      <label class="muted" style="display:block;margin-top:10px">核心卖点（逗号分隔）</label>
      <input v-model="researchPoints" class="input" />
      <button class="btn" style="margin-top:12px" :disabled="readOnly" @click="saveResearch">保存调研纪要</button>
    </div>

    <!-- 货盘 / 采购 / 定价 -->
    <div v-show="tab === 'cart'" class="card">
      <h3>货盘与采购</h3>
      <div class="row" style="margin-bottom:12px">
        <select v-model.number="addProductId" class="select" style="max-width:320px" :disabled="readOnly">
          <option :value="0">— 选择商品库商品 —</option>
          <option v-for="p in products" :key="p.id" :value="p.id">
            {{ p.name }}（成本 {{ yuan(p.cost_cents) }} 元 / 市场价 {{ yuan(p.market_price_cents) }} 元）
          </option>
        </select>
        <select v-model="addRole" class="select" style="max-width:140px" :disabled="readOnly">
          <option value="traffic">引流款</option>
          <option value="profit">利润款</option>
          <option value="image">形象款</option>
        </select>
        <button class="btn sm" :disabled="readOnly" @click="addItem">加入货盘</button>
      </div>
      <p class="muted" style="margin:0 0 10px">
        货盘结构：引流款 {{ cartSummary.roleCount.traffic }} / 利润款 {{ cartSummary.roleCount.profit }} / 形象款 {{ cartSummary.roleCount.image }}
        ｜ <b>预计毛利（按当前库存）：{{ yuan(cartSummary.marginCents) }} 元</b>
      </p>

      <table class="table">
        <thead>
          <tr><th>商品</th><th>定位</th><th>成本</th><th>划线价/直播价（元）</th><th>毛利/件</th><th>库存</th><th>采购</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="item in cart.items" :key="item.id">
            <td>{{ item.name }}<div class="muted">#{{ item.id }} · 已采购 {{ item.purchased_qty }}</div></td>
            <td>
              <select :value="item.role" class="select" style="width:110px" @change="changeRole(item, $event)">
                <option value="traffic">引流款</option>
                <option value="profit">利润款</option>
                <option value="image">形象款</option>
              </select>
            </td>
            <td>{{ yuan(item.cost_cents) }}</td>
            <td>
              <div class="row">
                <input :value="(pricing[item.id]?.list ?? item.list_price_cents / 100)" type="number" class="input" style="width:100px"
                       @input="setPricing(item.id, 'list', $event)" />
                <input :value="(pricing[item.id]?.live ?? item.live_price_cents / 100)" type="number" class="input" style="width:100px"
                       @input="setPricing(item.id, 'live', $event)" />
                <button class="btn sm ghost" @click="savePricing(item)">保存定价</button>
              </div>
            </td>
            <td>
              <span :class="unitMargin(item) > 0 ? 'ok-text' : 'error'">{{ yuan(unitMargin(item)) }} 元</span>
            </td>
            <td>
              <input :value="(pricing[item.id]?.stock ?? item.stock)" type="number" class="input" style="width:80px"
                     :disabled="readOnly" @input="setPricing(item.id, 'stock', $event)" />
            </td>
            <td>
              <div class="row">
                <input :value="purchaseQty[item.id] ?? 50" type="number" class="input" style="width:80px"
                       :disabled="readOnly" @input="setPurchaseQty(item.id, $event)" />
                <button class="btn sm" :disabled="readOnly" @click="purchase(item)">采购</button>
              </div>
            </td>
            <td><span class="tag" :class="item.status === 'listed' ? 'ended' : 'warn'">{{ item.status === 'listed' ? '已上架' : '编辑中' }}</span></td>
            <td><button class="btn sm danger" :disabled="readOnly" @click="removeItem(item)">移出</button></td>
          </tr>
          <tr v-if="!cart.items.length"><td colspan="9" class="muted">货盘为空：至少加入 1 款商品并完成采购与定价</td></tr>
        </tbody>
      </table>
      <p class="muted" style="margin-top:10px">提示：采购会扣减经营资金并增加本场库存；定价后库存 &gt; 0 自动上架。</p>
    </div>

    <!-- 脚本 -->
    <div v-show="tab === 'script'" class="card">
      <h3>直播脚本 <span class="muted">（环节：开场/暖场/讲解/互动/逼单/转场/收尾）</span></h3>
      <div v-for="(seg, idx) in segments" :key="idx" class="seg">
        <div class="row">
          <select v-model="seg.stage" class="select" style="width:130px">
            <option value="opening">开场</option>
            <option value="warmup">暖场</option>
            <option value="explain">讲解</option>
            <option value="interact">互动</option>
            <option value="push">逼单</option>
            <option value="transition">转场</option>
            <option value="closing">收尾</option>
          </select>
          <select v-model.number="seg.item_id" class="select" style="width:200px">
            <option :value="null">不绑定商品</option>
            <option v-for="item in cart.items" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <input v-model.number="seg.duration_min" type="number" class="input" style="width:90px" placeholder="分钟" />
          <button class="btn sm danger" @click="segments.splice(idx, 1)">删除</button>
        </div>
        <textarea v-model="seg.speech" class="textarea" style="margin-top:8px" placeholder="口播话术"></textarea>
      </div>
      <div class="row" style="margin-top:12px">
        <button class="btn ghost sm" :disabled="readOnly" @click="addSegment">添加段落</button>
        <button class="btn sm" :disabled="readOnly" @click="saveScript">保存脚本</button>
      </div>
      <div v-if="adoptedNotes.length" class="muted" style="margin-top:12px">
        已采纳智能体结果 {{ adoptedNotes.length }} 条（来自智能体中心「采纳」写入）
      </div>
    </div>

    <!-- 推广 -->
    <div v-show="tab === 'ad'" class="card">
      <h3>流量推广</h3>
      <div class="grid grid-4">
        <div>
          <label class="muted">渠道</label>
          <select v-model="adForm.channel" class="select">
            <option value="short_video">短视频预热</option>
            <option value="feed">信息流投放</option>
            <option value="reservation">直播预约</option>
            <option value="social">社交渠道</option>
          </select>
        </div>
        <div>
          <label class="muted">优化目标</label>
          <select v-model="adForm.objective" class="select">
            <option value="exposure">曝光</option>
            <option value="click">点击</option>
            <option value="enter_room">进房</option>
            <option value="order">成交</option>
          </select>
        </div>
        <div><label class="muted">预算（元）</label><input v-model.number="adForm.budgetYuan" type="number" class="input" /></div>
        <div><label class="muted">出价（分）</label><input v-model.number="adForm.bid_cents" type="number" class="input" /></div>
      </div>
      <button class="btn" style="margin-top:12px" :disabled="readOnly" @click="createAdPlan">创建投流计划</button>
      <table class="table" style="margin-top:12px">
        <thead><tr><th>#</th><th>渠道</th><th>目标</th><th>预算</th><th>已消耗</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in adPlans" :key="p.id">
            <td>{{ p.id }}</td>
            <td>{{ p.channel }}</td>
            <td>{{ p.objective }}</td>
            <td>{{ yuan(p.budget_cents) }} 元</td>
            <td>{{ yuan(p.spent_cents) }} 元</td>
            <td><span class="tag" :class="p.status === 'active' ? 'ended' : 'warn'">{{ p.status === 'active' ? '投放中' : p.status === 'stopped' ? '已停止' : '草稿' }}</span></td>
            <td class="row">
              <button v-if="p.status !== 'active'" class="btn sm" :disabled="readOnly" @click="activateAd(p)">启用</button>
              <button v-else class="btn sm ghost" :disabled="readOnly" @click="stopAd(p)">停止</button>
            </td>
          </tr>
          <tr v-if="!adPlans.length"><td colspan="7" class="muted">暂无投流计划（建议项：影响直播间进房量）</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 装修 -->
    <div v-show="tab === 'room'" class="card">
      <h3>直播间装修</h3>
      <div class="grid grid-2">
        <div><label class="muted">直播间标题 *</label><input v-model="room.title" class="input" /></div>
        <div><label class="muted">副标题</label><input v-model="room.subtitle" class="input" /></div>
        <div><label class="muted">底部公告</label><input v-model="room.notice" class="input" /></div>
        <div><label class="muted">欢迎语</label><input v-model="room.welcome" class="input" /></div>
        <div><label class="muted">背景</label><input v-model="room.background" class="input" placeholder="自然助农 / 时尚精品店 …" /></div>
        <div><label class="muted">画布比例</label>
          <select v-model="roomRatio" class="select"><option value="9:16">9:16 竖屏</option><option value="16:9">16:9 横屏</option></select>
        </div>
      </div>
      <label class="muted" style="display:block;margin-top:10px">敏感词（逗号分隔，口播命中会记录违规）</label>
      <input v-model="roomSensitive" class="input" placeholder="最低价,国家级,绝对" />
      <label class="muted" style="display:block;margin-top:10px">快捷短语 / FAQ 可在后续迭代补充</label>
      <input v-model="roomQuick" class="input" placeholder="还有库存吗,什么时候发货" />
      <button class="btn" style="margin-top:12px" :disabled="readOnly" @click="saveRoom">保存装修</button>
      <p class="muted" style="margin-top:8px">骨架版画布为简化实现：保存标题与公告即可满足开播检查；专业直播伴侣画布（元素拖拽/实时预览）为后续迭代项。</p>
    </div>

    <!-- 开播检查 -->
    <div v-show="tab === 'check'" class="card">
      <h3>开播检查 <span class="muted">{{ preflight?.strict_mode ? '（严格模式：未通过不允许开播）' : '（普通练习：未通过仅提示）' }}</span></h3>
      <table class="table">
        <thead><tr><th>检查项</th><th>类型</th><th>结果</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="item in preflight?.items || []" :key="item.key">
            <td>{{ item.label }}</td>
            <td><span class="tag" :class="item.required ? 'warn' : ''">{{ item.required ? '必须' : '建议' }}</span></td>
            <td><span class="tag" :class="item.passed ? 'ended' : 'live'">{{ item.passed ? '通过' : '未完成' }}</span></td>
            <td class="muted">{{ item.reason || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="row" style="margin-top:14px">
        <b>{{ preflight?.passed ? '✅ 检查通过，可以开播' : '⚠️ 仍有必须项未完成' }}</b>
        <div class="spacer" />
        <button class="btn" :disabled="readOnly || session?.status !== 'preparing'" @click="startLive">开始直播</button>
      </div>
      <p v-if="session && session.status !== 'preparing'" class="muted">场次状态为 {{ statusLabel }}，不能重复开播。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, yuan } from '../api'
import type { Cart, CartItem, Preflight, Product, ScriptSegment, Session } from '../api/types'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const sessionId = Number(route.params.sessionId)

/** 教师/管理员进入本页为只读浏览（巡课用途），写入需学生账号操作 */
const readOnly = computed(() => auth.isTeacher)

const session = ref<Session | null>(null)
const cart = ref<Cart>({ session_id: sessionId, fund_balance_cents: 0, total_cost_cents: 0, items: [] })
const products = ref<Product[]>([])
const adPlans = ref<Array<Record<string, any>>>([])
const preflight = ref<Preflight | null>(null)
const segments = ref<ScriptSegment[]>([])
const adoptedNotes = ref<unknown[]>([])
const error = ref('')
const notice = ref('')

const tab = ref('research')
const tabs = [
  { key: 'research', label: '市场调研' },
  { key: 'cart', label: '货盘/采购/定价' },
  { key: 'script', label: '直播脚本' },
  { key: 'ad', label: '流量推广' },
  { key: 'room', label: '直播间装修' },
  { key: 'check', label: '开播检查' }
]

const research = reactive({ target_audience: '', reasons: '', competitors: '', price_band: '', recommended_slot: '' })
const researchPoints = ref('')
const addProductId = ref(0)
const addRole = ref('traffic')
const pricing = reactive<Record<number, { list?: number; live?: number; stock?: number }>>({})
const purchaseQty = reactive<Record<number, number>>({})
const adForm = reactive({ channel: 'short_video', objective: 'enter_room', budgetYuan: 300, bid_cents: 150 })
const room = reactive<Record<string, any>>({ title: '', subtitle: '', notice: '', welcome: '', background: '', canvas: { ratio: '9:16', elements: [] } })
const roomSensitive = ref('')
const roomQuick = ref('')

const statusLabel = computed(() => {
  const map: Record<string, string> = { preparing: '准备中', live: '直播中', paused: '已暂停', ended: '已下播', submitted: '已提交' }
  return map[session.value?.status || ''] || ''
})
const statusClass = computed(() => (session.value?.status === 'preparing' ? 'preparing' : session.value?.status === 'live' ? 'live' : 'ended'))
const roomRatio = computed({
  get: () => (room.canvas?.ratio as string) || '9:16',
  set: (v: string) => { room.canvas = { ...(room.canvas || {}), ratio: v } }
})

/** 单件毛利 = 直播价 - 成本；预计毛利合计按当前库存估算（19.1 选品决策的查看要点） */
function unitMargin(item: CartItem): number {
  return item.live_price_cents - item.cost_cents
}

const cartSummary = computed(() => {
  const roleCount: Record<string, number> = { traffic: 0, profit: 0, image: 0 }
  let marginCents = 0
  for (const item of cart.value.items) {
    roleCount[item.role] = (roleCount[item.role] || 0) + 1
    marginCents += (item.live_price_cents - item.cost_cents) * item.stock
  }
  return { roleCount, marginCents }
})

async function loadAll() {
  error.value = ''
  try {
    session.value = await api.sessions.get(sessionId)
    cart.value = await api.cart.get(sessionId)
    products.value = (await api.products.list({ page_size: 50 })).items
    adPlans.value = (await api.adPlans.list(sessionId)) as Array<Record<string, any>>
    preflight.value = await api.sessions.preflight(sessionId)
    const script = await api.sessions.getScript(sessionId)
    segments.value = (script.segments as ScriptSegment[]) || []
    adoptedNotes.value = script.adopted_notes || []

    const r = (session.value.research || {}) as Record<string, any>
    research.target_audience = r.target_audience || ''
    research.reasons = r.reasons || ''
    research.competitors = r.competitors || ''
    research.price_band = r.price_band || ''
    research.recommended_slot = r.recommended_slot || ''
    researchPoints.value = ((r.selling_points as string[]) || []).join(',')

    const roomCfg = await api.sessions.getRoom(sessionId)
    Object.assign(room, { canvas: { ratio: '9:16', elements: [] } }, roomCfg || {})
    roomSensitive.value = ((roomCfg?.sensitive_words as string[]) || []).join(',')
    roomQuick.value = ((roomCfg?.quick_phrases as string[]) || []).join(',')
    for (const item of cart.value.items) {
      pricing[item.id] = { list: item.list_price_cents / 100, live: item.live_price_cents / 100, stock: item.stock }
      purchaseQty[item.id] = purchaseQty[item.id] ?? 50
    }
  } catch (e) {
    error.value = (e as Error).message
  }
}

function setPricing(itemId: number, key: 'list' | 'live' | 'stock', event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  pricing[itemId] = { ...(pricing[itemId] || {}), [key]: value }
}

function setPurchaseQty(itemId: number, event: Event) {
  purchaseQty[itemId] = Number((event.target as HTMLInputElement).value)
}

async function saveResearch() {
  error.value = ''; notice.value = ''
  try {
    await api.sessions.saveResearch(sessionId, {
      ...research,
      selling_points: researchPoints.value.split(',').map((s) => s.trim()).filter(Boolean)
    })
    notice.value = '调研纪要已保存'
  } catch (e) { error.value = (e as Error).message }
}

async function addItem() {
  if (!addProductId.value) return
  error.value = ''
  try {
    await api.cart.add(sessionId, addProductId.value, addRole.value)
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function changeRole(item: CartItem, event: Event) {
  const role = (event.target as HTMLSelectElement).value
  await api.cart.patch(sessionId, item.id, { role })
  await loadAll()
}

async function savePricing(item: CartItem) {
  const p = pricing[item.id] || {}
  error.value = ''; notice.value = ''
  try {
    await api.cart.pricing(sessionId, item.id, {
      list_price_cents: Math.round((p.list ?? 0) * 100),
      live_price_cents: Math.round((p.live ?? 0) * 100),
      stock: Number(p.stock ?? 0)
    })
    notice.value = `「${item.name}」定价已保存`
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function purchase(item: CartItem) {
  error.value = ''; notice.value = ''
  try {
    await api.cart.purchase(sessionId, { item_id: item.id, qty: purchaseQty[item.id] || 1, supplier: '产地直供' })
    notice.value = `「${item.name}」采购完成`
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function removeItem(item: CartItem) {
  error.value = ''
  try {
    await api.cart.remove(sessionId, item.id)
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

function addSegment() {
  segments.value.push({ stage: 'explain', item_id: null, duration_min: 3, speech: '', actions: [] })
}

async function saveScript() {
  error.value = ''; notice.value = ''
  try {
    await api.sessions.saveScript(sessionId, { segments: segments.value })
    notice.value = '脚本已保存'
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function createAdPlan() {
  error.value = ''; notice.value = ''
  try {
    await api.adPlans.create(sessionId, {
      channel: adForm.channel,
      objective: adForm.objective,
      budget_cents: Math.round(adForm.budgetYuan * 100),
      bid_cents: adForm.bid_cents,
      audience: {},
      creative: ''
    })
    notice.value = '投流计划已创建，请点击启用'
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function activateAd(plan: Record<string, any>) {
  await api.adPlans.activate(plan.id)
  await loadAll()
}

async function stopAd(plan: Record<string, any>) {
  await api.adPlans.stop(plan.id)
  await loadAll()
}

async function saveRoom() {
  error.value = ''; notice.value = ''
  try {
    const canvas = { ...(room.canvas || { ratio: '9:16', elements: [] }) }
    if (!(canvas.elements || []).length) canvas.elements = [{ type: 'title', x: 40, y: 60 }]
    await api.sessions.saveRoom(sessionId, {
      title: room.title, subtitle: room.subtitle, notice: room.notice, welcome: room.welcome,
      background: room.background, canvas,
      sensitive_words: roomSensitive.value.split(',').map((s) => s.trim()).filter(Boolean),
      quick_phrases: roomQuick.value.split(',').map((s) => s.trim()).filter(Boolean)
    })
    notice.value = '装修配置已保存'
    await loadAll()
  } catch (e) { error.value = (e as Error).message }
}

async function startLive() {
  error.value = ''
  try {
    await api.live.start(sessionId)
    router.push({ name: 'live', params: { sessionId } })
  } catch (e) { error.value = (e as Error).message }
}

onMounted(loadAll)
</script>

<style scoped>
.seg { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 10px; }
</style>

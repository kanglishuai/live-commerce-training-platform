<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">订单履约与售后 · 场次 #{{ sessionId }}</h3>
        <span class="tag" :class="statusClass">{{ statusLabel }}</span>
        <div class="spacer" />
        <select v-model="statusFilter" class="select" style="max-width:150px" @change="loadOrders">
          <option value="">全部状态</option>
          <option value="pending_ship">待发货</option>
          <option value="shipping">运输中</option>
          <option value="signed">已签收</option>
          <option value="closed">已关闭</option>
        </select>
        <button class="btn ghost sm" @click="loadOrders">刷新</button>
        <router-link class="btn sm" :to="{ name: 'review', params: { sessionId } }">去复盘</router-link>
      </div>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
      <p class="muted" style="margin:8px 0 0">未完成履约与售后的场次不能提交复盘（系统会拦截）。</p>
    </div>

    <PromptDialog
      :show="promptState.show"
      :title="promptState.title"
      :default-value="promptState.value"
      @confirm="onPromptConfirm"
      @cancel="promptState.show = false"
    />

    <div class="card">
      <h3>订单（{{ orders.length }}）</h3>
      <table class="table">
        <thead>
          <tr><th>订单号</th><th>商品</th><th>金额</th><th>买家</th><th>状态</th><th>物流</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td>{{ o.order_no }}<div class="muted">{{ o.created_at }}</div></td>
            <td>{{ o.product_name }} × {{ o.qty }}</td>
            <td>{{ yuan(o.amount_cents) }} 元</td>
            <td>{{ o.buyer_name }}</td>
            <td><span class="tag" :class="orderTag(o.status)">{{ orderLabel(o.status) }}</span></td>
            <td class="muted">{{ o.logistics_node ? nodeLabel(o.logistics_node) : '未发货' }}</td>
            <td class="row">
              <button v-if="o.status === 'pending_ship'" class="btn sm" @click="ship(o)">发货</button>
              <template v-if="o.status === 'shipping'">
                <button v-if="o.logistics_node === 'picked_up'" class="btn sm ghost" @click="advance(o, 'in_transit')">运输中</button>
                <button v-if="o.logistics_node === 'in_transit'" class="btn sm ghost" @click="advance(o, 'delivering')">派送中</button>
                <button v-if="o.logistics_node === 'delivering'" class="btn sm ok" @click="advance(o, 'signed')">签收</button>
                <button v-if="o.logistics_node !== 'signed'" class="btn sm danger" @click="advance(o, 'rejected')">拒收</button>
              </template>
              <button v-if="o.status !== 'closed'" class="btn sm ghost" @click="openAfterSale(o)">发起售后</button>
            </td>
          </tr>
          <tr v-if="!orders.length"><td colspan="7" class="muted">暂无订单（开播后仿真成交会自动生成）</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>售后工单（{{ afterSales.length }}）</h3>
      <table class="table">
        <thead><tr><th>#</th><th>订单</th><th>类型</th><th>原因</th><th>金额</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in afterSales" :key="a.id">
            <td>{{ a.id }}</td>
            <td>#{{ a.order_id }}</td>
            <td>{{ afterSaleType(a.type) }}</td>
            <td>{{ a.reason }}</td>
            <td>{{ yuan(a.amount_cents) }} 元</td>
            <td><span class="tag" :class="a.status === 'pending' ? 'warn' : a.status === 'approved' ? 'ended' : ''">{{ afterSaleStatus(a.status) }}</span></td>
            <td class="row">
              <template v-if="a.status === 'pending'">
                <button class="btn sm ok" @click="resolve(a, 'approve')">同意（退款回补库存）</button>
                <button class="btn sm danger" @click="resolve(a, 'reject')">驳回</button>
              </template>
              <span v-else class="muted">{{ a.handler_note || '—' }}</span>
            </td>
          </tr>
          <tr v-if="!afterSales.length"><td colspan="7" class="muted">暂无售后工单</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, yuan } from '../api'
import type { AfterSale, Order, Session } from '../api/types'
import PromptDialog from '../components/PromptDialog.vue'

const route = useRoute()
const sessionId = Number(route.params.sessionId)

const session = ref<Session | null>(null)
const orders = ref<Order[]>([])
const afterSales = ref<AfterSale[]>([])
const statusFilter = ref('')
const error = ref('')

// 内置浏览器/嵌入式 WebView 不支持 window.prompt（直接抛错），统一走应用内对话框
const promptState = ref<{ show: boolean; title: string; value: string; onOk: (text: string) => Promise<void> }>({
  show: false, title: '', value: '', onOk: async () => {}
})
function openPrompt(title: string, value: string, onOk: (text: string) => Promise<void>) {
  promptState.value = { show: true, title, value, onOk }
}
async function onPromptConfirm(text: string) {
  const run = promptState.value.onOk
  promptState.value.show = false
  try { await run(text) } catch (e) { error.value = (e as Error).message }
}

const statusLabel = computed(() => {
  const map: Record<string, string> = { preparing: '准备中', live: '直播中', paused: '已暂停', ended: '已下播', submitted: '已提交' }
  return map[session.value?.status || ''] || ''
})
const statusClass = computed(() => (session.value?.status === 'live' ? 'live' : session.value?.status === 'ended' ? 'ended' : 'preparing'))

function orderLabel(s: string) {
  return { pending_ship: '待发货', shipping: '运输中', signed: '已签收', closed: '已关闭' }[s] || s
}
function orderTag(s: string) {
  return s === 'pending_ship' ? 'warn' : s === 'shipping' ? 'preparing' : s === 'signed' ? 'ended' : ''
}
function nodeLabel(n: string) {
  return { picked_up: '已揽收', in_transit: '运输中', delivering: '派送中', signed: '已签收', rejected: '已拒收' }[n] || n
}
function afterSaleType(t: string) {
  return { refund: '退款', return: '退货', exchange: '换货', complaint: '投诉', oversell: '超卖', delay: '延迟发货' }[t] || t
}
function afterSaleStatus(s: string) {
  return { pending: '待处理', approved: '已同意', rejected: '已驳回', closed: '已结案' }[s] || s
}

async function loadOrders() {
  error.value = ''
  session.value = await api.sessions.get(sessionId)
  const params: Record<string, unknown> = { page_size: 200 }
  if (statusFilter.value) params.status = statusFilter.value
  orders.value = (await api.orders.list(sessionId, params)).items
  afterSales.value = await api.afterSales.list(sessionId)
}

async function ship(order: Order) {
  error.value = ''
  try { await api.orders.ship(order.id); await loadOrders() } catch (e) { error.value = (e as Error).message }
}

async function advance(order: Order, node: string) {
  error.value = ''
  try { await api.orders.advance(order.id, node); await loadOrders() } catch (e) { error.value = (e as Error).message }
}

function openAfterSale(order: Order) {
  openPrompt('售后原因（如：顾客反馈果径偏小）', '顾客反馈与描述不符', async (reason) => {
    await api.afterSales.create(sessionId, { order_id: order.id, type: 'refund', reason })
    await loadOrders()
  })
}

async function resolve(afterSale: AfterSale, action: 'approve' | 'reject') {
  error.value = ''
  try {
    await api.afterSales.resolve(afterSale.id, action, action === 'approve' ? '同意处理并回补库存' : '不符合售后条件')
    await loadOrders()
  } catch (e) { error.value = (e as Error).message }
}

onMounted(loadOrders)
</script>

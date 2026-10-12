<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">数据复盘 · 场次 #{{ sessionId }}</h3>
        <span class="tag" :class="session?.status === 'submitted' ? 'ended' : 'preparing'">{{ statusLabel }}</span>
        <div class="spacer" />
        <button class="btn ghost sm" @click="loadAll">刷新</button>
        <router-link class="btn sm ghost" :to="{ name: 'orders', params: { sessionId } }">订单履约</router-link>
      </div>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
      <p v-if="notice" class="ok-text" style="margin:10px 0 0">{{ notice }}</p>
    </div>

    <div class="grid grid-4" style="margin-bottom:16px">
      <div class="metric"><div class="num">{{ overview.viewers ?? 0 }}</div><div class="label">累计观看</div></div>
      <div class="metric"><div class="num">{{ overview.item_clicks ?? 0 }}</div><div class="label">商品点击</div></div>
      <div class="metric"><div class="num">{{ overview.orders ?? 0 }}</div><div class="label">成交订单</div></div>
      <div class="metric"><div class="num">{{ yuan(overview.gmv_cents) }}</div><div class="label">GMV（元）</div></div>
      <div class="metric"><div class="num">{{ pct(overview.click_rate) }}</div><div class="label">点击率</div></div>
      <div class="metric"><div class="num">{{ pct(overview.conversion_rate) }}</div><div class="label">转化率</div></div>
      <div class="metric"><div class="num">{{ yuan(overview.aov_cents) }}</div><div class="label">客单价（元）</div></div>
      <div class="metric"><div class="num">{{ overview.violations ?? 0 }}</div><div class="label">违规次数</div></div>
    </div>

    <div class="card">
      <div class="row">
        <h3 style="margin:0">复盘报告</h3>
        <span v-if="report" class="tag" :class="report.source === 'llm' ? 'ended' : 'warn'">
          来源：{{ report.source === 'llm' ? '大模型生成' : '规则兜底（未接入大模型）' }}
        </span>
        <span v-if="report" class="tag">{{ reportStatusLabel }}</span>
        <div class="spacer" />
        <button class="btn sm" :disabled="!session || session.status === 'preparing'" @click="generate">生成 / 重新生成</button>
      </div>

      <template v-if="report">
        <p class="muted" style="margin:10px 0">{{ report.content?.overview }}</p>
        <div v-for="section in report.content?.sections || []" :key="section.key" class="section">
          <b>{{ section.title }}</b>
          <div>{{ section.summary }}</div>
          <ul><li v-for="(b, i) in section.bullets || []" :key="i">{{ b }}</li></ul>
        </div>
        <div class="grid grid-2">
          <div>
            <h4 style="margin:12px 0 6px">亮点</h4>
            <ul><li v-for="(h, i) in report.content?.highlights || []" :key="i">{{ h }}</li></ul>
            <h4 style="margin:12px 0 6px">问题</h4>
            <ul><li v-for="(h, i) in report.content?.issues || []" :key="i">{{ h }}</li></ul>
          </div>
          <div>
            <h4 style="margin:12px 0 6px">风险</h4>
            <ul><li v-for="(h, i) in report.content?.risks || []" :key="i">{{ h }}</li></ul>
            <h4 style="margin:12px 0 6px">下一场建议</h4>
            <ul><li v-for="(h, i) in report.content?.next_actions || []" :key="i">{{ h }}</li></ul>
          </div>
        </div>
        <div v-if="report.content?.adopted_notes?.length" class="muted" style="margin-top:8px">
          已采纳智能体结果 {{ report.content.adopted_notes.length }} 条
        </div>

        <h4 style="margin:16px 0 6px">我的改进措施 <span class="muted">（提交前可修改，提交后锁定）</span></h4>
        <textarea v-model="improvement" class="textarea" :disabled="report.locked"></textarea>
        <div class="row" style="margin-top:10px">
          <button class="btn ghost sm" :disabled="report.locked" @click="saveImprovement">保存草稿</button>
          <button class="btn sm" :disabled="report.locked" @click="submitReport">提交复盘（锁定）</button>
          <span v-if="report.locked" class="muted">已提交于 {{ submittedAtText }}，如需修改请联系教师退回复盘</span>
        </div>
      </template>
      <p v-else class="muted">尚未生成报告：完成直播并下播后点击「生成」。</p>
    </div>

    <div class="card">
      <h3>成绩</h3>
      <template v-if="score">
        <div class="grid grid-3">
          <div class="metric"><div class="num">{{ score.objective_score }}</div><div class="label">客观分</div></div>
          <div class="metric"><div class="num">{{ score.subjective_score ?? '—' }}</div><div class="label">教师主观分</div></div>
          <div class="metric"><div class="num">{{ score.comprehensive_score ?? '—' }}</div><div class="label">综合成绩</div></div>
        </div>
        <table class="table" style="margin-top:12px">
          <thead><tr><th>维度</th><th>得分</th><th>权重</th></tr></thead>
          <tbody>
            <tr v-for="(v, k) in score.objective_detail?.dimensions || {}" :key="k">
              <td>{{ dimensionLabel(String(k)) }}</td>
              <td>{{ v }}</td>
              <td>{{ score.objective_detail?.weights?.[k] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="score.comment" class="muted">教师评语：{{ score.comment }}</p>
      </template>
      <p v-else class="muted">暂无成绩（需提交复盘后由教师评分）</p>

      <template v-if="isTeacher">
        <h4 style="margin:16px 0 6px">教师评分</h4>
        <div class="row">
          <input v-model.number="subjective" type="number" class="input" style="max-width:120px" placeholder="主观分 0-100" />
          <input v-model="comment" class="input" style="max-width:360px" placeholder="评语" />
          <button class="btn sm" @click="submitScore">提交评分</button>
          <button class="btn ghost sm" @click="returnReport">退回复盘</button>
        </div>
      </template>
    </div>

    <div class="card">
      <h3>数据口径说明</h3>
      <ul class="muted"><li v-for="(n, i) in metricsNotes" :key="i">{{ n }}</li></ul>
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
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, yuan } from '../api'
import type { Report, Score, Session } from '../api/types'
import { useAuthStore } from '../stores/auth'
import PromptDialog from '../components/PromptDialog.vue'

const route = useRoute()
const auth = useAuthStore()
const sessionId = Number(route.params.sessionId)

const session = ref<Session | null>(null)
const overview = ref<Record<string, any>>({})
const report = ref<Report | null>(null)
const score = ref<Score | null>(null)
const improvement = ref('')
const metricsNotes = ref<string[]>([])
const error = ref('')
const notice = ref('')
const subjective = ref<number>(85)
const comment = ref('')

// 内置浏览器/嵌入式 WebView 不支持 window.prompt（直接抛错），统一走应用内对话框
const promptState = ref<{ show: boolean; title: string; value: string; withInput: boolean; onOk: (text: string) => Promise<void> }>({
  show: false, title: '', value: '', withInput: true, onOk: async () => {}
})
function openPrompt(title: string, value: string, onOk: (text: string) => Promise<void>) {
  promptState.value = { show: true, title, value, withInput: true, onOk }
}
function openConfirm(title: string, onOk: () => Promise<void>) {
  promptState.value = { show: true, title, value: '', withInput: false, onOk: async () => { await onOk() } }
}
async function onPromptConfirm(text: string) {
  const run = promptState.value.onOk
  promptState.value.show = false
  try { await run(text) } catch (e) { error.value = (e as Error).message }
}

const isTeacher = computed(() => auth.isTeacher)
const statusLabel = computed(() => {
  const map: Record<string, string> = { preparing: '准备中', live: '直播中', paused: '已暂停', ended: '已下播', submitted: '已提交' }
  return map[session.value?.status || ''] || session.value?.status || ''
})
const submittedAtText = computed(() => {
  const raw = report.value?.submitted_at
  return raw ? new Date(raw).toLocaleString('zh-CN', { hour12: false }) : '—'
})
const reportStatusLabel = computed(() => {
  const map: Record<string, string> = { draft: '草稿', submitted: '已提交', returned: '已退回', scored: '已评分' }
  return map[report.value?.status || ''] || ''
})

function pct(v: unknown) {
  if (v === null || v === undefined) return '—'
  return `${(Number(v) * 100).toFixed(1)}%`
}

function dimensionLabel(key: string) {
  return { operation: '经营结果', process: '过程完成度', service: '履约与售后', compliance: '合规表现', review: '复盘质量' }[key] || key
}

async function loadAll() {
  error.value = ''
  try {
    session.value = await api.sessions.get(sessionId)
    const metrics = await api.reviews.metrics(sessionId, 'overview')
    overview.value = metrics.data
    metricsNotes.value = metrics.notes
    try {
      report.value = await api.reviews.getReport(sessionId)
      improvement.value = report.value.improvement_plan || ''
    } catch { report.value = null }
    try {
      score.value = await api.reviews.getScore(sessionId)
    } catch { score.value = null }
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function generate() {
  error.value = ''; notice.value = ''
  try {
    report.value = await api.reviews.generateReport(sessionId)
    notice.value = '报告已生成'
  } catch (e) { error.value = (e as Error).message }
}

async function saveImprovement() {
  error.value = ''; notice.value = ''
  try {
    report.value = await api.reviews.updateReport(sessionId, improvement.value)
    notice.value = '改进措施已保存（草稿）'
  } catch (e) { error.value = (e as Error).message }
}

async function submitReport() {
  openConfirm('提交后报告进入只读状态，确认提交？', async () => {
    await api.reviews.updateReport(sessionId, improvement.value)
    report.value = await api.reviews.submitReport(sessionId)
    notice.value = '复盘已提交并锁定'
  })
}

async function submitScore() {
  error.value = ''; notice.value = ''
  try {
    score.value = await api.reviews.score(sessionId, subjective.value, comment.value)
    notice.value = '评分已保存'
  } catch (e) { error.value = (e as Error).message }
}

async function returnReport() {
  openPrompt('退回原因（学生将可修改并重新提交）', '', async (reason) => {
    await api.reviews.returnReport(sessionId, reason)
    await loadAll()
    notice.value = '已退回复盘'
  })
}

onMounted(loadAll)
</script>

<style scoped>
.section { border-top: 1px solid var(--border); padding: 10px 0; }
ul { margin: 6px 0; padding-left: 20px; }
</style>

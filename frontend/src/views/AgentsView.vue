<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">AI 岗位智能体中心</h3>
        <div class="spacer" />
        <select v-model="scope" class="select" style="max-width:160px" @change="loadAgents">
          <option value="">全部（内置/班级/个人）</option>
          <option value="builtin">系统内置</option>
          <option value="class">班级共享</option>
          <option value="personal">我的个人</option>
        </select>
        <button class="btn ghost sm" @click="loadAgents">刷新</button>
      </div>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
      <p v-if="notice" class="ok-text" style="margin:10px 0 0">{{ notice }}</p>
      <p class="muted" style="margin:8px 0 0">
        规则：内置/班级共享智能体需「已上架」才能正式运行；个人智能体仅创建者可用；
        结果遵循「先生成、后采纳」，采纳后才写入本人脚本或复盘。
        运行结果以 <b>source</b> 字段标明来源：<b>llm</b> 为大模型生成，<b>rule</b> 为规则兜底（未接入大模型）。
      </p>
    </div>

    <div class="grid grid-2">
      <div class="card">
        <h3>智能体市场（{{ agents.length }}）</h3>
        <table class="table">
          <thead><tr><th>名称</th><th>岗位</th><th>范围/状态</th><th>完成度</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="a in agents" :key="a.id">
              <td>
                {{ a.name }}
                <div class="muted">{{ a.duty }}</div>
              </td>
              <td>{{ positionLabel(a.position_type) }}</td>
              <td>
                <span class="tag">{{ scopeLabel(a.scope) }}</span>
                <span class="tag" :class="statusTag(a.status)">{{ statusLabel(a.status) }}</span>
              </td>
              <td>{{ Math.round(a.completeness * 100) }}%</td>
              <td class="row">
                <button class="btn sm" @click="selectAgent(a)">运行</button>
                <button v-if="isOwner(a) && (a.status === 'draft' || a.status === 'rejected')" class="btn sm ghost" @click="submitForReview(a)">提交审核</button>
                <template v-if="isTeacher && a.status === 'pending'">
                  <button class="btn sm ok" @click="review(a, 'approve')">上架</button>
                  <button class="btn sm danger" @click="review(a, 'reject')">驳回</button>
                </template>
              </td>
            </tr>
            <tr v-if="!agents.length"><td colspan="5" class="muted">暂无智能体</td></tr>
          </tbody>
        </table>
      </div>

      <div>
        <div class="card">
          <h3>运行智能体 {{ selected ? `· ${selected.name}` : '' }}</h3>
          <template v-if="selected">
            <p class="muted">{{ selected.duty }}</p>
            <label class="muted">请求内容</label>
            <textarea v-model="prompt" class="textarea" placeholder="例：顾客说收到货有破损怎么办？"></textarea>
            <label class="muted" style="display:block;margin-top:8px">关联场次（可选，用于读取场次上下文）</label>
            <input v-model.number="runSessionId" type="number" class="input" placeholder="场次 ID" />
            <div class="row" style="margin-top:10px">
              <button class="btn sm" @click="runAgent(false)">预演（不落库）</button>
              <button class="btn sm ghost" @click="runAgent(true)">正式运行（落库）</button>
            </div>
            <template v-if="runResult">
              <div class="output">
                <div class="row">
                  <span class="tag" :class="runResult.source === 'llm' ? 'ended' : 'warn'">来源：{{ runResult.source }}</span>
                  <span class="muted">模型 {{ runResult.model }} · {{ runResult.latency_ms }}ms</span>
                </div>
                <p style="white-space:pre-wrap">{{ runResult.output?.result }}</p>
                <div v-if="runResult.output?.evidence?.length" class="muted">依据：{{ runResult.output.evidence.join('；') }}</div>
                <div v-if="runResult.output?.caveats?.length" class="muted">注意：{{ runResult.output.caveats.join('；') }}</div>
                <div class="row" style="margin-top:10px">
                  <button class="btn sm" :disabled="!runResult.id" @click="adopt('script')">采纳到脚本</button>
                  <button class="btn sm ghost" :disabled="!runResult.id" @click="adopt('report')">采纳到复盘</button>
                </div>
                <p v-if="!runResult.id" class="muted">预演结果不落库，如需采纳请先「正式运行」。</p>
              </div>
            </template>
          </template>
          <p v-else class="muted">从左侧市场选择一个智能体。</p>
        </div>

        <div class="card">
          <h3>设计新智能体</h3>
          <div class="grid grid-2">
            <div><label class="muted">名称</label><input v-model="createForm.name" class="input" /></div>
            <div>
              <label class="muted">岗位</label>
              <select v-model="createForm.position_type" class="select">
                <option value="service">客服</option>
                <option value="select">选品</option>
                <option value="operation">运营</option>
                <option value="control">场控</option>
                <option value="host">主播</option>
                <option value="teaching">教学</option>
              </select>
            </div>
            <div>
              <label class="muted">从内置模板起步</label>
              <select v-model.number="createForm.from_template_id" class="select">
                <option :value="null">不使用模板</option>
                <option v-for="t in builtinTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
              </select>
            </div>
            <div><label class="muted">工具（逗号分隔）</label><input v-model="createForm.tools" class="input" placeholder="弹幕事件流,FAQ 配置" /></div>
          </div>
          <label class="muted" style="display:block;margin-top:8px">职责</label>
          <input v-model="createForm.duty" class="input" />
          <label class="muted" style="display:block;margin-top:8px">行为指令</label>
          <textarea v-model="createForm.instructions" class="textarea" placeholder="明确服务边界、回复口径与升级条件"></textarea>
          <label class="muted" style="display:block;margin-top:8px">知识卡（逗号分隔）</label>
          <input v-model="createForm.knowledge_cards" class="input" placeholder="七天无理由,发货时效" />
          <button class="btn" style="margin-top:12px" @click="createAgent">创建（草稿）</button>
          <p class="muted" style="margin-top:8px">完成度 = 命名 20% + 职责 25% + 行为指令 35% + 工具 20%；低于 60% 不能提交审核。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import type { Agent, AgentRun } from '../api/types'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const agents = ref<Agent[]>([])
const scope = ref('')
const selected = ref<Agent | null>(null)
const prompt = ref('顾客说收到货有破损怎么办？')
const runSessionId = ref<number | null>(null)
const runResult = ref<(AgentRun & { persist?: boolean }) | null>(null)
const error = ref('')
const notice = ref('')

const createForm = reactive({
  name: '客服应答助手',
  position_type: 'service',
  from_template_id: null as number | null,
  duty: '处理观众咨询与售后争议',
  instructions: '按 FAQ 与服务条款口径回复，不做超范围承诺，争议升级教师复核。',
  tools: '弹幕事件流,FAQ 配置',
  knowledge_cards: '七天无理由,发货时效'
})

const isTeacher = computed(() => auth.isTeacher)

const builtinTemplates = computed(() => agents.value.filter((a) => a.scope === 'builtin'))

function scopeLabel(s: string) {
  return { builtin: '系统内置', class: '班级共享', personal: '个人' }[s] || s
}
function statusLabel(s: string) {
  return { draft: '草稿', pending: '待审核', published: '已上架', rejected: '已驳回' }[s] || s
}
function statusTag(s: string) {
  return s === 'published' ? 'ended' : s === 'pending' ? 'warn' : ''
}
function positionLabel(p: string) {
  return { select: '选品', operation: '运营', control: '场控', service: '客服', host: '主播', teaching: '教学' }[p] || p
}
function isOwner(a: Agent) {
  return a.owner_id === auth.user?.id
}

async function loadAgents() {
  error.value = ''
  try {
    const params: Record<string, unknown> = { page_size: 50 }
    if (scope.value) params.scope = scope.value
    agents.value = (await api.agents.list(params)).items
    if (selected.value) {
      selected.value = agents.value.find((a) => a.id === selected.value?.id) || null
    }
  } catch (e) { error.value = (e as Error).message }
}

function selectAgent(agent: Agent) {
  selected.value = agent
  runResult.value = null
}

async function runAgent(persist: boolean) {
  if (!selected.value) return
  error.value = ''; notice.value = ''
  try {
    if (persist) {
      runResult.value = await api.agents.run(selected.value.id, prompt.value, runSessionId.value)
      notice.value = '已生成并记录运行轨迹'
    } else {
      const data = await api.agents.rehearse(selected.value.id, prompt.value)
      runResult.value = data as unknown as AgentRun
    }
  } catch (e) { error.value = (e as Error).message }
}

async function adopt(target: 'script' | 'report') {
  if (!runResult.value?.id) return
  error.value = ''; notice.value = ''
  try {
    await api.agents.adopt(runResult.value.id, target)
    notice.value = `已采纳写入${target === 'script' ? '脚本' : '复盘'}`
  } catch (e) { error.value = (e as Error).message }
}

async function createAgent() {
  error.value = ''; notice.value = ''
  try {
    await api.agents.create({
      name: createForm.name,
      position_type: createForm.position_type,
      duty: createForm.duty,
      instructions: createForm.instructions,
      tools: createForm.tools.split(',').map((s) => s.trim()).filter(Boolean),
      knowledge_cards: createForm.knowledge_cards.split(',').map((s) => s.trim()).filter(Boolean),
      from_template_id: createForm.from_template_id
    })
    notice.value = '智能体已创建（草稿），可在市场中「提交审核」'
    await loadAgents()
  } catch (e) { error.value = (e as Error).message }
}

async function submitForReview(agent: Agent) {
  error.value = ''; notice.value = ''
  try {
    await api.agents.submit(agent.id)
    notice.value = `「${agent.name}」已提交审核`
    await loadAgents()
  } catch (e) { error.value = (e as Error).message }
}

async function review(agent: Agent, action: 'approve' | 'reject') {
  error.value = ''; notice.value = ''
  try {
    await api.agents.review(agent.id, action, action === 'approve' ? '配置完整，可进入班级市场' : '请补充行为指令与工具')
    notice.value = action === 'approve' ? '已上架到班级市场' : '已驳回'
    await loadAgents()
  } catch (e) { error.value = (e as Error).message }
}

onMounted(loadAgents)
</script>

<style scoped>
.output { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; }
ul { padding-left: 20px; }
</style>

<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">任务与场次</h3>
        <div class="spacer" />
        <button v-if="auth.isTeacher" class="btn sm" @click="showCreate = !showCreate">
          {{ showCreate ? '收起' : '新建任务' }}
        </button>
        <button class="btn ghost sm" @click="load">刷新</button>
      </div>

      <div v-if="showCreate && auth.isTeacher" class="create-box">
        <div class="grid grid-3">
          <div><label class="muted">任务标题</label><input v-model="form.title" class="input" /></div>
          <div>
            <label class="muted">班级</label>
            <select v-model.number="form.class_id" class="select">
              <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div><label class="muted">初始资金（元）</label><input v-model.number="form.fundYuan" type="number" class="input" /></div>
          <div><label class="muted">市场热度 1-10</label><input v-model.number="form.market_heat" type="number" step="0.5" class="input" /></div>
          <div><label class="muted">竞争难度 1-10</label><input v-model.number="form.competition_level" type="number" step="0.5" class="input" /></div>
          <div>
            <label class="muted">严格开播检查</label>
            <select v-model="form.strict_mode" class="select">
              <option :value="false">否（普通练习）</option>
              <option :value="true">是（考核/竞赛）</option>
            </select>
          </div>
        </div>
        <p v-if="createError" class="error">{{ createError }}</p>
        <button class="btn" style="margin-top:12px" @click="createTask">创建并发布</button>
      </div>
    </div>

    <div class="card">
      <h3>可参与任务</h3>
      <table class="table">
        <thead>
          <tr><th>任务</th><th>模式</th><th>状态</th><th>初始资金</th><th>热度/难度</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id">
            <td>
              {{ t.title }}
              <div class="muted">{{ t.description }}</div>
            </td>
            <td>{{ t.mode === 'team' ? '团队协作' : '个人练习' }}</td>
            <td>
              <span class="tag" :class="t.status === 'published' ? 'ended' : 'warn'">
                {{ t.status === 'published' ? '已发布' : t.status === 'closed' ? '已关闭' : '草稿' }}
              </span>
            </td>
            <td>{{ yuan(t.initial_fund_cents) }} 元</td>
            <td>{{ t.market_heat }} / {{ t.competition_level }}</td>
            <td>
              <button v-if="t.status === 'draft'" class="btn sm" @click="publishTask(t)">发布</button>
              <span v-else-if="!auth.isTeacher" class="row">
                <select v-if="t.mode === 'team' && myTeams.length" v-model.number="teamChoice[t.id]" class="select" style="width:150px">
                  <option :value="0">选择团队（协作）</option>
                  <option v-for="tm in myTeams" :key="tm.id" :value="tm.id">{{ tm.name }}</option>
                </select>
                <button class="btn sm" @click="createSession(t)">创建场次</button>
              </span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
          <tr v-if="!tasks.length"><td colspan="6" class="muted">暂无任务</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>我的场次</h3>
      <table class="table">
        <thead>
          <tr><th>场次</th><th>状态</th><th>资金余额</th><th>观看/成交</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id">
            <td>{{ s.name }}<div class="muted">#{{ s.id }}</div></td>
            <td><span class="tag" :class="statusClass(s.status)">{{ statusLabel(s.status) }}</span></td>
            <td>{{ yuan(s.fund_balance_cents) }} 元</td>
            <td>{{ s.metrics?.viewers ?? 0 }} / {{ s.metrics?.orders ?? 0 }}</td>
            <td class="row">
              <button class="btn sm ghost" @click="enter(s, 'workbench')">经营准备</button>
              <button class="btn sm" @click="enter(s, 'live')">直播工作台</button>
              <button class="btn sm ghost" @click="enter(s, 'orders')">订单履约</button>
              <button class="btn sm ghost" @click="enter(s, 'review')">数据复盘</button>
            </td>
          </tr>
          <tr v-if="!sessions.length"><td colspan="5" class="muted">暂无声次，先从上方任务创建</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, yuan } from '../api'
import type { Session, Task } from '../api/types'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const tasks = ref<Task[]>([])
const sessions = ref<Session[]>([])
const classes = ref<Array<Record<string, any>>>([])
const myTeams = ref<Array<Record<string, any>>>([])
const teamChoice = reactive<Record<number, number>>({})
const showCreate = ref(false)
const createError = ref('')

const form = reactive({
  title: '助农产品直播选品与运营实训',
  class_id: 0,
  fundYuan: 50000,
  market_heat: 7,
  competition_level: 4,
  strict_mode: false
})

async function load() {
  const taskPage = await api.tasks.list({ page_size: 50 })
  tasks.value = taskPage.items
  const sessionPage = await api.sessions.list({ page_size: 50 })
  sessions.value = sessionPage.items
  if (auth.isTeacher) {
    classes.value = await api.classes.list()
    if (!form.class_id && classes.value.length) form.class_id = classes.value[0].id
  } else if (auth.user?.class_id) {
    // 学生：加载本人所在的团队（团队任务可协作开单，岗位分工在团队成员中配置）
    try {
      const teams = await api.classes.teams(auth.user.class_id)
      myTeams.value = teams.filter((t: Record<string, any>) =>
        (t.members || []).some((m: Record<string, any>) => m.user_id === auth.user?.id)
      )
    } catch { myTeams.value = [] }
  }
}

async function createTask() {
  createError.value = ''
  try {
    const task = await api.tasks.create({
      title: form.title,
      class_id: form.class_id,
      initial_fund_cents: Math.round(form.fundYuan * 100),
      market_heat: form.market_heat,
      competition_level: form.competition_level,
      strict_mode: form.strict_mode
    })
    await api.tasks.publish(task.id)
    showCreate.value = false
    await load()
  } catch (e) {
    createError.value = (e as Error).message
  }
}

async function publishTask(task: Task) {
  await api.tasks.publish(task.id)
  await load()
}

async function createSession(task: Task) {
  const payload: Record<string, unknown> = {}
  if (task.mode === 'team' && teamChoice[task.id]) payload.team_id = teamChoice[task.id]
  const session = await api.sessions.createForTask(task.id, payload)
  await load()
  router.push({ name: 'workbench', params: { sessionId: session.id } })
}

function enter(session: Session, target: 'workbench' | 'live' | 'orders' | 'review') {
  router.push({ name: target, params: { sessionId: session.id } })
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    preparing: '准备中', live: '直播中', paused: '已暂停', ended: '已下播', submitted: '已提交'
  }
  return map[status] || status
}

function statusClass(status: string) {
  if (status === 'live') return 'live'
  if (status === 'preparing') return 'preparing'
  if (status === 'ended' || status === 'submitted') return 'ended'
  return 'warn'
}

onMounted(load)
</script>

<style scoped>
.create-box { border-top: 1px dashed var(--border); margin-top: 12px; padding-top: 12px; }
</style>

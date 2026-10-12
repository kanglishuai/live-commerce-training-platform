<template>
  <div>
    <div class="card">
      <div class="row">
        <h3 style="margin:0">班级与巡课</h3>
        <div class="spacer" />
        <select v-model.number="classId" class="select" style="max-width:220px" @change="loadDetail">
          <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <button class="btn ghost sm" @click="loadDetail">刷新</button>
      </div>
      <p v-if="error" class="error" style="margin:10px 0 0">{{ error }}</p>
    </div>

    <div v-if="report" class="card">
      <h3>班级报告 · {{ report.class_name }}</h3>
      <div class="grid grid-4">
        <div class="metric"><div class="num">{{ report.summary.sessions }}</div><div class="label">场次</div></div>
        <div class="metric"><div class="num">{{ report.summary.students_participated }}</div><div class="label">参与学生</div></div>
        <div class="metric"><div class="num">{{ yuan(report.summary.gmv_cents_total) }}</div><div class="label">GMV 合计（元）</div></div>
        <div class="metric"><div class="num">{{ report.summary.avg_comprehensive ?? '—' }}</div><div class="label">平均综合成绩</div></div>
      </div>
      <table class="table" style="margin-top:12px">
        <thead><tr><th>学生</th><th>场次状态</th><th>GMV</th><th>订单</th><th>客观分</th><th>主观分</th><th>综合</th></tr></thead>
        <tbody>
          <tr v-for="row in report.students" :key="row.session_id">
            <td>{{ row.student_name }}<div class="muted">场次 #{{ row.session_id }}</div></td>
            <td>{{ row.status }}</td>
            <td>{{ yuan(row.gmv_cents) }} 元</td>
            <td>{{ row.orders }}</td>
            <td>{{ row.objective_score ?? '—' }}</td>
            <td>{{ row.subjective_score ?? '—' }}</td>
            <td>{{ row.comprehensive_score ?? '—' }}</td>
          </tr>
          <tr v-if="!report.students?.length"><td colspan="7" class="muted">该班级暂无场次</td></tr>
        </tbody>
      </table>
      <p class="muted" style="margin-top:8px">导出：{{ report.summary.export }}</p>
    </div>

    <div v-if="patrol" class="card">
      <h3>巡课工作台</h3>
      <table class="table">
        <thead><tr><th>场次</th><th>学生</th><th>状态</th><th>实时指标</th><th>最新弹幕</th><th></th></tr></thead>
        <tbody>
          <tr v-for="g in patrol.groups" :key="g.session_id">
            <td>{{ g.title }}<div class="muted">#{{ g.session_id }} · {{ g.prep_progress }}</div></td>
            <td>{{ g.owner_name }}</td>
            <td><span class="tag" :class="g.status === 'live' ? 'live' : g.status === 'preparing' ? 'preparing' : 'ended'">{{ g.status }}</span></td>
            <td class="muted">在线 {{ g.metrics.online }} / 观看 {{ g.metrics.viewers }} / 订单 {{ g.metrics.orders }} / GMV {{ yuan(g.metrics.gmv_cents) }} 元</td>
            <td class="muted">{{ (g.latest_comments || []).join(' ｜ ') || '—' }}</td>
            <td>
              <router-link class="btn sm ghost" :to="{ name: 'workbench', params: { sessionId: g.session_id } }">看货盘调研</router-link>
              <router-link class="btn sm ghost" :to="{ name: 'live', params: { sessionId: g.session_id } }">观察直播</router-link>
              <router-link class="btn sm ghost" :to="{ name: 'review', params: { sessionId: g.session_id } }">看复盘</router-link>
            </td>
          </tr>
          <tr v-if="!patrol.groups?.length"><td colspan="6" class="muted">暂无声次</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>竞赛与排行榜 <span class="muted">（同场对比：相同初始条件、按所选口径排名）</span></h3>
      <div class="row" style="margin-bottom:12px">
        <input v-model="compForm.name" class="input" style="max-width:260px" placeholder="竞赛名称，如：同场对比赛" />
        <select v-model="compForm.metric" class="select" style="max-width:220px">
          <option value="comprehensive">综合分（默认）</option>
          <option value="gmv">GMV</option>
          <option value="profit">利润（期末资金-初始资金）</option>
          <option value="conversion">转化率</option>
          <option value="compliance">合规分</option>
          <option value="interaction">互动量</option>
          <option value="fulfillment">履约率</option>
        </select>
        <select v-model.number="compForm.task_id" class="select" style="max-width:280px">
          <option :value="0">不限任务（本班全部场次）</option>
          <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.title }}</option>
        </select>
        <button class="btn sm" @click="createCompetition">创建竞赛</button>
        <button class="btn ghost sm" @click="loadCompetitions">刷新</button>
      </div>
      <table class="table">
        <thead><tr><th>竞赛</th><th>口径</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="c in competitions" :key="c.id">
            <td>{{ c.name }}<div class="muted">#{{ c.id }}</div></td>
            <td>{{ metricLabel(c.metric) }}</td>
            <td><span class="tag" :class="c.status === 'running' ? 'ended' : ''">{{ c.status === 'running' ? '进行中' : '已结束' }}</span></td>
            <td><button class="btn sm" @click="showLeaderboard(c)">查看排行榜</button></td>
          </tr>
          <tr v-if="!competitions.length"><td colspan="4" class="muted">暂无竞赛</td></tr>
        </tbody>
      </table>

      <template v-if="leaderboard">
        <h4 style="margin:16px 0 6px">排行榜 · {{ leaderboard.metric }}（{{ leaderboard.entries?.length || 0 }} 条）</h4>
        <table class="table">
          <thead><tr><th>名次</th><th>学生/场次</th><th>得分</th><th>GMV</th><th>利润</th><th>转化率</th><th>合规</th><th>互动</th><th>履约</th></tr></thead>
          <tbody>
            <tr v-for="e in leaderboard.entries" :key="e.session_id">
              <td>{{ e.rank }}</td>
              <td>{{ e.owner_name }}<div class="muted">{{ e.session_name }} · {{ e.session_status }}</div></td>
              <td><b>{{ e.value }}</b></td>
              <td>{{ yuan(e.by_metric?.gmv) }}</td>
              <td>{{ yuan(e.by_metric?.profit) }}</td>
              <td>{{ ((e.by_metric?.conversion || 0) * 100).toFixed(1) }}%</td>
              <td>{{ e.by_metric?.compliance }}</td>
              <td>{{ e.by_metric?.interaction }}</td>
              <td>{{ ((e.by_metric?.fulfillment || 0) * 100).toFixed(0) }}%</td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, yuan } from '../api'
import type { Task } from '../api/types'

const classes = ref<Array<Record<string, any>>>([])
const classId = ref(0)
const report = ref<Record<string, any> | null>(null)
const patrol = ref<Record<string, any> | null>(null)
const tasks = ref<Task[]>([])
const competitions = ref<Array<Record<string, any>>>([])
const leaderboard = ref<Record<string, any> | null>(null)
const error = ref('')

const compForm = reactive({ name: '同场对比赛', metric: 'comprehensive', task_id: 0 })

function metricLabel(metric: string) {
  return {
    comprehensive: '综合分', gmv: 'GMV', profit: '利润', conversion: '转化率',
    compliance: '合规', interaction: '互动', fulfillment: '履约率'
  }[metric] || metric
}

async function loadClasses() {
  error.value = ''
  try {
    classes.value = await api.classes.list()
    if (classes.value.length && !classId.value) classId.value = classes.value[0].id
    tasks.value = (await api.tasks.list({ page_size: 50 })).items
    await loadDetail()
    await loadCompetitions()
  } catch (e) { error.value = (e as Error).message }
}

async function loadDetail() {
  if (!classId.value) return
  error.value = ''
  try {
    report.value = await api.classes.report(classId.value)
    patrol.value = await api.classes.patrol(classId.value)
  } catch (e) { error.value = (e as Error).message }
}

async function loadCompetitions() {
  if (!classId.value) return
  try {
    competitions.value = await api.competitions.list({ class_id: classId.value })
    leaderboard.value = null
  } catch (e) { error.value = (e as Error).message }
}

async function createCompetition() {
  error.value = ''
  try {
    await api.competitions.create({
      class_id: classId.value,
      name: compForm.name,
      metric: compForm.metric,
      task_id: compForm.task_id || null
    })
    await loadCompetitions()
  } catch (e) { error.value = (e as Error).message }
}

async function showLeaderboard(comp: Record<string, any>) {
  error.value = ''
  try {
    leaderboard.value = await api.competitions.leaderboard(comp.id)
  } catch (e) { error.value = (e as Error).message }
}

onMounted(loadClasses)
</script>

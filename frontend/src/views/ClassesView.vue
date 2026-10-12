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
              <router-link class="btn sm ghost" :to="{ name: 'live', params: { sessionId: g.session_id } }">观察直播</router-link>
              <router-link class="btn sm ghost" :to="{ name: 'review', params: { sessionId: g.session_id } }">看复盘</router-link>
            </td>
          </tr>
          <tr v-if="!patrol.groups?.length"><td colspan="6" class="muted">暂无声次</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, yuan } from '../api'

const classes = ref<Array<Record<string, any>>>([])
const classId = ref(0)
const report = ref<Record<string, any> | null>(null)
const patrol = ref<Record<string, any> | null>(null)
const error = ref('')

async function loadClasses() {
  error.value = ''
  try {
    classes.value = await api.classes.list()
    if (classes.value.length && !classId.value) classId.value = classes.value[0].id
    await loadDetail()
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

onMounted(loadClasses)
</script>

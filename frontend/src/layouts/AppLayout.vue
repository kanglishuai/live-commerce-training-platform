<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">直播运营实训平台</div>
      <nav>
        <router-link to="/" class="nav-item">任务与场次</router-link>
        <router-link v-if="auth.isTeacher" to="/classes" class="nav-item">班级与巡课</router-link>
        <router-link to="/agents" class="nav-item">AI 智能体</router-link>
      </nav>
      <div class="sidebar-foot muted">教学仿真数据 · 不连接真实支付</div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="muted">{{ roleLabel }}</div>
        <div class="spacer" />
        <span class="muted">{{ auth.user?.real_name || auth.user?.username }}</span>
        <button class="btn ghost sm" @click="onLogout">退出</button>
      </header>
      <div class="content">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const roleLabel = computed(() => {
  const map: Record<string, string> = { admin: '管理员', teacher: '教师', student: '学生' }
  return map[auth.user?.role || ''] || ''
})

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 208px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.brand { font-weight: 600; padding: 4px 8px; }
nav { display: flex; flex-direction: column; gap: 4px; }
.nav-item {
  padding: 9px 10px;
  border-radius: 6px;
  color: var(--text-dim);
}
.nav-item.router-link-exact-active,
.nav-item.router-link-active { background: var(--panel-2); color: var(--text); }
.sidebar-foot { margin-top: auto; padding: 0 8px; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
.content { padding: 20px; max-width: 1200px; width: 100%; }
</style>

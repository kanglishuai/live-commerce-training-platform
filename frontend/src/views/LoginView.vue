<template>
  <div class="login-wrap">
    <div class="card login-card">
      <h2 style="margin:0 0 4px">直播运营虚拟仿真实训平台</h2>
      <p class="muted" style="margin:0 0 18px">教学仿真数据 · 不连接真实支付</p>
      <form @submit.prevent="onSubmit">
        <label class="muted">账号</label>
        <input v-model="username" class="input" placeholder="请输入账号" autocomplete="username" />
        <label class="muted" style="display:block;margin-top:12px">口令</label>
        <input v-model="password" type="password" class="input" placeholder="请输入口令" autocomplete="current-password" />
        <p v-if="error" class="error" style="margin:12px 0 0">{{ error }}</p>
        <button class="btn" style="width:100%;margin-top:16px" :disabled="auth.loading">
          {{ auth.loading ? '登录中…' : '登 录' }}
        </button>
      </form>
      <div class="demo muted">
        <div>演示账号（种子数据）：</div>
        <div>管理员 admin / Admin@123</div>
        <div>教师 teacher_li / Teacher@123</div>
        <div>学生 stu_001 / Student@123</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const error = ref('')

async function onSubmit() {
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    router.push((route.query.redirect as string) || '/')
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>

<style scoped>
.login-wrap { min-height: 100vh; display: grid; place-items: center; }
.login-card { width: 380px; }
.demo { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; line-height: 1.7; }
</style>

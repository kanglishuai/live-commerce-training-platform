import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api'
import type { User } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value)
  const isStudent = computed(() => user.value?.role === 'student')
  const isTeacher = computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin')

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const data = await api.auth.login(username, password)
      token.value = data.token
      user.value = data.user
      localStorage.setItem('token', data.token)
      return data.user
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!token.value) return null
    user.value = await api.auth.me()
    return user.value
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, loading, isLoggedIn, isStudent, isTeacher, login, fetchMe, logout }
})

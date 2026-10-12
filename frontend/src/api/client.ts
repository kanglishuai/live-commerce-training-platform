import axios, { type AxiosInstance } from 'axios'

/** 统一后端访问：注入令牌、归一化错误（code/message/context 与 docs/API.md 一致） */
const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 20000
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const data = error.response?.data
    const status: number | undefined = error.response?.status
    const message: string = data?.message || error.message || '请求失败'
    const code: string = data?.code || 'NETWORK_ERROR'
    if (status === 401) {
      localStorage.removeItem('token')
      if (!location.pathname.startsWith('/login')) location.href = '/login'
    }
    const normalized = Object.assign(new Error(message), { code, status, context: data?.context })
    return Promise.reject(normalized)
  }
)

export default client

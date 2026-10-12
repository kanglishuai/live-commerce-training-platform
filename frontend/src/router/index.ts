import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('../layouts/AppLayout.vue'),
      children: [
        { path: '', name: 'home', component: () => import('../views/HomeView.vue') },
        { path: 'workbench/:sessionId', name: 'workbench', component: () => import('../views/WorkbenchView.vue') },
        { path: 'live/:sessionId', name: 'live', component: () => import('../views/LiveRoomView.vue') },
        { path: 'orders/:sessionId', name: 'orders', component: () => import('../views/OrdersView.vue') },
        { path: 'review/:sessionId', name: 'review', component: () => import('../views/ReviewView.vue') },
        { path: 'agents', name: 'agents', component: () => import('../views/AgentsView.vue') },
        {
          path: 'classes',
          name: 'classes',
          component: () => import('../views/ClassesView.vue'),
          meta: { roles: ['teacher', 'admin'] }
        }
      ]
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue'), meta: { public: true } }
  ]
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { name: 'login', query: { redirect: to.fullPath } }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { name: 'login' }
    }
  }
  const roles = (to.meta.roles as string[] | undefined) ?? null
  if (roles && auth.user && !roles.includes(auth.user.role)) return { name: 'home' }
  return true
})

export default router

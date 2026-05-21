import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import AntProxy from '@/views/AntProxy.vue'
import Dashboard from '@/views/Dashboard.vue'
import Logs from '@/views/Logs.vue'
import Login from '@/views/Login.vue'
import Nodes from '@/views/Nodes.vue'
import Rules from '@/views/Rules.vue'
import Settings from '@/views/Settings.vue'
import SmartProxies from '@/views/SmartProxies.vue'
import Subscriptions from '@/views/Subscriptions.vue'
import Templates from '@/views/Templates.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login },
    {
      path: '/',
      component: AppLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', component: Dashboard },
        { path: 'subscriptions', component: Subscriptions },
        { path: 'nodes', component: Nodes },
        { path: 'smart-proxies', component: SmartProxies },
        { path: 'ant-proxy', component: AntProxy },
        { path: 'rules', component: Rules },
        { path: 'templates', component: Templates },
        { path: 'settings', component: Settings },
        { path: 'logs', component: Logs },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.accessToken) return '/login'
  if (to.path === '/login' && auth.accessToken) return '/dashboard'
  return true
})

export default router

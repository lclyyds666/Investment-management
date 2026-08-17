import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getAlertCounts, listAlerts } from '@/api/legalRisk'
import { useUserStore } from '@/store/user'

export const useLegalAlertsStore = defineStore('legalAlerts', () => {
  const counts = ref({ total: 0, critical: 0, warning: 0 })
  const importantAlerts = ref([])
  const count = computed(() => counts.value.total || 0)
  let timer = null

  async function refresh() {
    if (!useUserStore().isLogin) return
    try {
      const [nextCounts, important] = await Promise.all([
        getAlertCounts(),
        listAlerts({ status: 'pending', level: 'critical', page: 1, page_size: 5 })
      ])
      counts.value = { total: 0, critical: 0, warning: 0, ...(nextCounts || {}) }
      importantAlerts.value = important?.items || []
    } catch {
      // 角标属于非关键路径，网络失败不打断当前工作。
    }
  }

  function startPolling(intervalMs = 30000) {
    stopPolling()
    refresh()
    timer = setInterval(refresh, intervalMs)
  }

  function stopPolling() {
    if (timer) clearInterval(timer)
    timer = null
  }

  function reset() {
    stopPolling()
    counts.value = { total: 0, critical: 0, warning: 0 }
    importantAlerts.value = []
  }

  return { counts, count, importantAlerts, refresh, startPolling, stopPolling, reset }
})

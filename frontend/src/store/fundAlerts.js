import { defineStore } from 'pinia'
import { ref } from 'vue'
import { acknowledgeTodayFundAlerts, getTodayFundAlerts } from '@/api/fund'

export const useFundAlertStore = defineStore('fundAlerts', () => {
  const items = ref([])
  const visible = ref(false)
  const loading = ref(false)
  let loadedForSession = false
  let inFlight = null
  let sessionVersion = 0

  function loadForLogin() {
    if (loadedForSession) return Promise.resolve()
    if (inFlight) return inFlight
    const requestVersion = sessionVersion
    loading.value = true
    inFlight = getTodayFundAlerts()
      .then((result) => {
        if (requestVersion !== sessionVersion) return
        loadedForSession = true
        items.value = result?.items || []
        visible.value = items.value.length > 0
      })
      .catch(() => undefined)
      .finally(() => {
        if (requestVersion !== sessionVersion) return
        loading.value = false
        inFlight = null
      })
    return inFlight
  }

  async function acknowledgeShown() {
    const shown = items.value.map(item => ({ fund_id: item.id, stage: item.stage }))
    if (shown.length) await acknowledgeTodayFundAlerts(shown)
  }

  function reset() {
    sessionVersion += 1
    loadedForSession = false
    inFlight = null
    items.value = []
    visible.value = false
    loading.value = false
  }

  return { items, visible, loading, loadForLogin, acknowledgeShown, reset }
})

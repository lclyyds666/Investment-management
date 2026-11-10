import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getWorkItems } from '@/api/workItems'

export const useWorkItemsStore = defineStore('workItems', () => {
  const items = ref([])
  const loading = ref(false)
  const error = ref(false)
  const count = computed(() => items.value.length)
  let timer = null
  let version = 0
  let session = ''
  let pending = null

  function load() {
    if (!session) return Promise.resolve()
    if (pending) return pending
    const requestVersion = version
    loading.value = true
    pending = getWorkItems().then((rows) => {
      if (requestVersion !== version) return
      items.value = Array.isArray(rows) ? rows : []
      error.value = false
    }).catch(() => {
      if (requestVersion !== version) return
      error.value = true
      items.value = []
    }).finally(() => {
      if (requestVersion !== version) return
      pending = null
      loading.value = false
    })
    return pending
  }

  function stopPolling() {
    if (timer) clearInterval(timer)
    timer = null
  }
  function reset() {
    stopPolling()
    version += 1
    session = ''
    pending = null
    items.value = []
    loading.value = false
    error.value = false
  }
  function startPolling(token) {
    if (!token) { reset(); return }
    if (session !== token) { reset(); session = token }
    stopPolling()
    void load()
    timer = setInterval(() => { void load() }, 30000)
  }
  return { items, count, loading, error, load, startPolling, stopPolling, reset }
})

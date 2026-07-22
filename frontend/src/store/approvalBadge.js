import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPendingCount } from '@/api/approval'
import { useUserStore } from '@/store/user'

/**
 * 审批角标 store：按当前登录用户角色统计「待我处理」的审批数量，
 * 供侧边栏在「合同管理」「业务审批」及其分组上渲染 Badge。
 *
 * 刷新策略：登录后启动 30s 轮询；切换用户/审批完成后主动 refresh() 实时刷新。
 * 后端接口 /approval/pending-count 返回 { contract, business, total }。
 */
export const useApprovalBadgeStore = defineStore('approvalBadge', () => {
  const contract = ref(0)   // 合同(法律)类·待我审批
  const business = ref(0)   // 业务审批单·待我审批
  const total = computed(() => contract.value + business.value)

  let timer = null

  async function refresh() {
    const userStore = useUserStore()
    if (!userStore.isLogin) return
    try {
      const res = await getPendingCount()
      contract.value = res?.contract || 0
      business.value = res?.business || 0
    } catch {
      // 静默失败：角标非关键路径，不打断用户操作
    }
  }

  /** 启动轮询（幂等：重复调用只保留一个定时器）；立即拉一次。 */
  function startPolling(intervalMs = 30000) {
    stopPolling()
    refresh()
    timer = setInterval(refresh, intervalMs)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  /** 退出登录时清零并停轮询。 */
  function reset() {
    stopPolling()
    contract.value = 0
    business.value = 0
  }

  return { contract, business, total, refresh, startPolling, stopPolling, reset }
})

<template>
  <section class="dashboard-page" v-loading="loading">
    <header class="dashboard-header">
      <div><span>LEGAL RISK DESK</span><h1>法务工作台</h1><p>{{ today }} 案件进度、回款与期限任务</p></div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </header>

    <div class="metric-grid">
      <button v-for="item in metrics" :key="item.key" class="metric" type="button" @click="drill(item)">
        <span>{{ item.label }}</span><strong>{{ item.money ? `¥ ${money(item.value)}` : item.value }}</strong><small>{{ item.note }}</small>
      </button>
    </div>

    <div class="dashboard-grid">
      <section class="work-panel">
        <header><div><h2>近期期限</h2><span>未来 45 天</span></div><el-button link type="primary" @click="$router.push('/investment/legal-risk/alerts')">全部预警</el-button></header>
        <el-table :data="stats.upcoming_deadlines" size="small">
          <el-table-column prop="title" label="事项" min-width="160" show-overflow-tooltip />
          <el-table-column label="类型" width="110"><template #default="{ row }">{{ deadlineTypeLabel(row.deadline_type) }}</template></el-table-column>
          <el-table-column prop="event_date" label="日期" width="110" />
          <el-table-column label="剩余" width="82" align="right"><template #default="{ row }"><span :class="{ urgent: row.remaining_days <= 7 }">{{ row.remaining_days }} 天</span></template></el-table-column>
          <el-table-column width="60"><template #default="{ row }"><el-button link type="primary" @click="openCase(row.case_id)">查看</el-button></template></el-table-column>
        </el-table>
        <el-empty v-if="!stats.upcoming_deadlines?.length" description="未来 45 天无待办期限" :image-size="70" />
      </section>

      <section class="work-panel">
        <header><div><h2>资产保全到期</h2><span>未来 45 天</span></div></header>
        <el-table :data="stats.upcoming_assets" size="small">
          <el-table-column prop="asset_name" label="资产" min-width="180" show-overflow-tooltip />
          <el-table-column prop="expiry_date" label="到期日" width="110" />
          <el-table-column label="剩余" width="82" align="right"><template #default="{ row }"><span :class="{ urgent: row.remaining_days <= 7 }">{{ row.remaining_days }} 天</span></template></el-table-column>
          <el-table-column width="60"><template #default="{ row }"><el-button link type="primary" @click="openCase(row.case_id)">查看</el-button></template></el-table-column>
        </el-table>
        <el-empty v-if="!stats.upcoming_assets?.length" description="未来 45 天无资产到期" :image-size="70" />
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getDashboardStatistics } from '@/api/legalRisk'
import { deadlineTypeLabel, money } from '@/constants/legalRisk'

const router = useRouter()
const loading = ref(false)
const stats = reactive({ upcoming_deadlines: [], upcoming_assets: [] })
const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })
const metrics = computed(() => [
  { key: 'case_count', label: '正式案件', value: stats.case_count || 0, note: '当前案件总量' },
  { key: 'review_filing_count', label: '审查立案', value: stats.review_filing_count || 0, note: '正在审查建档', status: 'review_filing' },
  { key: 'recovered_amount', label: '累计回款', value: stats.recovered_amount || 0, note: '已登记清收金额', money: true },
  { key: 'outstanding_amount', label: '待回款', value: stats.outstanding_amount || 0, note: '按当前执行依据', money: true },
  { key: 'active_alert_count', label: '活动预警', value: stats.active_alert_count || 0, note: '待处理与处理中', alerts: true },
  { key: 'upcoming_asset_count', label: '资产到期', value: stats.upcoming_asset_count || 0, note: '未来 45 天' }
])

async function load() {
  loading.value = true
  try { Object.assign(stats, await getDashboardStatistics()) } finally { loading.value = false }
}
function drill(item) {
  if (item.alerts) return router.push('/investment/legal-risk/alerts')
  router.push({ path: '/investment/legal-risk/cases', query: item.status ? { status: item.status } : {} })
}
const openCase = (id) => router.push(`/investment/legal-risk/cases/${id}`)
onMounted(load)
</script>

<style scoped>
.dashboard-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 18px; padding: 4px 0 16px 16px; border-bottom: 1px solid var(--el-border-color-lighter); border-left: 4px solid var(--brand-vermilion); }
.dashboard-header span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; letter-spacing: 0; }
.dashboard-header h1 { margin: 4px 0; font-size: 25px; letter-spacing: 0; }
.dashboard-header p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 16px; border-top: 1px solid var(--el-border-color-lighter); border-left: 1px solid var(--el-border-color-lighter); }
.metric { display: flex; min-width: 0; min-height: 122px; padding: 18px; flex-direction: column; align-items: flex-start; border: 0; border-right: 1px solid var(--el-border-color-lighter); border-bottom: 1px solid var(--el-border-color-lighter); color: inherit; background: var(--surface-solid); text-align: left; cursor: pointer; }
.metric:hover { background: var(--surface-hover); }
.metric span { color: var(--el-text-color-secondary); font-size: 13px; }
.metric strong { max-width: 100%; margin-top: 10px; overflow: hidden; text-overflow: ellipsis; font-family: var(--font-data); font-size: 25px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.metric small { margin-top: auto; color: var(--el-text-color-placeholder); }
.dashboard-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.work-panel { min-width: 0; padding: 18px; border: 1px solid var(--el-border-color-lighter); border-left: 3px solid var(--divider-rail); background: var(--surface-solid); }
.work-panel > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.work-panel h2 { margin: 0; font-size: 16px; letter-spacing: 0; }
.work-panel header span { color: var(--el-text-color-secondary); font-size: 12px; }
.urgent { color: var(--el-color-danger); font-weight: 700; }
@media (max-width: 980px) { .dashboard-grid { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .metric strong { font-size: 20px; } }
</style>

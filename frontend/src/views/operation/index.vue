<template>
  <div class="operation" v-loading="loading">
    <header class="page-intro">
      <div>
        <p class="page-eyebrow">TRAVEL LEDGER INSIGHTS</p>
        <h1 class="page-title">经营数据中心</h1>
        <p class="page-subtitle">所有指标均由文旅门票与酒店台账实时汇总，金额、期次和景区维度保持同源。</p>
      </div>
    </header>

    <el-row :gutter="16" class="kpi-row">
      <el-col v-for="kpi in kpiCards" :key="kpi.label" :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover" class="kpi-card" :class="`is-${kpi.tone}`">
          <div class="kpi-label">{{ kpi.label }}</div>
          <div class="kpi-value">{{ kpi.value }}</div>
          <div class="kpi-foot">{{ kpi.hint }}</div>
        </el-card>
      </el-col>
    </el-row>

    <div class="chart-filters mt">
      <div class="filter-title">图表筛选</div>
      <el-select v-model="selectedYear" placeholder="年份" clearable class="filter-control">
        <el-option v-for="year in yearOptions" :key="year" :label="`${year}年`" :value="year" />
      </el-select>
      <el-select
        v-model="selectedScenicIds" multiple collapse-tags collapse-tags-tooltip
        placeholder="全部景区 ID" class="filter-control scenic-filter"
      >
        <el-option
          v-for="item in scenicOptions" :key="item.id"
          :label="`${item.name} (${item.id})`" :value="item.id"
        />
      </el-select>
    </div>

    <el-row :gutter="16" class="mt chart-row">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <div class="chart-header">
              <span class="card-title">业务毛利润</span>
              <span class="chart-subtitle">各景区每期门票/酒店服务费</span>
            </div>
          </template>
          <BaseChart :option="barOption" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="chart-card pie-card">
          <template #header>
            <div class="pie-header">
              <div class="chart-header">
                <span class="card-title">毛利润占比</span>
                <span class="chart-subtitle">门票/酒店独立拆分</span>
              </div>
              <div class="pie-filters">
                <el-select v-model="selectedMonth" clearable placeholder="全部月份" class="small-filter">
                  <el-option v-for="month in monthOptions" :key="month" :label="`${month}月`" :value="month" />
                </el-select>
                <el-select v-model="selectedPeriod" clearable placeholder="全部期次" class="period-filter">
                  <el-option
                    v-for="item in periodOptions" :key="item.key"
                    :label="item.label" :value="item.key"
                  />
                </el-select>
              </div>
            </div>
          </template>
          <BaseChart :option="pieOption" />
        </el-card>
      </el-col>
    </el-row>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import BaseChart from '@/components/BaseChart.vue'
import { getFinancial } from '@/api/operation'
import { getScenicById } from '@/constants/scenic'
import { getScenicColor } from '@/utils/scenicColors'
import { chartVisualTokens } from '@/utils/visualTokens'

const loading = ref(false)
const selectedYear = ref('')
const selectedScenicIds = ref([])
const selectedMonth = ref('')
const selectedPeriod = ref('')
const dash = ref({
  existing_scale: 0, total_realized_scale: 0, total_gross_income: 0,
  capital_occupation_days: null, ledger_profit: [],
  available_years: [], scenic_ids: []
})

const yuan = (v) => '¥' + Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const yearOptions = computed(() => dash.value.available_years || [])
const scenicOptions = computed(() => (dash.value.scenic_ids || []).map((id) => ({
  id,
  name: getScenicById(id)?.name || id
})))

function scenicName(id) {
  return getScenicById(id)?.name || id
}

function seriesKey(point) {
  return `${point.scenic_id}:${point.business_type}`
}

function seriesLabel(key) {
  const separator = key.lastIndexOf(':')
  const id = key.slice(0, separator)
  const type = key.slice(separator + 1)
  return `${scenicName(id)}-${type === 'hotel' ? '酒店' : '门票'}`
}

function matchesSharedFilters(point) {
  const yearMatched = !selectedYear.value || Number(point.year) === Number(selectedYear.value)
  const scenicMatched = !selectedScenicIds.value.length || selectedScenicIds.value.includes(point.scenic_id)
  return yearMatched && scenicMatched
}

const sharedFilteredPoints = computed(() => (dash.value.ledger_profit || []).filter(matchesSharedFilters))
const monthOptions = computed(() => [...new Set(
  sharedFilteredPoints.value.map((item) => item.month).filter((value) => value != null)
)].sort((a, b) => a - b))
const monthFilteredPoints = computed(() => sharedFilteredPoints.value.filter(
  (item) => !selectedMonth.value || Number(item.month) === Number(selectedMonth.value)
))
const periodOptions = computed(() => {
  const periods = new Map()
  for (const item of monthFilteredPoints.value) {
    if (!periods.has(item.period_key)) periods.set(item.period_key, item.period)
  }
  return [...periods.entries()].map(([key, label]) => ({ key, label }))
})
const pieFilteredPoints = computed(() => monthFilteredPoints.value.filter(
  (item) => !selectedPeriod.value || item.period_key === selectedPeriod.value
))

watch([selectedYear, selectedScenicIds, selectedMonth], () => {
  selectedPeriod.value = ''
}, { deep: true })

const kpiCards = computed(() => {
  const d = dash.value
  return [
    { label: '已投入业务规模', value: yuan(d.existing_scale), tone: 'invested', hint: '门票及酒店付款金额减跟投金额；酒店同期只计一次' },
    { label: '已实现业务规模', value: yuan(d.total_realized_scale), tone: 'realized', hint: '所有景区门票及酒店销售额合计' },
    { label: '已实现业务毛利润', value: yuan(d.total_gross_income), tone: 'profit', hint: '所有景区门票及酒店服务费合计' },
    { label: '资金占用时长', value: d.capital_occupation_days != null ? d.capital_occupation_days + ' 天' : '—', tone: 'duration', hint: '按净投入金额加权的平均占用天数' }
  ]
})

function emptyGraphic(show) {
  return show ? [{
    type: 'text', left: 'center', top: 'middle',
    style: { text: '暂无服务费数据', fill: chartVisualTokens.emptyText, fontSize: 14 }
  }] : []
}

const barOption = computed(() => {
  const points = sharedFilteredPoints.value
  const periods = new Map()
  const keys = new Set()
  for (const item of points) {
    if (!periods.has(item.period_key)) periods.set(item.period_key, { label: item.period, values: new Map() })
    const key = seriesKey(item)
    keys.add(key)
    const values = periods.get(item.period_key).values
    values.set(key, (values.get(key) || 0) + Number(item.service_fee || 0))
  }
  const periodList = [...periods.entries()]
  const seriesKeys = [...keys].sort((a, b) => seriesLabel(a).localeCompare(seriesLabel(b), 'zh-CN'))
  return {
    color: seriesKeys.map((key) => {
      const [id, type] = key.split(':')
      return getScenicColor(id, type)
    }),
    tooltip: { trigger: 'axis', valueFormatter: (value) => yuan(value) },
    legend: { type: 'scroll', top: 0, data: seriesKeys.map(seriesLabel) },
    grid: { left: 76, right: 24, top: 58, bottom: periodList.length > 6 ? 92 : 70 },
    xAxis: {
      type: 'category',
      data: periodList.map(([, value]) => value.label),
      axisLabel: { interval: 0, rotate: periodList.length > 5 ? 28 : 0, width: 120, overflow: 'truncate' }
    },
    yAxis: { type: 'value', name: '服务费(元)', axisLabel: { formatter: (value) => Number(value).toLocaleString('zh-CN') } },
    dataZoom: periodList.length > 10 ? [{ type: 'slider', height: 18, bottom: 10 }, { type: 'inside' }] : [],
    graphic: emptyGraphic(!points.length),
    series: seriesKeys.map((key) => {
      const [id, type] = key.split(':')
      return {
        name: seriesLabel(key), type: 'bar', barMaxWidth: 30,
        itemStyle: { color: getScenicColor(id, type) },
        data: periodList.map(([, value]) => value.values.get(key) || 0)
      }
    })
  }
})

const pieOption = computed(() => {
  const sums = new Map()
  for (const item of pieFilteredPoints.value) {
    const key = seriesKey(item)
    sums.set(key, (sums.get(key) || 0) + Number(item.service_fee || 0))
  }
  const data = [...sums.entries()]
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => {
      const [id, type] = key.split(':')
      return { name: seriesLabel(key), value, itemStyle: { color: getScenicColor(id, type) } }
    })
  return {
    tooltip: { trigger: 'item', formatter: (params) => `${params.name}<br/>${yuan(params.value)} (${params.percent}%)` },
    legend: { type: 'scroll', bottom: 0 },
    graphic: emptyGraphic(!data.length),
    series: [{
      name: '业务毛利润占比', type: 'pie', radius: ['42%', '68%'], center: ['50%', '43%'],
      itemStyle: { borderColor: 'transparent', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%' },
      data
    }]
  }
})

async function load() {
  loading.value = true
  try {
    dash.value = await getFinancial()
    if (!selectedYear.value && dash.value.available_years?.length) {
      selectedYear.value = dash.value.available_years[0]
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.operation {
  .kpi-row { margin-bottom: 6px; row-gap: 16px; }
  .kpi-card {
    height: 100%;
    --kpi-color: var(--metric-invested);
    &.is-realized { --kpi-color: var(--metric-realized); }
    &.is-profit { --kpi-color: var(--metric-profit); }
    &.is-duration { --kpi-color: var(--metric-duration); }
    :deep(.el-card__body) { min-height: 170px; display: flex; flex-direction: column; }
    .kpi-label { color: var(--el-text-color-secondary); font-size: 13px; font-weight: 650; letter-spacing: .02em; }
    .kpi-value { margin-top: 14px; color: var(--kpi-color); font-size: clamp(25px, 2vw, 34px); font-weight: 800; line-height: 1.1; overflow-wrap: anywhere; }
    .kpi-foot { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--el-border-color-extra-light); font-size: 12px; line-height: 1.55; color: var(--el-text-color-placeholder); min-height: 50px; }
  }
  .mt { margin-top: 20px; }
  .card-title { font-family: var(--font-display); font-weight: 750; }
  .chart-filters {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 14px 16px; border: 1px solid var(--surface-border); border-radius: var(--radius-md); background: var(--surface); box-shadow: var(--surface-shadow);
  }
  .filter-title { font-size: 14px; font-weight: 700; margin-right: 4px; }
  .filter-control { width: 140px; }
  .scenic-filter { width: min(420px, 100%); }
  .chart-row { row-gap: 16px; }
  .chart-card { min-height: 460px; height: 100%; }
  .chart-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .chart-subtitle { color: var(--el-text-color-secondary); font-size: 12px; }
  .pie-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .pie-filters { display: flex; gap: 8px; flex-wrap: wrap; }
  .small-filter { width: 110px; }
  .period-filter { width: 180px; }
}

@media (max-width: 768px) {
  .operation {
    .filter-control, .scenic-filter { width: 100%; }
    .pie-filters { width: 100%; }
    .small-filter, .period-filter { flex: 1 1 140px; }
  }
}
</style>

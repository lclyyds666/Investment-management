<template>
  <div class="operation" v-loading="loading">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="tb-left">
          <span class="tb-title">经营数据 · 文旅台账经营指标</span>
          <el-tag v-if="hasLedgerData" type="success" effect="plain" size="small">台账数据实时汇总</el-tag>
          <el-tag v-else type="info" effect="plain" size="small">暂无门票或酒店台账数据</el-tag>
        </div>
        <div class="tb-right">
          <span class="cost-label">可用资金(元)</span>
          <el-input-number
            v-model="availableFunds" :min="0" :step="1000000" :controls="false"
            style="width: 170px" size="default"
          />
          <el-button size="default" :loading="savingFunds" @click="saveFunds">保存</el-button>
          <el-upload
            action="#" :auto-upload="false" :show-file-list="false"
            accept=".xlsx,.xlsm" :on-change="onUploadProjects"
          >
            <el-button type="primary" :icon="UploadFilled" :loading="uploading">上传项目统计表(xlsx)</el-button>
          </el-upload>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="kpi-row">
      <el-col v-for="kpi in kpiCards" :key="kpi.label" :xs="24" :sm="12" :lg="8">
        <el-card shadow="hover" class="kpi-card" :style="{ borderTopColor: kpi.color }">
          <div class="kpi-label">{{ kpi.label }}</div>
          <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
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
      <el-col :xs="24" :xl="14">
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
      <el-col :xs="24" :xl="10">
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

    <el-card shadow="never" class="mt">
      <template #header><span class="card-title">历史项目统计明细（独立数据源）</span></template>
      <el-table :data="dash.projects" border stripe>
        <el-table-column prop="seq" label="#" width="50" align="center" />
        <el-table-column prop="project_name" label="项目" min-width="160" />
        <el-table-column prop="platforms" label="平台" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="p in splitPlatforms(row.platforms)" :key="p" size="small" class="pf-tag">{{ p }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="投入金额" min-width="130" align="right">
          <template #default="{ row }">{{ yuan(row.invested_amount) }}</template>
        </el-table-column>
        <el-table-column label="已回款" min-width="130" align="right">
          <template #default="{ row }">{{ yuan(row.realized_scale) }}</template>
        </el-table-column>
        <el-table-column label="实现毛利" min-width="120" align="right">
          <template #default="{ row }"><span class="income">{{ yuan(row.gross_profit) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率" width="90" align="right">
          <template #default="{ row }">{{ row.profit_rate != null ? (row.profit_rate * 100).toFixed(2) + '%' : '—' }}</template>
        </el-table-column>
        <el-table-column label="投入与回款差额" min-width="130" align="right">
          <template #default="{ row }"><span class="occ">{{ yuan(row.capital_occupied) }}</span></template>
        </el-table-column>
        <el-table-column prop="pay_date" label="付款日期" width="120" align="center" />
      </el-table>
      <el-empty v-if="!dash.projects.length" description="暂无独立项目统计数据" />
    </el-card>

    <el-card shadow="never" class="mt" v-if="dash.platforms && dash.platforms.length">
      <template #header><span class="card-title">平台对账单回款明细（独立数据源）</span></template>
      <el-table :data="dash.platforms" border stripe size="small">
        <el-table-column label="平台" width="110">
          <template #default="{ row }"><el-tag effect="dark" size="small">{{ row.platform_label }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="period" label="账期" min-width="150" />
        <el-table-column label="已实现业务规模" align="right" min-width="150">
          <template #default="{ row }">{{ yuan(row.realized_scale) }}</template>
        </el-table-column>
        <el-table-column label="毛收入(回款)" align="right" min-width="150">
          <template #default="{ row }">{{ yuan(row.gross_income) }}</template>
        </el-table-column>
        <el-table-column prop="order_count" label="订单" width="80" align="right" />
      </el-table>
    </el-card>

    <AiBrainPanel />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import BaseChart from '@/components/BaseChart.vue'
import AiBrainPanel from '@/components/AiBrainPanel.vue'
import { getFinancial, uploadProjects, setAvailableFunds } from '@/api/operation'
import { getScenicById } from '@/constants/scenic'
import { getScenicColor } from '@/utils/scenicColors'

const loading = ref(false)
const uploading = ref(false)
const savingFunds = ref(false)
const availableFunds = ref(0)
const selectedYear = ref('')
const selectedScenicIds = ref([])
const selectedMonth = ref('')
const selectedPeriod = ref('')
const dash = ref({
  existing_scale: 0, total_realized_scale: 0, total_gross_income: 0,
  profit_rate: null, capital_occupation_days: null, capital_occupied: 0,
  available_funds: 0, projects: [], platforms: [], ledger_profit: [],
  available_years: [], scenic_ids: []
})

const yuan = (v) => '¥' + Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const splitPlatforms = (s) => String(s || '').replace(/，/g, ',').replace(/、/g, ',').split(',').map((x) => x.trim()).filter(Boolean)
const hasLedgerData = computed(() => dash.value.ledger_profit.length > 0)
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
    { label: '已投入业务规模', value: yuan(d.existing_scale), color: '#4b5563', hint: '门票及酒店付款金额减跟投金额；酒店同期只计一次' },
    { label: '已实现业务规模', value: yuan(d.total_realized_scale), color: '#2563eb', hint: '所有景区门票及酒店销售额合计' },
    { label: '已实现业务毛利润', value: yuan(d.total_gross_income), color: '#15803d', hint: '所有景区门票及酒店服务费合计' },
    { label: '业务收益率', value: d.profit_rate != null ? d.profit_rate + '%' : '—', color: '#b45309', hint: '业务毛利润 ÷ 已投入业务规模' },
    { label: '资金占用时长', value: d.capital_occupation_days != null ? d.capital_occupation_days + ' 天' : '—', color: '#be123c', hint: '按净投入金额加权的平均占用天数' },
    { label: '可用资金', value: Number(d.available_funds) > 0 ? yuan(d.available_funds) : '—', color: '#0f766e', hint: '手工录入资金余额' }
  ]
})

function emptyGraphic(show) {
  return show ? [{
    type: 'text', left: 'center', top: 'middle',
    style: { text: '暂无服务费数据', fill: '#909399', fontSize: 14 }
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
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%' },
      data
    }]
  }
})

async function load() {
  loading.value = true
  try {
    dash.value = await getFinancial()
    availableFunds.value = Number(dash.value.available_funds || 0)
    if (!selectedYear.value && dash.value.available_years?.length) {
      selectedYear.value = dash.value.available_years[0]
    }
  } finally {
    loading.value = false
  }
}

async function saveFunds() {
  savingFunds.value = true
  try {
    dash.value = await setAvailableFunds(availableFunds.value)
    availableFunds.value = Number(dash.value.available_funds || 0)
    ElMessage.success('可用资金已更新')
  } finally {
    savingFunds.value = false
  }
}

async function onUploadProjects(file) {
  const raw = file.raw
  if (!raw) return
  uploading.value = true
  try {
    const res = await uploadProjects(raw)
    ElMessage.success(`已导入 ${res.imported} 个项目，投入合计 ${yuan(res.total_invested)}，回款 ${yuan(res.total_realized)}`)
    await load()
  } catch {
    // 错误消息由请求拦截器统一提示。
  } finally {
    uploading.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.operation {
  .toolbar-card { margin-bottom: 16px; :deep(.el-card__body) { padding: 14px 18px; } }
  .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .tb-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .tb-title { font-size: 16px; font-weight: 700; color: var(--el-text-color-primary); }
  .tb-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .cost-label { color: var(--el-text-color-regular); font-size: 13px; }

  .kpi-row { margin-bottom: 4px; row-gap: 16px; }
  .kpi-card {
    border-top: 3px solid var(--el-border-color);
    transition: box-shadow .3s ease, transform .3s ease;
    &:hover { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(31,41,55,.12) !important; }
    .kpi-label { color: var(--el-text-color-secondary); font-size: 14px; }
    .kpi-value { margin-top: 8px; font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; }
    .kpi-foot { margin-top: 6px; font-size: 12px; color: var(--el-text-color-placeholder); min-height: 32px; }
  }
  .mt { margin-top: 16px; }
  .card-title { font-weight: 700; }
  .chart-filters {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter); border-bottom: 1px solid var(--el-border-color-lighter);
  }
  .filter-title { font-size: 14px; font-weight: 700; margin-right: 4px; }
  .filter-control { width: 140px; }
  .scenic-filter { width: min(420px, 100%); }
  .chart-row { row-gap: 16px; }
  .chart-card { min-height: 460px; }
  .chart-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .chart-subtitle { color: var(--el-text-color-secondary); font-size: 12px; }
  .pie-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .pie-filters { display: flex; gap: 8px; flex-wrap: wrap; }
  .small-filter { width: 110px; }
  .period-filter { width: 180px; }
  .income { color: #15803d; font-weight: 700; }
  .occ { color: #be123c; font-weight: 600; }
  .pf-tag { margin: 0 4px 2px 0; }
}

@media (max-width: 768px) {
  .operation {
    .tb-right { width: 100%; }
    .filter-control, .scenic-filter { width: 100%; }
    .pie-filters { width: 100%; }
    .small-filter, .period-filter { flex: 1 1 140px; }
  }
}
</style>

<template>
  <div class="operation-analysis">
    <header class="page-intro">
      <p class="page-eyebrow">OPERATION INTELLIGENCE</p>
      <h1 class="page-title">分析预测</h1>
      <p class="page-subtitle">
        基于已确认台账分析经营表现，结合人工影响因素进行区间预测。金额单位：万元。
      </p>
    </header>
    <el-tabs v-model="activeTab"
      ><el-tab-pane label="经营情况分析" name="analysis" /><el-tab-pane
        label="数据 AI 预测"
        name="forecast"
    /></el-tabs>
    <section class="filters" aria-label="统一筛选">
      <template v-if="activeTab === 'forecast'">
        <el-radio-group v-model="forecastPeriodMode" aria-label="预测周期类型">
          <el-radio-button value="month">按月</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-if="forecastPeriodMode === 'month'"
          v-model="forecastMonth"
          type="month"
          value-format="YYYY-MM"
          placeholder="选择预测月份"
          @change="selectForecastMonth"
        />
      </template>
      <el-date-picker
        v-if="activeTab === 'analysis' || forecastPeriodMode === 'custom'"
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
      />
      <el-select
        v-model="scenicIds"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="全部景区"
        aria-label="景区"
        ><el-option
          v-for="s in scenicSpots"
          :key="s.id"
          :label="s.name"
          :value="s.id"
      /></el-select>
      <el-select
        v-model="businessTypes"
        multiple
        placeholder="全部业务"
        aria-label="业务"
        ><el-option label="门票" value="ticket" /><el-option
          label="酒店"
          value="hotel"
      /></el-select>
      <el-select
        v-model="platforms"
        multiple
        filterable
        placeholder="全部已观测平台"
        aria-label="平台"
        ><el-option v-for="p in platformOptions" :key="p" :label="p" :value="p"
      /></el-select>
      <el-button
        v-if="activeTab === 'analysis'"
        type="primary"
        :loading="loading"
        @click="loadAnalysis"
        >查询分析</el-button
      >
    </section>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <section
      v-if="activeTab === 'analysis'"
      v-loading="loading"
      aria-label="经营情况分析"
    >
      <template v-if="analysis">
        <div class="metrics">
          <el-card v-for="m in metrics" :key="m.key" shadow="never"
            ><div class="muted">{{ m.label }}</div>
            <strong>{{ display(analysis.summary[m.key], m.key) }}</strong>
            <p class="muted">
              同比 {{ rate(analysis.comparisons[m.comparison]?.yoy_rate) }} ·
              环比 {{ rate(analysis.comparisons[m.comparison]?.mom_rate) }}
            </p></el-card
          >
        </div>
        <el-empty
          v-if="!analysis.rankings.length"
          description="当前范围暂无已确认经营数据，请调整筛选或确认台账。"
        />
        <el-card shadow="never"
          ><template #header>经营趋势</template
          ><BaseChart :option="analysisChart"
        /></el-card>
        <div class="columns">
          <el-card shadow="never"
            ><template #header>结算排名与占比</template
            ><el-table :data="analysis.rankings" empty-text="暂无排名"
              ><el-table-column label="维度"
                ><template #default="{ row }"
                  >{{ dimensionNames[row.dimension] }} /
                  {{ label(row.value) }}</template
                ></el-table-column
              ><el-table-column label="结算（万元）"
                ><template #default="{ row }">{{
                  display(row.summary.settlement_amount)
                }}</template></el-table-column
              ><el-table-column label="占比"
                ><template #default="{ row }">{{
                  rate(row.settlement_share)
                }}</template></el-table-column
              ></el-table
            ></el-card
          >
          <el-card shadow="never"
            ><template #header>环比贡献</template
            ><el-table :data="analysis.contributions" empty-text="暂无贡献数据"
              ><el-table-column label="维度"
                ><template #default="{ row }"
                  >{{ dimensionNames[row.dimension] }} /
                  {{ label(row.value) }}</template
                ></el-table-column
              ><el-table-column label="结算增减（万元）"
                ><template #default="{ row }">{{
                  display(row.settlement_change)
                }}</template></el-table-column
              ><el-table-column label="贡献率"
                ><template #default="{ row }">{{
                  rate(row.contribution_rate)
                }}</template></el-table-column
              ></el-table
            ></el-card
          >
        </div>
        <el-card shadow="never"
          ><template #header>异常与经营洞察</template>
          <p class="muted">
            环比对比前一等长周期；同比对比去年同期。基数为零时不计算变化率。
          </p>
          <p v-if="!analysis.anomalies.length">未发现达到规则阈值的异常。</p>
          <p v-for="(a, i) in analysis.anomalies" :key="i">
            {{ metricName(a.metric) }}：{{
              a.severity === 'critical' ? '重点关注' : '关注'
            }}，{{
              a.rule === 'mom_change'
                ? `环比变化 ${rate(a.evidence)}`
                : `偏离历史均值 ${a.evidence} 个标准差`
            }}；当前 {{ display(a.current, a.metric) }}，基准
            {{ display(a.baseline, a.metric) }}。
          </p></el-card
        > </template
      ><el-empty v-else-if="!loading" description="选择时间和维度后查询分析" />
    </section>
    <section v-else v-loading="forecastLoading" aria-label="数据 AI 预测">
      <el-card shadow="never"
        ><template #header>预测周期与影响因素</template>
        <p class="muted">
          上方时间为预测周期，最多 90 天。影响比例 0.1 表示增加
          10%；仅使用手工维护或 Excel 导入因素。
        </p>
        <ForecastFactorEditor v-if="canEditFactors" v-model="factors" />
        <p v-else class="muted">当前账号没有影响因素编辑权限。</p>
        <div class="actions">
          <el-button
            v-if="canForecast"
            type="primary"
            :loading="forecastLoading"
            @click="generateForecast"
            >生成预测</el-button
          ><el-button
            v-if="canExport"
            :loading="exporting"
            @click="exportForecast"
            >导出预测 Excel</el-button
          >
        </div>
        <p v-if="!canForecast" class="muted">
          当前账号没有生成预测权限。
        </p></el-card
      >
      <template v-if="forecastResult"
        ><p class="muted">
          本次结果周期：{{ forecastResult.start_date }} 至
          {{
            forecastResult.end_date
          }}；修改条件后请重新生成。汇总仅包含可计算分层。
        </p>
        <div class="metrics forecast-metrics">
          <el-card v-for="m in forecastMetrics" :key="m.key" shadow="never"
            ><div class="muted">预测{{ m.label }}</div>
            <strong>{{
              m.value == null ? '数据不足' : display(m.value, m.key)
            }}</strong>
            <p>
              区间 {{ m.low == null ? '—' : display(m.low, m.key) }} ~
              {{ m.high == null ? '—' : display(m.high, m.key) }}
            </p>
            <p class="muted">{{ m.missing }} 个分层数据不足</p></el-card
          >
        </div>
        <el-card shadow="never"
          ><template #header>历史与预测区间</template
          ><el-select v-model="chartMetric" aria-label="趋势指标"
            ><el-option
              v-for="m in metrics.slice(0, 3)"
              :key="m.key"
              :label="m.label"
              :value="m.key"
          /></el-select>
          <p class="muted">
            历史按预测周期等长分段汇总；最后一段为整个预测周期总量，阴影为预测区间，不代表逐日预测。
          </p>
          <el-alert
            v-if="historyError"
            :title="historyError"
            type="warning"
            :closable="false" />
          <BaseChart :option="forecastChart"
        /></el-card>
        <el-card shadow="never"
          ><template #header
            >预测解释 ·
            {{
              forecastResult.insights.engine === 'deepseek' ? 'AI' : '规则'
            }}</template
          >
          <p>{{ forecastResult.insights.summary }}</p>
          <p v-for="r in forecastResult.insights.recommendations" :key="r">
            {{ r }}
          </p></el-card
        >
        <el-card shadow="never"
          ><template #header>分层明细与置信度</template
          ><el-table :data="forecastResult.lines" empty-text="暂无可预测分层"
            ><el-table-column label="景区 / 业务 / 平台" min-width="200"
              ><template #default="{ row }"
                >{{ label(row.scenic_id) }} / {{ label(row.business_type) }} /
                {{ row.platform || '未标注' }}</template
              ></el-table-column
            ><el-table-column label="指标"
              ><template #default="{ row }">{{
                metricName(row.metric)
              }}</template></el-table-column
            ><el-table-column label="预测 / 区间" min-width="200"
              ><template #default="{ row }"
                >{{ display(row.forecast, row.metric) }} /
                {{ display(row.interval_low, row.metric) }} ~
                {{ display(row.interval_high, row.metric) }}</template
              ></el-table-column
            ><el-table-column label="置信度"
              ><template #default="{ row }">{{
                confidenceNames[row.confidence]
              }}</template></el-table-column
            ><el-table-column label="依据" min-width="260"
              ><template #default="{ row }"
                >{{ row.reasons.join('；') }}
                <div v-for="(c, name) in row.components" :key="name">
                  {{ name }}：{{ display(c.value, row.metric) }}，权重
                  {{ Number(c.weight) * 100 }}%
                </div></template
              ></el-table-column
            ></el-table
          ></el-card
        ></template
      >
      <el-empty
        v-else
        description="维护周期与因素后生成预测，结果包含区间、置信度和分层依据。"
      />
    </section>
    <el-card v-if="qualityIssues.length" shadow="never"
      ><template #header>数据质量 · {{ qualityIssues.length }} 项</template>
      <p class="muted">以下台账存在质量问题，请核对后重新确认。</p>
      <p v-for="(q, i) in qualityIssues" :key="i">
        {{ label(q.business_type) }} · 行 {{ q.row_id ?? '未知' }} ·
        {{ q.code }}
      </p></el-card
    >
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import BaseChart from '@/components/BaseChart.vue'
import ForecastFactorEditor from '@/components/ForecastFactorEditor.vue'
import {
  getOperationAnalysis,
  createOperationForecast,
  exportOperationForecast,
} from '@/api/operation'
import { usePortalStore } from '@/store/portal'
import { scenicSpots, getScenicById } from '@/constants/scenic'
import { yuanToWan } from '@/utils/money'
const portal = usePortalStore()
const canForecast = computed(() =>
  portal.hasPermission('supply.operation.create'),
)
const canExport = computed(() =>
  portal.hasPermission('supply.operation.export'),
)
const canEditFactors = canForecast
const iso = (d) => d.toISOString().slice(0, 10)
const localDate = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const today = new Date()
const initialDates = [
  localDate(new Date(today.getFullYear(), today.getMonth(), 1)),
  localDate(today),
]
const tabFilters = ref({
  analysis: {
    dateRange: [...initialDates],
    scenicIds: [],
    businessTypes: [],
    platforms: [],
  },
  forecast: {
    dateRange: [...initialDates],
    scenicIds: [],
    businessTypes: [],
    platforms: [],
  },
})
const fieldForTab = (key) =>
  computed({
    get: () => tabFilters.value[activeTab.value][key],
    set: (value) => {
      tabFilters.value[activeTab.value][key] = value
    },
  })
const dateRange = fieldForTab('dateRange')
const scenicIds = fieldForTab('scenicIds')
const businessTypes = fieldForTab('businessTypes')
const platforms = computed({
  get: () => tabFilters.value[activeTab.value].platforms,
  set: (values) => {
    tabFilters.value[activeTab.value].platforms = values.filter((value) =>
      platformOptions.value.includes(value),
    )
  },
})
const factors = ref([])
const forecastPeriodMode = ref('custom')
const forecastMonth = ref('')
function selectForecastMonth(month) {
  forecastMonth.value = month || ''
  tabFilters.value.forecast.dateRange = month ? monthDates(month) : []
}
function monthDates(month) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month || ''))
    throw new Error('请选择有效的预测月份')
  const [year, monthNumber] = month.split('-').map(Number)
  const lastDay = new Date(year, monthNumber, 0).getDate()
  return [`${month}-01`, `${month}-${lastDay}`]
}
const activeTab = ref('analysis'),
  analysis = ref(null),
  forecastResult = ref(null),
  history = ref(null)
const historyError = ref('')
const loading = ref(false),
  forecastLoading = ref(false),
  exporting = ref(false),
  error = ref(''),
  chartMetric = ref('settlement_amount')
const metrics = [
  { key: 'settlement_amount', label: '结算金额', comparison: 'settlement' },
  { key: 'writeoff_amount', label: '景区核销金额', comparison: 'writeoff' },
  { key: 'order_count', label: '订单量', comparison: 'orders' },
  {
    key: 'capital_occupation',
    label: '资金占用',
    comparison: 'capital_occupation',
  },
]
const dimensionNames = {
    scenic_id: '景区',
    business_type: '业务',
    platform: '平台',
  },
  confidenceNames = { high: '高', medium: '中', low: '低' }
const label = (v) =>
  getScenicById(v)?.name ||
  { ticket: '门票', hotel: '酒店' }[v] ||
  v ||
  '未标注'
const metricName = (key) => metrics.find((m) => m.key === key)?.label || key
const display = (v, key) =>
  v == null
    ? '数据不足'
    : key === 'order_count'
      ? `${Number(v).toLocaleString()} 单`
      : `${yuanToWan(v).toFixed(2)} 万元`
const rate = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)
const platformOptions = ref([])
function observePlatforms(result) {
  platformOptions.value = [
    ...new Set([
      ...platformOptions.value,
      ...(result.rankings || [])
        .filter((r) => r.dimension === 'platform')
        .map((r) => r.value)
        .filter(Boolean),
    ]),
  ]
}
const qualityIssues = computed(
  () =>
    (activeTab.value === 'analysis' ? analysis.value : forecastResult.value)
      ?.quality_issues || [],
)
function dates(maxDays = 366, period = dateRange.value) {
  const [start, end] = period || []
  if (!start || !end || end < start)
    throw new Error('请选择有效的开始和结束日期')
  if ((Date.parse(end) - Date.parse(start)) / 86400000 + 1 > maxDays)
    throw new Error(`时间范围不能超过 ${maxDays} 天`)
  return { start_date: start, end_date: end }
}
function query(period) {
  return {
    ...period,
    scenic_id: [...scenicIds.value],
    business_type: [...businessTypes.value],
    platform: [...platforms.value],
  }
}
function payload() {
  return {
    ...dates(
      90,
      forecastPeriodMode.value === 'month'
        ? monthDates(forecastMonth.value)
        : tabFilters.value.forecast.dateRange,
    ),
    scenic_ids: [...scenicIds.value],
    business_types: [...businessTypes.value],
    platforms: [...platforms.value],
    factors: factors.value.map((f) => ({ ...f })),
  }
}
const failure = (e) => {
  const detail = e?.response?.data?.detail
  if (Array.isArray(detail))
    return detail.map((d) => `${(d.loc || []).join('.')}：${d.msg}`).join('；')
  return typeof detail === 'string' ? detail : e.message || '请求失败，请重试'
}
async function loadAnalysis() {
  loading.value = true
  error.value = ''
  try {
    analysis.value = await getOperationAnalysis(query(dates()))
    observePlatforms(analysis.value)
  } catch (e) {
    error.value = failure(e)
  } finally {
    loading.value = false
  }
}
let forecastPayload = null
async function generateForecast() {
  if (!canForecast.value) return
  forecastLoading.value = true
  error.value = ''
  historyError.value = ''
  try {
    const p = payload(),
      days = (Date.parse(p.end_date) - Date.parse(p.start_date)) / 86400000 + 1
    const historyPeriod = {
      start_date: iso(new Date(Date.parse(p.start_date) - days * 4 * 86400000)),
      end_date: iso(new Date(Date.parse(p.start_date) - 86400000)),
    }
    const [result, past] = await Promise.allSettled([
      createOperationForecast(p),
      getOperationAnalysis(query(historyPeriod)),
    ])
    if (result.status === 'rejected') throw result.reason
    forecastResult.value = result.value
    history.value = past.status === 'fulfilled' ? past.value : null
    if (past.status === 'rejected')
      historyError.value = `历史数据加载失败：${failure(past.reason)}。预测结果仍可查看和导出。`
    forecastPayload = p
  } catch (e) {
    error.value = failure(e)
  } finally {
    forecastLoading.value = false
  }
}
async function exportForecast() {
  if (!canExport.value) return
  exporting.value = true
  error.value = ''
  try {
    const blob = await exportOperationForecast(forecastPayload || payload()),
      url = URL.createObjectURL(blob),
      a = document.createElement('a')
    a.href = url
    a.download = '经营数据预测.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = failure(e)
  } finally {
    exporting.value = false
  }
}
const forecastMetrics = computed(() =>
  metrics.slice(0, 3).map((m) => {
    const lines = (forecastResult.value?.lines || []).filter(
        (l) => l.metric === m.key,
      ),
      valid = lines.filter((l) => l.forecast != null)
    const sum = (field) =>
      valid.length ? valid.reduce((n, l) => n + Number(l[field] || 0), 0) : null
    return {
      ...m,
      value: sum('forecast'),
      low: sum('interval_low'),
      high: sum('interval_high'),
      missing: lines.length - valid.length,
    }
  }),
)
const scale = (v, key) => (key === 'order_count' ? Number(v) : yuanToWan(v))
const analysisChart = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: metrics.map((m) => m.label) },
  grid: { left: 70, right: 65, bottom: 40 },
  xAxis: {
    type: 'category',
    data: (analysis.value?.trends || []).map((t) => t.day),
  },
  yAxis: [
    { type: 'value', name: '万元' },
    { type: 'value', name: '单' },
  ],
  series: metrics.map((m) => ({
    name: m.label,
    type: 'line',
    showSymbol: false,
    yAxisIndex: m.key === 'order_count' ? 1 : 0,
    data: (analysis.value?.trends || []).map((t) => scale(t[m.key], m.key)),
  })),
}))
const forecastChart = computed(() => {
  const result = forecastResult.value
  if (!result) return {}
  const key = chartMetric.value,
    span =
      (Date.parse(result.end_date) - Date.parse(result.start_date)) / 86400000 +
      1,
    base = Date.parse(result.start_date) - span * 4 * 86400000
  const values = history.value ? [0, 0, 0, 0] : [null, null, null, null],
    labels = values.map(
      (_, i) =>
        `${iso(new Date(base + i * span * 86400000))} ~ ${iso(new Date(base + ((i + 1) * span - 1) * 86400000))}`,
    )
  for (const t of history.value?.trends || []) {
    const i = Math.floor((Date.parse(t.day) - base) / (span * 86400000))
    if (i >= 0 && i < 4) values[i] += Number(t[key] || 0)
  }
  const m = forecastMetrics.value.find((m) => m.key === key),
    n = (v) => (v == null ? null : scale(v, key))
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['历史', '预测', '预测区间'] },
    grid: { left: 70, right: 24, bottom: 85 },
    xAxis: {
      type: 'category',
      data: [...labels, `${result.start_date} ~ ${result.end_date}`],
      axisLabel: { rotate: 15 },
    },
    yAxis: { type: 'value', name: key === 'order_count' ? '单' : '万元' },
    series: [
      { name: '历史', type: 'line', data: [...values.map(n), null] },
      {
        name: '预测',
        type: 'line',
        symbolSize: 12,
        data: [null, null, null, null, n(m.value)],
      },
      {
        name: '预测区间',
        type: 'custom',
        encode: { x: 0, y: [1, 2] },
        data: m.low == null ? [] : [[4, n(m.low), n(m.high)]],
        renderItem: (_params, api) => {
          const low = api.coord([api.value(0), api.value(1)]),
            high = api.coord([api.value(0), api.value(2)])
          return {
            type: 'rect',
            shape: {
              x: low[0] - 24,
              y: high[1],
              width: 48,
              height: Math.max(2, low[1] - high[1]),
            },
            style: api.style({ opacity: 0.25 }),
          }
        },
      },
    ],
  }
})
onMounted(loadAnalysis)
</script>

<style scoped>
.operation-analysis {
  display: grid;
  gap: 18px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
  background: var(--surface);
}
.filters :deep(.el-select) {
  width: 190px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}
.metrics strong {
  display: block;
  margin-top: 14px;
  font-size: 26px;
  color: var(--el-color-primary);
  font-family: var(--font-display);
}
.forecast-metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 18px 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}
section > .el-card + .el-card {
  margin-top: 18px;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}
@media (max-width: 900px) {
  .metrics,
  .forecast-metrics,
  .columns {
    grid-template-columns: 1fr;
  }
  .filters :deep(.el-select),
  .filters :deep(.el-date-editor) {
    width: 100%;
  }
}
</style>

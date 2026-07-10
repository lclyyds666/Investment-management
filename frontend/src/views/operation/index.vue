<template>
  <div class="operation" v-loading="loading">
    <!-- 全局日期 / 周期选择器 -->
    <el-card shadow="never" class="filter-bar">
      <div class="filter-inner">
        <div class="filter-left">
          <span class="filter-label">统计周期</span>
          <el-radio-group v-model="period" @change="onPeriodChange">
            <el-radio-button value="month">本月</el-radio-button>
            <el-radio-button value="quarter">本季度</el-radio-button>
            <el-radio-button value="year">本年</el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-model="refMonth"
            type="month"
            value-format="YYYY-MM"
            format="YYYY 年 MM 月"
            placeholder="选择月份"
            :clearable="false"
            style="width: 160px"
          />
        </div>
        <el-tag type="primary" effect="light" size="large">当前：{{ periodLabel }}</el-tag>
      </div>
    </el-card>

    <!-- KPI 指标卡 -->
    <el-row :gutter="16" class="kpi-row">
      <el-col :span="6" v-for="kpi in kpiCards" :key="kpi.label">
        <el-card
          shadow="hover"
          class="kpi-card"
          :class="{ 'kpi-clickable': kpi.clickable }"
          @click="kpi.clickable && openOrders()"
        >
          <div class="kpi-label">
            {{ kpi.label }}
            <el-icon v-if="kpi.clickable" class="kpi-arrow"><Right /></el-icon>
          </div>
          <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
          <div class="kpi-foot">
            <span v-if="kpi.clickable" class="kpi-hint">点击查看订单明细</span>
            <span v-else class="kpi-period">{{ periodLabel }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <!-- 营收/利润月度趋势 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>营收 / 利润趋势（{{ periodLabel }}）</template>
          <BaseChart :option="trendOption" />
        </el-card>
      </el-col>
      <!-- 业务条线营收占比 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>业务条线营收占比（{{ year }}年）</template>
          <BaseChart :option="pieOption" />
        </el-card>
      </el-col>
    </el-row>

    <!-- AI 智能大脑分析（常驻底部） -->
    <AiBrainPanel />

    <!-- 订单明细抽屉（Mock 数据） -->
    <el-drawer v-model="ordersVisible" title="最近订单明细" size="720px" direction="rtl">
      <div class="orders-summary">
        <el-statistic title="订单总数" :value="kpiRaw.total_orders || 0" />
        <el-statistic title="下方展示" :value="mockOrders.length" suffix=" 条最近订单" />
      </div>
      <el-table :data="mockOrders" border stripe size="small" class="orders-table">
        <el-table-column prop="order_no" label="订单编号" width="150" />
        <el-table-column prop="customer" label="客户" min-width="130" />
        <el-table-column prop="product" label="商品/服务" min-width="140" />
        <el-table-column label="金额(元)" width="120" align="right">
          <template #default="{ row }">{{ Number(row.amount).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="date" label="下单日期" width="120" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="ORDER_STATUS[row.status]" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import BaseChart from '@/components/BaseChart.vue'
import AiBrainPanel from '@/components/AiBrainPanel.vue'
import { getDashboard } from '@/api/operation'

const loading = ref(false)
const dashboard = ref({ kpi: {}, trend: [], line_share: [] })

// 周期选择：本月 / 本季度 / 本年 + 参考月份
const period = ref('year')
const refMonth = ref('2026-06')
const year = computed(() => Number(refMonth.value.slice(0, 4)))
const monthNum = computed(() => Number(refMonth.value.slice(5, 7)))
const quarter = computed(() => Math.ceil(monthNum.value / 3))

const yuan = (v) => '¥' + Number(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })

const kpiRaw = computed(() => dashboard.value.kpi || {})

// 当前周期覆盖的月份（YYYY-MM）
const selectedMonths = computed(() => {
  const y = year.value
  const pad = (m) => `${y}-${String(m).padStart(2, '0')}`
  if (period.value === 'month') return [pad(monthNum.value)]
  if (period.value === 'quarter') {
    const start = (quarter.value - 1) * 3 + 1
    return [pad(start), pad(start + 1), pad(start + 2)]
  }
  return dashboard.value.trend.map((t) => t.month) // 本年：全部
})

// 依据周期过滤后的趋势数据
const filteredTrend = computed(() =>
  dashboard.value.trend.filter((t) => selectedMonths.value.includes(t.month))
)

// 依据周期重新聚合的 KPI（本年与后端汇总一致，子周期客户端聚合）
const periodKpi = computed(() => {
  const ft = filteredTrend.value
  const revenue = ft.reduce((s, t) => s + Number(t.revenue), 0)
  const profit = ft.reduce((s, t) => s + Number(t.profit), 0)
  const cost = revenue - profit // profit = revenue - cost
  const totalRev = Number(kpiRaw.value.total_revenue || 0)
  const totalOrders = Number(kpiRaw.value.total_orders || 0)
  const orders = totalRev > 0 ? Math.round((totalOrders * revenue) / totalRev) : 0
  return { revenue, cost, profit, orders }
})

const periodLabel = computed(() => {
  if (period.value === 'month') return `${year.value}年${monthNum.value}月`
  if (period.value === 'quarter') return `${year.value}年第${quarter.value}季度`
  return `${year.value}年全年`
})

// KPI 卡片
const kpiCards = computed(() => {
  const k = periodKpi.value
  return [
    { label: '总营收', value: yuan(k.revenue), color: '#409eff' },
    { label: '总成本', value: yuan(k.cost), color: '#e6a23c' },
    { label: '总利润', value: yuan(k.profit), color: '#67c23a' },
    { label: '订单总数', value: Number(k.orders || 0).toLocaleString(), color: '#909399', clickable: true }
  ]
})

function onPeriodChange() {
  /* 周期切换由 computed 自动重算，无需额外逻辑 */
}

/* ============ 订单明细（Mock 数据） ============ */
const ordersVisible = ref(false)
const ORDER_STATUS = { 已完成: 'success', 配送中: 'primary', 待发货: 'warning', 已取消: 'info' }
const mockOrders = [
  { order_no: 'DD20260628012', customer: '济南新华书店', product: '中小学教辅采购', amount: 286500, date: '2026-06-28', status: '已完成' },
  { order_no: 'DD20260628007', customer: '青岛出版发行公司', product: '仓储物流服务', amount: 132000, date: '2026-06-28', status: '配送中' },
  { order_no: 'DD20260627031', customer: '烟台图书大厦', product: '文学类图书分销', amount: 98600, date: '2026-06-27', status: '已完成' },
  { order_no: 'DD20260627018', customer: '潍坊教育书店', product: '印刷采购（教材）', amount: 415800, date: '2026-06-27', status: '待发货' },
  { order_no: 'DD20260626022', customer: '淄博新华连锁', product: '渠道配送服务', amount: 76400, date: '2026-06-26', status: '已完成' },
  { order_no: 'DD20260626009', customer: '临沂书城', product: '少儿读物采购', amount: 58900, date: '2026-06-26', status: '配送中' },
  { order_no: 'DD20260625044', customer: '威海文化传媒', product: '期刊分销服务', amount: 34200, date: '2026-06-25', status: '已完成' },
  { order_no: 'DD20260625016', customer: '德州新华书店', product: '仓储代管服务', amount: 121500, date: '2026-06-25', status: '待发货' },
  { order_no: 'DD20260624030', customer: '泰安图书批发中心', product: '教辅图书采购', amount: 189700, date: '2026-06-24', status: '已完成' },
  { order_no: 'DD20260624005', customer: '聊城书香文化', product: '物流配送服务', amount: 43600, date: '2026-06-24', status: '已取消' }
]
function openOrders() {
  ordersVisible.value = true
}

// 折线/柱状趋势图 option（按当前周期）
const trendOption = computed(() => {
  const ft = filteredTrend.value
  const months = ft.map((t) => t.month.slice(5) + '月')
  const revenue = ft.map((t) => Number(t.revenue))
  const profit = ft.map((t) => Number(t.profit))
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['营收', '利润'] },
    grid: { left: 60, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => v / 10000 + '万' } },
    series: [
      { name: '营收', type: 'bar', data: revenue, itemStyle: { color: '#409eff' }, barMaxWidth: 36 },
      { name: '利润', type: 'line', smooth: true, data: profit, itemStyle: { color: '#67c23a' } }
    ]
  }
})

// 饼图 option（业务条线，年度）
const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0 },
  series: [
    {
      name: '营收占比',
      type: 'pie',
      radius: ['40%', '65%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%' },
      data: dashboard.value.line_share.map((l) => ({
        name: l.business_line,
        value: Number(l.revenue)
      }))
    }
  ]
}))

async function load() {
  loading.value = true
  try {
    dashboard.value = await getDashboard(year.value)
  } finally {
    loading.value = false
  }
}

// 年份变化时重新拉取后端数据
watch(year, () => load())

onMounted(load)
</script>

<style scoped lang="scss">
.operation {
  .filter-bar {
    margin-bottom: 16px;
    :deep(.el-card__body) {
      padding: 14px 18px;
    }
  }
  .filter-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .filter-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .filter-label {
    color: #606266;
    font-size: 14px;
    font-weight: 600;
  }

  .kpi-row {
    margin-bottom: 16px;
  }
  .kpi-card {
    position: relative;
    // 悬停轻微上浮 + 更明显的投影
    transition: box-shadow 0.3s ease, transform 0.3s ease;
    &:hover {
      transform: translateY(-4px);
      box-shadow: 0 10px 24px rgba(64, 158, 255, 0.16) !important;
    }
    .kpi-label {
      color: #909399;
      font-size: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .kpi-value {
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
    }
    .kpi-foot {
      margin-top: 6px;
      min-height: 18px;
    }
    .kpi-hint {
      font-size: 12px;
      color: #c0c4cc;
    }
    .kpi-period {
      font-size: 12px;
      color: #c0c4cc;
    }
    .kpi-arrow {
      color: #c0c4cc;
      transition: transform 0.2s;
    }
  }
  // 可点击卡片：光标 + 顶部高亮条 + Hover 箭头位移
  .kpi-clickable {
    cursor: pointer;
    border-top: 3px solid #409eff !important;
    &:hover {
      .kpi-arrow {
        transform: translateX(3px);
        color: #409eff;
      }
      .kpi-hint {
        color: #409eff;
      }
    }
  }
}

.orders-summary {
  display: flex;
  gap: 48px;
  padding: 4px 4px 18px;
  margin-bottom: 8px;
  border-bottom: 1px solid rgba(96,150,210,0.16);
}
.orders-table {
  margin-top: 4px;
}
</style>

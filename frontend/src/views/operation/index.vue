<template>
  <div class="operation" v-loading="loading">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="tb-left">
          <span class="tb-title">经营数据 · 供管公司项目投入与回款</span>
          <el-tag v-if="hasProjects" type="success" effect="plain" size="small">已接入真实项目数据</el-tag>
          <el-tag v-else type="info" effect="plain" size="small">暂无项目数据，请上传统计表</el-tag>
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

    <!-- 核心指标卡 -->
    <el-row :gutter="16" class="kpi-row">
      <el-col :span="8" v-for="kpi in kpiCards" :key="kpi.label">
        <el-card shadow="hover" class="kpi-card" :style="{ borderTopColor: kpi.color }">
          <div class="kpi-label">{{ kpi.label }}</div>
          <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
          <div class="kpi-foot">{{ kpi.hint }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 项目明细 -->
    <el-card shadow="never" class="mt">
      <template #header><span class="card-title">项目投入与回款收益明细</span></template>
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
        <el-table-column label="已回款(规模)" min-width="130" align="right">
          <template #default="{ row }">{{ yuan(row.realized_scale) }}</template>
        </el-table-column>
        <el-table-column label="实现毛利" min-width="120" align="right">
          <template #default="{ row }"><span class="income">{{ yuan(row.gross_profit) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率" width="90" align="right">
          <template #default="{ row }">{{ row.profit_rate != null ? (row.profit_rate * 100).toFixed(2) + '%' : '—' }}</template>
        </el-table-column>
        <el-table-column label="资金占用" min-width="130" align="right">
          <template #default="{ row }"><span class="occ">{{ yuan(row.capital_occupied) }}</span></template>
        </el-table-column>
        <el-table-column prop="pay_date" label="付款日期" width="120" align="center" />
      </el-table>
      <el-empty v-if="!dash.projects.length" description="暂无项目数据，请点击右上角上传统计表" />
    </el-card>

    <!-- 图表 -->
    <el-row :gutter="16" class="mt">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>各项目 投入 vs 已回款</template>
          <BaseChart :option="barOption" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>各项目投入占比</template>
          <BaseChart :option="pieOption" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 对账单平台明细（独立数据源，保留） -->
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

    <!-- AI 智能大脑分析 -->
    <AiBrainPanel />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import BaseChart from '@/components/BaseChart.vue'
import AiBrainPanel from '@/components/AiBrainPanel.vue'
import { getFinancial, uploadProjects, setAvailableFunds } from '@/api/operation'

const loading = ref(false)
const uploading = ref(false)
const savingFunds = ref(false)
const availableFunds = ref(0)
const dash = ref({
  existing_scale: 0, total_realized_scale: 0, total_gross_income: 0,
  profit_rate: null, capital_occupied: 0, available_funds: 0,
  projects: [], platforms: []
})

const yuan = (v) => '¥' + Number(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const splitPlatforms = (s) => String(s || '').replace(/，/g, ',').replace(/、/g, ',').split(',').map((x) => x.trim()).filter(Boolean)
const hasProjects = computed(() => dash.value.projects.length > 0)

const kpiCards = computed(() => {
  const d = dash.value
  return [
    { label: '现存业务规模(已投入本金)', value: yuan(d.existing_scale), color: '#909399', hint: '各项目投入金额合计' },
    { label: '已实现业务规模', value: yuan(d.total_realized_scale), color: '#409eff', hint: '各项目回款小计合计' },
    { label: '已实现业务毛收入', value: yuan(d.total_gross_income), color: '#67c23a', hint: '各项目实现毛利合计' },
    { label: '业务收益率', value: d.profit_rate != null ? d.profit_rate + '%' : '—', color: '#e6a23c', hint: '按投入加权平均' },
    { label: '资金占用情况', value: yuan(d.capital_occupied), color: '#f56c6c', hint: '投入 − 已回款' },
    { label: '可用资金', value: Number(d.available_funds) > 0 ? yuan(d.available_funds) : '—', color: '#2de1c2', hint: '手工录入，待补充' }
  ]
})

const barOption = computed(() => {
  const p = dash.value.projects
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['投入金额', '已回款'] },
    grid: { left: 70, right: 20, top: 40, bottom: 70 },
    xAxis: { type: 'category', data: p.map((x) => x.project_name), axisLabel: { interval: 0, rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => v / 10000 + '万' } },
    series: [
      { name: '投入金额', type: 'bar', data: p.map((x) => Number(x.invested_amount)), itemStyle: { color: '#409eff' }, barMaxWidth: 28 },
      { name: '已回款', type: 'bar', data: p.map((x) => Number(x.realized_scale)), itemStyle: { color: '#67c23a' }, barMaxWidth: 28 }
    ]
  }
})

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
  legend: { type: 'scroll', bottom: 0 },
  series: [{
    name: '投入占比', type: 'pie', radius: ['40%', '65%'],
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    label: { formatter: '{b}\n{d}%' },
    data: dash.value.projects.map((x) => ({ name: x.project_name, value: Number(x.invested_amount) }))
  }]
}))

async function load() {
  loading.value = true
  try {
    dash.value = await getFinancial()
    availableFunds.value = Number(dash.value.available_funds || 0)
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
  } catch (e) {
    /* 错误消息已由拦截器提示 */
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
  .tb-left { display: flex; align-items: center; gap: 10px; }
  .tb-title { font-size: 16px; font-weight: 700; color: #303133; }
  .tb-right { display: flex; align-items: center; gap: 10px; }
  .cost-label { color: #606266; font-size: 13px; }

  .kpi-row { margin-bottom: 4px; row-gap: 16px; }
  .kpi-card {
    border-top: 3px solid #ccc;
    transition: box-shadow .3s ease, transform .3s ease;
    &:hover { transform: translateY(-4px); box-shadow: 0 10px 24px rgba(64,158,255,.16) !important; }
    .kpi-label { color: #909399; font-size: 14px; }
    .kpi-value { margin-top: 8px; font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; }
    .kpi-foot { margin-top: 6px; font-size: 12px; color: #c0c4cc; min-height: 16px; }
  }
  .mt { margin-top: 16px; }
  .card-title { font-weight: 700; }
  .income { color: #67c23a; font-weight: 700; }
  .occ { color: #f56c6c; font-weight: 600; }
  .pf-tag { margin: 0 4px 2px 0; }
}
</style>

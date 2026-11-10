<template>
  <div class="work-items">
    <el-card shadow="never">
      <template #header><div class="work-items-header"><h2>待处理事项</h2><el-button :loading="store.loading" @click="store.load">刷新</el-button></div></template>
      <el-alert v-if="store.error" title="加载失败，请刷新重试" type="error" :closable="false" />
      <el-table v-loading="store.loading" :data="store.items" stripe empty-text="暂无待处理事项">
        <el-table-column label="类型" min-width="170"><template #default="{ row }">{{ labels[row.item_type] || row.item_type }}</template></el-table-column>
        <el-table-column label="景区" min-width="140"><template #default="{ row }">{{ scenicName(row.scenic_id) }}</template></el-table-column>
        <el-table-column prop="contract_name" label="合同" min-width="180" />
        <el-table-column label="金额（元）" min-width="140" align="right"><template #default="{ row }">{{ money(row.amount) }}</template></el-table-column>
        <el-table-column prop="due_date" label="日期" width="120" />
        <el-table-column prop="status" label="状态" min-width="140" />
        <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" @click="handleWorkItem(row)">去处理</el-button></template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useWorkItemsStore } from '@/store/workItems'
import { getScenicById } from '@/constants/scenic'

const store = useWorkItemsStore()
const router = useRouter()
const labels = { missing_contract: '待关联合同', cash_execution: '待付款执行', receipt_confirmation: '待回款确认', input_invoice_missing: '预付款未补进项发票', invoice_unallocated: '发票待核销', fund_unallocated: '资金待核销', contract_amount_exceeded: '合同金额控制', fund_due_soon: '资金即将到期', fund_overdue: '资金已逾期' }
const money = value => Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const scenicName = id => getScenicById(id)?.name || id || '—'
async function handleWorkItem(item) {
  await router.push({ path: item.target_path, query: item.target_query || {} })
}
</script>

<style scoped>
.work-items-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
h2 { font-size: 18px; margin: 0; }
</style>

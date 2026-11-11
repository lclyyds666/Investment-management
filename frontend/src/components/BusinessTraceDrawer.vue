<template>
  <el-drawer :model-value="modelValue" title="业务链路" size="min(680px, 100%)"
    @update:model-value="$emit('update:modelValue', $event)">
    <p>选择业务与原始台账期次查看关联记录。金额单位：元。</p>
    <el-select :model-value="selectedPeriod" placeholder="请选择业务 / 期次" class="period-select"
      :disabled="loading" @update:model-value="$emit('select-period', $event)">
      <el-option v-for="(period, index) in periods" :key="`${period.source_kind}:${period.period_key}`"
        :value="index" :label="`${period.source_kind === 'hotel' ? '酒店' : '门票'} · ${period.period_key}`" />
    </el-select>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-else-if="loading" role="status">正在加载业务链路…</div>
    <p v-else-if="!periods.length">当前景区及年份暂无可追溯期次；无日期期次仅在全部年份下显示。</p>
    <p v-else-if="!trace">请选择期次。</p>
    <template v-else>
      <p v-if="trace.restricted_count" role="status" data-testid="restricted-count">
        {{ trace.restricted_count }} 个关联节点因权限或关联端点不可见而隐藏。
      </p>
      <section v-for="section in sections" :key="section.key" class="trace-section" :data-testid="`trace-${section.key}`">
        <h3>{{ section.label }}（{{ section.rows.length }}）</h3>
        <p v-if="!section.rows.length" class="empty">暂无可见关联记录</p>
        <ul v-else>
          <li v-for="node in section.rows" :key="node.id">
            <button type="button" class="node-link" @click="openNode(section.key, node)">
              {{ nodeLabel(section.key, node) }}
            </button>
          </li>
        </ul>
      </section>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: Boolean,
  trace: { type: Object, default: null },
  periods: { type: Array, default: () => [] },
  selectedPeriod: { type: Number, default: null },
  loading: Boolean,
  error: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'select-period', 'open-node'])
const sectionLabels = [
  ['ledger_rows', '台账'], ['invoices', '发票'], ['allocations', '核销'],
  ['funds', '资金'], ['execution_tasks', '执行任务'], ['approvals', '审批'], ['contracts', '合同']
]
const sections = computed(() => sectionLabels.map(([key, label]) => ({ key, label, rows: props.trace?.[key] || [] })))
function nodeLabel(kind, node) {
  if (kind === 'ledger_rows') return `#${node.id} · ${node.platform} · ${node.confirmed ? '已确认' : '待确认'}`
  if (kind === 'contracts') return `${node.contract_no} · ${node.status}`
  if (kind === 'execution_tasks') return `#${node.id} · ${node.status} · 已执行 ${node.executed_amount} / ${node.planned_amount} 元`
  if (kind === 'approvals') return `#${node.id} · ${node.form_type} · ${node.status}`
  return `#${node.id} · ${node.status || node.direction || '核销'} · ${node.amount} 元`
}
function openNode(kind, node) {
  const routes = {
    ledger_rows: { path: `/supplymanagement/cultural-tourism/${encodeURIComponent(props.trace.scenic_id)}`,
      query: { source_kind: props.trace.source_kind, period_key: props.trace.period_key } },
    invoices: { path: '/supplymanagement/finance/invoice', query: { invoice_id: String(node.id) } },
    allocations: { path: '/supplymanagement/finance/fund', query: { fund_id: String(node.fund_transaction_id) } },
    funds: { path: '/supplymanagement/finance/fund', query: { fund_id: String(node.id) } },
    execution_tasks: { path: '/supplymanagement/finance/fund', query: { tab: 'execution', task_id: String(node.id) } },
    approvals: { path: '/supplymanagement/approval', query: { form_id: String(node.id) } },
    contracts: { path: '/investment/legal-risk/contracts', query: { contract_id: String(node.id) } }
  }
  emit('open-node', routes[kind])
}
</script>

<style scoped>
.period-select { width: 100%; }
.trace-section { margin-top: 22px; }
.trace-section h3 { font-size: 15px; margin-bottom: 8px; }
.trace-section ul { padding-left: 20px; }
.trace-section li { margin: 8px 0; }
.empty { color: var(--el-text-color-secondary); }
.node-link { border: 0; background: transparent; color: var(--el-color-primary); cursor: pointer; text-align: left; padding: 4px 0; font: inherit; overflow-wrap: anywhere; }
</style>

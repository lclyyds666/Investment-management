<template>
  <section class="approver-fields" aria-labelledby="approver-fields-title">
    <div class="chain-heading">
      <div>
        <h3 id="approver-fields-title">指定审批链路</h3>
        <p>按实际流转顺序选择审批人，同一人不能承担多个环节。</p>
      </div>
      <span class="completion" :class="{ complete: isComplete }">{{ completedCount }}/{{ nodes.length }} 已选择</span>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      show-icon
      title="候选人加载失败"
      description="请检查网络后重新加载，已选人员将在仍然有效时保留。"
      class="state-alert"
    >
      <template #default>
        <el-button type="primary" link data-testid="retry-candidates" @click="reloadCandidates({ preserve: true })">重新加载</el-button>
      </template>
    </el-alert>

    <div class="approval-chain" :aria-busy="loading">
      <article
        v-for="(node, index) in nodes"
        :key="node.code"
        class="approver-node"
        :class="{ selected: Boolean(selected[node.code]), invalid: invalidNodes.has(node.code) }"
        data-testid="approver-node"
        :data-node-code="node.code"
      >
        <div class="sequence" aria-hidden="true">
          <span>{{ index + 1 }}</span>
        </div>
        <div class="node-label">
          <strong>{{ node.name }}</strong>
          <span>{{ node.positionName }}</span>
        </div>
        <div class="candidate-field">
          <el-skeleton v-if="loading && !candidatesByNode[node.code]" :rows="1" animated class="candidate-skeleton" />
          <el-select
            :model-value="selected[node.code]"
            :data-focus-node="node.code"
            :placeholder="`选择${node.name}`"
            filterable
            clearable
            :disabled="loading || Boolean(errorsByNode[node.code])"
            :aria-invalid="invalidNodes.has(node.code)"
            @update:model-value="selectUser(node.code, $event)"
          >
            <el-option
              v-for="candidate in candidatesByNode[node.code] || []"
              :key="candidate.user_id"
              :value="candidate.user_id"
              :label="candidate.full_name"
              :disabled="isCandidateDisabled(node.code, candidate.user_id)"
            >
              <div class="option-name">{{ candidate.full_name }}</div>
              <div class="option-meta">{{ candidate.organization_name }} · {{ candidate.position_name }}</div>
            </el-option>
          </el-select>
          <div v-if="errorsByNode[node.code]" class="node-state error">
            本环节候选人加载失败
            <button type="button" @click="reloadNode(node.code)">重试</button>
          </div>
          <div v-else-if="!loading && !candidatesByNode[node.code]?.length" class="node-state empty">暂无符合当前任职条件的候选人</div>
          <div v-else-if="selectedCandidate(node.code)" class="selected-detail">
            <span>{{ selectedCandidate(node.code).organization_name }}</span>
            <span>{{ selectedCandidate(node.code).position_name }}</span>
            <span>{{ effectivePeriod(selectedCandidate(node.code)) }}</span>
          </div>
        </div>
      </article>
    </div>

    <p v-if="validationError" class="validation-error" role="alert">{{ validationError }}</p>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { listWorkflowCandidates } from '@/api/workflow'

const props = defineProps({
  workflowCode: { type: String, required: true },
  modelValue: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['update:modelValue'])

const NODE_DEFINITIONS = {
  'supply.contract.v2': [
    { code: 'company_leader', name: '公司负责人', positionName: '指定公司负责人' },
    { code: 'legal_counsel', name: '外聘法律顾问', positionName: '指定合同法律顾问' },
    { code: 'supply_governance_leader', name: '供管公司分管领导', positionName: '指定供管分管领导' }
  ],
  'supply.payment.v2': [
    { code: 'company_leader', name: '公司负责人', positionName: '指定公司负责人' },
    { code: 'supply_governance_leader', name: '供管公司分管领导', positionName: '指定供管分管领导' }
  ],
  'supply.business.v2': [
    { code: 'company_leader', name: '公司负责人', positionName: '指定公司负责人' },
    { code: 'supply_governance_leader', name: '供管公司分管领导', positionName: '指定供管分管领导' }
  ]
}

const nodes = computed(() => NODE_DEFINITIONS[props.workflowCode] || [])
const selected = ref({ ...props.modelValue })
const candidatesByNode = ref({})
const errorsByNode = ref({})
const loading = ref(false)
const validationError = ref('')
const invalidNodes = ref(new Set())

const completedCount = computed(() => nodes.value.filter((node) => selected.value[node.code]).length)
const isComplete = computed(() => completedCount.value === nodes.value.length && nodes.value.length > 0)
const loadError = computed(() => Object.keys(errorsByNode.value).length > 0)

watch(() => props.modelValue, (value) => {
  selected.value = { ...value }
}, { deep: true })

watch(() => props.workflowCode, async () => {
  selected.value = {}
  emit('update:modelValue', {})
  await reloadCandidates({ preserve: false })
})

function selectedCandidate(nodeCode) {
  return (candidatesByNode.value[nodeCode] || []).find((candidate) => candidate.user_id === selected.value[nodeCode])
}

function effectivePeriod(candidate) {
  if (!candidate.valid_from && !candidate.valid_until) return '当前有效'
  const start = candidate.valid_from ? `${candidate.valid_from} 起` : '已生效'
  const end = candidate.valid_until ? `${candidate.valid_until} 止` : '长期有效'
  return `${start} · ${end}`
}

function isCandidateDisabled(nodeCode, userId) {
  return Object.entries(selected.value).some(([selectedNode, selectedUser]) => (
    selectedNode !== nodeCode && Number(selectedUser) === Number(userId)
  ))
}

function selectUser(nodeCode, userId) {
  const next = { ...selected.value }
  if (userId === '' || userId === null || typeof userId === 'undefined') delete next[nodeCode]
  else next[nodeCode] = Number(userId)
  selected.value = next
  invalidNodes.value = new Set([...invalidNodes.value].filter((code) => code !== nodeCode))
  if (invalidNodes.value.size === 0) validationError.value = ''
  emit('update:modelValue', next)
}

function retainEligibleSelections(previous) {
  const retained = {}
  const usedUsers = new Set()
  for (const node of nodes.value) {
    const userId = Number(previous[node.code])
    const eligible = (candidatesByNode.value[node.code] || []).some((candidate) => candidate.user_id === userId)
    if (eligible && !usedUsers.has(userId)) {
      retained[node.code] = userId
      usedUsers.add(userId)
    }
  }
  selected.value = retained
  emit('update:modelValue', retained)
}

async function reloadNode(nodeCode) {
  errorsByNode.value = { ...errorsByNode.value, [nodeCode]: undefined }
  try {
    const candidates = await listWorkflowCandidates(props.workflowCode, nodeCode)
    candidatesByNode.value = { ...candidatesByNode.value, [nodeCode]: candidates }
    const nextErrors = { ...errorsByNode.value }
    delete nextErrors[nodeCode]
    errorsByNode.value = nextErrors
    retainEligibleSelections(selected.value)
  } catch (error) {
    errorsByNode.value = { ...errorsByNode.value, [nodeCode]: error }
  }
}

async function reloadCandidates({ preserve = true } = {}) {
  const previous = preserve ? { ...selected.value } : {}
  loading.value = true
  errorsByNode.value = {}
  const results = await Promise.allSettled(nodes.value.map(async (node) => ({
    nodeCode: node.code,
    candidates: await listWorkflowCandidates(props.workflowCode, node.code)
  })))
  const nextCandidates = preserve ? { ...candidatesByNode.value } : {}
  const nextErrors = {}
  results.forEach((result, index) => {
    const nodeCode = nodes.value[index].code
    if (result.status === 'fulfilled') nextCandidates[nodeCode] = result.value.candidates
    else nextErrors[nodeCode] = result.reason
  })
  candidatesByNode.value = nextCandidates
  errorsByNode.value = nextErrors
  retainEligibleSelections(previous)
  loading.value = false
  return Object.keys(nextErrors).length === 0
}

async function validate() {
  const missing = nodes.value.filter((node) => !selected.value[node.code]).map((node) => node.code)
  invalidNodes.value = new Set(missing)
  if (!missing.length) {
    validationError.value = ''
    return true
  }
  validationError.value = '请选择全部指定审批人后再提交。'
  await nextTick()
  const select = document.querySelector(`[data-focus-node="${missing[0]}"]`)
  select?.querySelector?.('input')?.focus()
  select?.focus?.()
  return false
}

onMounted(() => reloadCandidates({ preserve: true }))

defineExpose({ validate, reloadCandidates, reloadNode, isCandidateDisabled, selectUser })
</script>

<style scoped lang="scss">
.approver-fields { color: var(--el-text-color-primary); }
.chain-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3, 12px); margin-bottom: var(--space-4, 16px); }
.chain-heading h3 { margin: 0 0 4px; font-size: 16px; font-weight: 600; }
.chain-heading p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.completion { flex: none; padding: 3px 9px; border-radius: var(--el-border-radius-round); color: var(--el-text-color-secondary); background: var(--el-fill-color-light); font-size: 12px; }
.completion.complete { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.state-alert { margin-bottom: 12px; }
.approval-chain { border: 1px solid var(--el-border-color-light); border-radius: var(--el-border-radius-base); overflow: hidden; }
.approver-node { position: relative; display: grid; grid-template-columns: 38px minmax(150px, 180px) minmax(240px, 1fr); gap: 12px; align-items: start; padding: 14px 16px; background: var(--el-bg-color); transition: background-color var(--motion-fast, 160ms), border-color var(--motion-fast, 160ms); }
.approver-node + .approver-node { border-top: 1px solid var(--el-border-color-lighter); }
.approver-node.selected { background: var(--el-color-primary-light-9); }
.approver-node.invalid { box-shadow: inset 3px 0 0 var(--el-color-danger); }
.sequence { position: relative; display: flex; justify-content: center; min-height: 44px; }
.sequence::after { content: ''; position: absolute; top: 28px; bottom: -30px; width: 1px; background: var(--el-border-color); }
.approver-node:last-child .sequence::after { display: none; }
.sequence span { position: relative; z-index: 1; display: grid; width: 26px; height: 26px; place-items: center; border: 1px solid var(--el-border-color); border-radius: 50%; color: var(--el-text-color-secondary); background: var(--el-bg-color); font: 600 12px/1 var(--font-data, monospace); }
.selected .sequence span { border-color: var(--el-color-primary); color: #fff; background: var(--el-color-primary); }
.node-label { display: flex; flex-direction: column; gap: 3px; padding-top: 4px; }
.node-label strong { font-size: 14px; font-weight: 600; }
.node-label span { color: var(--el-text-color-secondary); font-size: 12px; }
.candidate-field :deep(.el-select) { width: 100%; }
.candidate-skeleton { margin-bottom: 6px; }
.candidate-field :deep(.el-select__wrapper.is-focused) { box-shadow: var(--focus-ring), 0 0 0 1px var(--el-color-primary) inset; }
.selected-detail { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 7px; color: var(--el-text-color-secondary); font-size: 12px; }
.selected-detail span + span::before { content: '·'; margin-right: 12px; color: var(--el-border-color); }
.node-state { margin-top: 7px; font-size: 12px; }
.node-state.empty { color: var(--el-color-warning); }
.node-state.error { color: var(--el-color-danger); }
.node-state button { margin-left: 6px; padding: 0; border: 0; color: var(--el-color-primary); background: transparent; cursor: pointer; text-decoration: underline; }
.node-state button:focus-visible { outline: none; border-radius: 2px; box-shadow: var(--focus-ring); }
.validation-error { margin: 10px 0 0; color: var(--el-color-danger); font-size: 13px; }
@media (max-width: 640px) {
  .chain-heading { align-items: stretch; flex-direction: column; }
  .completion { align-self: flex-start; }
  .approver-node { grid-template-columns: 30px minmax(0, 1fr); gap: 8px 10px; padding: 12px; }
  .node-label { grid-column: 2; }
  .candidate-field { grid-column: 2; }
  .selected-detail { flex-direction: column; gap: 2px; }
  .selected-detail span + span::before { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .approver-node { transition: none; }
}
</style>

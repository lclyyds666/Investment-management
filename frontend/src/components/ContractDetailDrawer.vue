<template>
  <el-drawer
    :model-value="modelValue"
    title="合同详情"
    size="820px"
    direction="rtl"
    @update:model-value="(v) => $emit('update:modelValue', v)"
  >
    <div v-loading="loading" v-if="contract">
      <div class="drawer-toolbar">
        <el-tag :type="STATUS_META[contract.status]?.type">
          {{ contract.status_label }}
        </el-tag>
        <!-- 仅当合同类型有值时才显示，避免空类型渲染成一个多余的空标签方框 -->
        <el-tag v-if="contract.contract_type_label" effect="plain">{{ contract.contract_type_label }}</el-tag>
        <span class="flex-1"></span>
        <el-button type="primary" :icon="Printer" :loading="docLoading" @click="downloadLegalDoc">
          生成并打印法律文件审批表
        </el-button>
      </div>

      <!-- 基础字段 -->
      <el-descriptions :column="2" border class="mb">
        <el-descriptions-item label="合同编号">{{ contract.contract_no }}</el-descriptions-item>
        <el-descriptions-item label="合同类型">{{ contract.contract_type_label || '—' }}</el-descriptions-item>
        <el-descriptions-item label="合同名称" :span="2">{{ contract.title }}</el-descriptions-item>
        <el-descriptions-item label="申请部门">{{ contract.department || '—' }}</el-descriptions-item>
        <el-descriptions-item label="是否内部合同">{{ contract.is_internal ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="合同标的" :span="2">{{ contract.subject || '—' }}</el-descriptions-item>
        <el-descriptions-item label="客户名称">{{ contract.customer_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="客户社会信用代码">{{ contract.customer_credit_code || '—' }}</el-descriptions-item>
        <el-descriptions-item label="签订日期">{{ contract.sign_date || '—' }}</el-descriptions-item>
        <el-descriptions-item label="合同金额">
          {{ Number(contract.amount).toLocaleString() }} {{ contract.currency || '' }}
          <span class="rmb">（{{ rmb }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="币种">{{ contract.currency || '—' }}</el-descriptions-item>
        <el-descriptions-item label="付款条件" :span="2">{{ contract.payment_terms || '—' }}</el-descriptions-item>
        <el-descriptions-item label="创建人(业务经办)">{{ contract.creator_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前环节">
          <el-tag v-if="contract.current_role_label" type="warning" size="small">
            {{ contract.current_role_label }}
          </el-tag>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="合同附件" :span="2">
          <template v-if="contract.attachment_name">
            <el-icon><Document /></el-icon>
            <span class="att-name">{{ contract.attachment_name }}</span>
            <el-button size="small" link type="primary" :icon="View" @click="previewAttachment">预览</el-button>
            <el-button size="small" link type="primary" :icon="Download" @click="downloadAttachment">下载</el-button>
          </template>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ contract.remark || '无' }}</el-descriptions-item>
      </el-descriptions>

      <h4 class="section-title"><el-icon><Guide /></el-icon> 岗位责任轨道</h4>
      <el-alert
        v-if="timelineError"
        type="error"
        :closable="false"
        title="流程记录加载失败，可重试"
        class="timeline-error"
      >
        <template #default><el-button link type="primary" @click="loadTimeline">重试</el-button></template>
      </el-alert>
      <WorkflowTimeline v-if="contract.workflow_version >= 2" :tasks="workflowTasks" />
      <el-timeline v-else class="flow-timeline">
        <el-timeline-item
          v-for="a in approvals"
          :key="a.id"
          :type="a.action === 'reject' ? 'danger' : 'success'"
          :timestamp="fmt(a.created_at)"
          size="large"
        >
          <div class="flow-node">
            <div class="flow-node-main">
              <span class="flow-role">{{ a.role_label }}</span>
              <el-tag :type="a.action === 'reject' ? 'danger' : 'success'" size="small" effect="plain">
                {{ a.action === 'reject' ? '退回' : '通过' }}
              </el-tag>
              <span class="flow-approver">{{ a.approver_name }}</span>
            </div>
            <div class="flow-comment" v-if="a.comment">{{ a.comment }}</div>
            <img v-if="a.signature_snapshot" :src="a.signature_snapshot" class="flow-sig" alt="签名" />
          </div>
        </el-timeline-item>
        <el-empty v-if="!approvals.length" :image-size="60" description="暂无审批流转记录" />
      </el-timeline>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Printer, Guide, Document, View, Download } from '@element-plus/icons-vue'
import { getContract, listApprovals, fetchContractAttachmentBlob, fetchLegalDocBlob } from '@/api/contract'
import { getWorkflowTimeline } from '@/api/workflow'
import { STATUS_META } from '@/constants/business'
import { digitToRMB } from '@/utils/rmb'
import { previewBlob, downloadBlob } from '@/utils/file'
import WorkflowTimeline from '@/components/workflow/WorkflowTimeline.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contractId: { type: [Number, String], default: null }
})
defineEmits(['update:modelValue'])
defineExpose({ reload: load })

const loading = ref(false)
const contract = ref(null)
const approvals = ref([])
const workflowTasks = ref([])
const timelineError = ref(false)
const docLoading = ref(false)

const rmb = computed(() => (contract.value ? digitToRMB(contract.value.amount) : ''))

async function downloadAttachment() {
  if (!contract.value?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(contract.value.id)
    downloadBlob(blob, contract.value.attachment_name)
  } catch {
    ElMessage.error('附件下载失败')
  }
}

async function previewAttachment() {
  if (!contract.value?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(contract.value.id)
    previewBlob(blob, contract.value.attachment_name)
  } catch {
    ElMessage.error('附件预览失败')
  }
}

function fmt(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}
function fmtDate(t) {
  if (!t) return ''
  return String(t).slice(0, 10)
}

async function load() {
  if (!props.contractId) return
  loading.value = true
  contract.value = null
  approvals.value = []
  workflowTasks.value = []
  timelineError.value = false
  try {
    const c = await getContract(props.contractId)
    contract.value = c
    await loadTimeline()
  } finally {
    loading.value = false
  }
}

async function loadTimeline() {
  if (!contract.value) return
  timelineError.value = false
  try {
    if (contract.value.workflow_version >= 2) {
      workflowTasks.value = await getWorkflowTimeline(contract.value.workflow_instance_id)
    } else {
      approvals.value = await listApprovals(contract.value.id)
    }
  } catch {
    timelineError.value = true
  }
}

// 生成并下载「法律文件审批表」.docx（后端 python-docx 生成，用 Word 打开打印）
async function downloadLegalDoc() {
  if (!contract.value) return
  docLoading.value = true
  try {
    const blob = await fetchLegalDocBlob(contract.value.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `法律文件审批表_${contract.value.contract_no}.docx`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('法律文件审批表已生成，请用 Word 打开打印')
  } catch {
    ElMessage.error('审批表生成失败')
  } finally {
    docLoading.value = false
  }
}

watch(
  () => [props.modelValue, props.contractId],
  ([visible]) => {
    if (visible && props.contractId) load()
  },
  { immediate: true }
)
</script>

<style scoped lang="scss">
.drawer-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.flex-1 { flex: 1; }
.mb { margin-bottom: 8px; }
.rmb { color: var(--el-text-color-secondary); font-size: 12px; }
.att-name { margin: 0 8px 0 4px; }
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 22px 0 14px;
  font-size: 15px;
  color: var(--el-text-color-primary);
  .el-icon { color: var(--el-color-primary); }
}
.flow-timeline {
  padding-left: 4px;
}
.timeline-error { margin-bottom: 12px; }
.flow-node-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.flow-role { font-weight: 600; color: var(--el-text-color-primary); }
.flow-approver { color: var(--el-text-color-regular); font-size: 13px; }
.flow-comment { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 13px; }
.flow-sig {
  margin-top: 6px;
  height: 44px;
  display: block;
  filter: drop-shadow(0 0 0.5px var(--el-mask-color-extra-light));
}
</style>

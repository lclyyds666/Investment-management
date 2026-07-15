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
            <el-button size="small" link type="primary" @click="downloadAttachment">下载</el-button>
          </template>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ contract.remark || '无' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 流转进度 -->
      <h4 class="section-title"><el-icon><Guide /></el-icon> 审批流转进度（{{ APPROVAL_CHAIN.length }} 级）</h4>
      <el-steps :active="stepsActive" align-center :process-status="processStatus" finish-status="success" class="chain-steps">
        <el-step v-for="(r, i) in APPROVAL_CHAIN" :key="r" :title="roleLabel(r)" />
      </el-steps>

      <!-- 流转时间轴（审计日志 + 签章） -->
      <h4 class="section-title"><el-icon><Clock /></el-icon> 合规审计日志</h4>
      <el-timeline class="flow-timeline">
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
                {{ a.action === 'reject' ? '驳回' : '通过' }}
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
import { Printer, Clock, Guide, Document } from '@element-plus/icons-vue'
import { getContract, listApprovals, fetchContractAttachmentBlob, fetchLegalDocBlob } from '@/api/contract'
import { APPROVAL_CHAIN, STATUS_META, roleLabel } from '@/constants/business'
import { digitToRMB } from '@/utils/rmb'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contractId: { type: [Number, String], default: null }
})
defineEmits(['update:modelValue'])

const loading = ref(false)
const contract = ref(null)
const approvals = ref([])
const docLoading = ref(false)

const rmb = computed(() => (contract.value ? digitToRMB(contract.value.amount) : ''))

async function downloadAttachment() {
  if (!contract.value?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(contract.value.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = contract.value.attachment_name
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    ElMessage.error('附件下载失败')
  }
}

const stepsActive = computed(() => {
  const c = contract.value
  if (!c) return 0
  if (c.status === 'approved') return APPROVAL_CHAIN.length
  if (c.status === 'draft') return 0
  return c.current_step // pending / rejected 停留在当前环节
})
const processStatus = computed(() => (contract.value?.status === 'rejected' ? 'error' : 'process'))

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
  try {
    const [c, aps] = await Promise.all([
      getContract(props.contractId),
      listApprovals(props.contractId)
    ])
    contract.value = c
    approvals.value = aps
  } finally {
    loading.value = false
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
.rmb { color: #909399; font-size: 12px; }
.att-name { margin: 0 8px 0 4px; }
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 22px 0 14px;
  font-size: 15px;
  color: #eafcff;
  .el-icon { color: #3f6ad8; }
}
.chain-steps {
  margin-bottom: 8px;
  :deep(.el-step__title) { font-size: 12px; }
}
.flow-timeline {
  padding-left: 4px;
}
.flow-node-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.flow-role { font-weight: 600; color: #eafcff; }
.flow-approver { color: #a9c2e0; font-size: 13px; }
.flow-comment { margin-top: 4px; color: #909399; font-size: 13px; }
.flow-sig {
  margin-top: 6px;
  height: 44px;
  display: block;
  filter: drop-shadow(0 0 0.5px rgba(0, 0, 0, 0.2));
}
</style>

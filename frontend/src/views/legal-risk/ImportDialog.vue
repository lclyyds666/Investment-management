<template>
  <el-dialog v-model="visible" title="导入案件台账" width="760px" destroy-on-close @closed="reset">
    <el-steps :active="step" finish-status="success" align-center>
      <el-step title="选择文件" />
      <el-step title="预检确认" />
      <el-step title="完成导入" />
    </el-steps>

    <div v-if="step === 0" class="import-step">
      <el-form label-position="top">
        <el-form-item v-if="initiatorOptions.length" label="案件发起组织" required>
          <el-select v-model="initiatorAssignmentId" :loading="initiatorOptionsLoading" placeholder="请选择案件发起组织">
            <el-option v-for="option in initiatorOptions" :key="option.assignment_id" :value="option.assignment_id" :label="`${option.company_name} / ${option.organization_name} / ${option.position_name || option.position_code}`" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="代理发起组织编码" required>
          <el-input v-model="organizationCode" :disabled="initiatorOptionsLoading" placeholder="超级管理员请输入发起组织编码" />
        </el-form-item>
      </el-form>
      <el-upload drag :auto-upload="false" accept=".xlsx" :limit="1" :on-change="selectFile" :on-remove="removeFile">
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div>拖入或选择标准 Excel 文件</div>
        <template #tip><span>仅支持本模块下载的 legal-case-v1 标准模板，最大 20 MB</span></template>
      </el-upload>
      <el-button :icon="Download" @click="downloadTemplate">下载标准模板</el-button>
    </div>

    <div v-else-if="step === 1" class="import-step">
      <div class="summary-grid">
        <div><span>校验行</span><strong>{{ batch.total_rows }}</strong></div>
        <div><span>可导入</span><strong>{{ batch.importable_rows }}</strong></div>
        <div><span>警告</span><strong class="warning">{{ batch.warning_rows }}</strong></div>
        <div><span>错误</span><strong class="danger">{{ batch.error_rows }}</strong></div>
      </div>
      <el-alert v-if="batch.error_rows" type="error" :closable="false" show-icon title="存在错误行，修正文件后重新预检。" />
      <el-table :data="issueRows" max-height="320" stripe>
        <el-table-column prop="sheet_name" label="工作表" width="130" />
        <el-table-column prop="row_number" label="行号" width="72" />
        <el-table-column label="校验结果" min-width="280">
          <template #default="{ row }">
            <div v-for="item in row.errors" :key="`e-${item}`" class="danger">{{ item }}</div>
            <div v-for="item in row.warnings" :key="`w-${item}`" class="warning">{{ item }}</div>
          </template>
        </el-table-column>
        <el-table-column v-if="batch.warning_rows" label="确认警告" width="100">
          <template #default="{ row }">
            <el-checkbox v-if="row.warnings?.length && !row.errors?.length" v-model="confirmed[row.id]" />
          </template>
        </el-table-column>
      </el-table>
      <el-button v-if="batch.error_rows" :icon="Download" @click="downloadErrors">下载校验报告</el-button>
    </div>

    <el-result v-else icon="success" title="案件台账导入完成" :sub-title="`已导入 ${result.imported_cases || 0} 个案件`" />

    <template #footer>
      <el-button v-if="step < 2" @click="visible = false">取消</el-button>
      <el-button v-if="step === 0" type="primary" :loading="loading" :disabled="!canPreview" @click="preview">开始预检</el-button>
      <el-button v-if="step === 1" type="primary" :loading="loading" :disabled="!canConfirm" @click="confirm">确认导入</el-button>
      <el-button v-if="step === 2" type="primary" @click="finish">完成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  confirmImport, downloadImportErrors, downloadImportTemplate,
  getImportBatch, listLegalInitiatorOptions, previewImport
} from '@/api/legalRisk'

const emit = defineEmits(['imported'])
const visible = ref(false)
const step = ref(0)
const loading = ref(false)
const file = ref(null)
const initiatorOptions = ref([])
const initiatorOptionsLoading = ref(false)
const initiatorAssignmentId = ref(null)
const organizationCode = ref('')
const batch = reactive({ id: null, total_rows: 0, importable_rows: 0, warning_rows: 0, error_rows: 0, rows: [] })
const confirmed = reactive({})
const result = reactive({ imported_cases: 0 })

const issueRows = computed(() => (batch.rows || []).filter((row) => row.errors?.length || row.warnings?.length))
const warningRows = computed(() => issueRows.value.filter((row) => row.warnings?.length && !row.errors?.length))
const canConfirm = computed(() => !batch.error_rows && warningRows.value.every((row) => confirmed[row.id]))
const ownership = computed(() => ({
  ...(initiatorAssignmentId.value !== null ? { initiator_assignment_id: initiatorAssignmentId.value } : {}),
  ...(organizationCode.value ? { organization_code: organizationCode.value } : {})
}))
const canPreview = computed(() => file.value && !initiatorOptionsLoading.value && (
  initiatorAssignmentId.value !== null || organizationCode.value.trim()
))

const saveBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function loadInitiatorOptions() {
  initiatorOptionsLoading.value = true
  try {
    initiatorOptions.value = await listLegalInitiatorOptions('case')
    if (initiatorOptions.value.length === 1) initiatorAssignmentId.value = initiatorOptions.value[0].assignment_id
  } catch {
    initiatorOptions.value = []
  } finally {
    initiatorOptionsLoading.value = false
  }
}

const open = () => { visible.value = true; loadInitiatorOptions() }
const selectFile = (uploadFile) => { file.value = uploadFile.raw }
const removeFile = () => { file.value = null }

async function downloadTemplate() {
  saveBlob(await downloadImportTemplate(), '法务案件标准导入模板-legal-case-v1.xlsx')
}

async function preview() {
  loading.value = true
  try {
    const data = new FormData()
    data.append('file', file.value)
    Object.entries(ownership.value).forEach(([key, value]) => data.append(key, String(value)))
    const summary = await previewImport(data)
    Object.assign(batch, summary, await getImportBatch(summary.id))
    step.value = 1
  } finally {
    loading.value = false
  }
}

async function confirm() {
  loading.value = true
  try {
    Object.assign(result, await confirmImport(batch.id, warningRows.value.map((row) => row.id), ownership.value))
    step.value = 2
    ElMessage.success('案件台账导入成功')
  } finally {
    loading.value = false
  }
}

async function downloadErrors() {
  saveBlob(await downloadImportErrors(batch.id), `法务案件导入校验报告-${batch.id}.xlsx`)
}

function finish() {
  visible.value = false
  emit('imported')
}

function reset() {
  step.value = 0
  file.value = null
  initiatorAssignmentId.value = null
  organizationCode.value = ''
  Object.assign(batch, { id: null, total_rows: 0, importable_rows: 0, warning_rows: 0, error_rows: 0, rows: [] })
  Object.keys(confirmed).forEach((key) => delete confirmed[key])
  result.imported_cases = 0
}

defineExpose({ open })
</script>

<style scoped>
.import-step { display: grid; gap: 18px; margin-top: 26px; }
.upload-icon { font-size: 40px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--el-border-color-lighter); }
.summary-grid > div { display: flex; min-width: 0; padding: 14px; flex-direction: column; border-right: 1px solid var(--el-border-color-lighter); }
.summary-grid > div:last-child { border-right: 0; }
.summary-grid span { color: var(--el-text-color-secondary); font-size: 12px; }
.summary-grid strong { margin-top: 6px; font-family: var(--font-data); font-size: 22px; }
.warning { color: var(--el-color-warning); }
.danger { color: var(--el-color-danger); }
@media (max-width: 640px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } }
</style>

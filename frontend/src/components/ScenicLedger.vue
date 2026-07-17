<template>
  <div class="scenic-ledger" v-loading="loading">
    <div class="ledger-head">
      <div class="ledger-title">
        <el-icon><Tickets /></el-icon>
        <span>核销数据台账</span>
        <el-tag size="small" effect="plain">共 {{ total }} 条</el-tag>
        <el-tag v-if="sourceFile" size="small" type="info" effect="plain">来源：{{ sourceFile }}</el-tag>
      </div>
      <div class="ledger-ops">
        <el-upload
          :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" :on-change="onFileChange"
        >
          <el-button type="primary" :icon="UploadFilled" :loading="uploading">上传 Excel</el-button>
        </el-upload>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button type="danger" plain :icon="Delete" :disabled="!total" @click="onClear">清空</el-button>
      </div>
    </div>

    <el-alert
      type="info" :closable="false" show-icon class="ledger-tip"
      :title="`当前仅展示【${scenicId}】景区的核销数据；上传的数据自动归属本景区，不与其他景区混淆。`"
    />

    <el-table :data="tableData" border stripe max-height="52vh" size="small">
      <el-table-column type="index" label="#" width="52" align="center" />
      <el-table-column
        v-for="col in columns" :key="col" :prop="col" :label="col"
        min-width="120" show-overflow-tooltip
      />
      <template #empty>该景区暂无核销数据，请上传 Excel 台账</template>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Delete, Tickets } from '@element-plus/icons-vue'
import { getScenicLedger, uploadScenicLedger, clearScenicLedger } from '@/api/scenic'

// scenicId 作为 Props 传入 —— 数据作用域的边界
const props = defineProps({
  scenicId: { type: String, required: true }
})

const loading = ref(false)
const uploading = ref(false)
const columns = ref([])
const rows = ref([])
const sourceFile = ref('')
const total = computed(() => rows.value.length)
// el-table 直接吃每行的 data 对象
const tableData = computed(() => rows.value.map((r) => r.data))

async function load() {
  if (!props.scenicId) return
  loading.value = true
  try {
    const res = await getScenicLedger(props.scenicId)
    columns.value = res.columns || []
    rows.value = res.rows || []
    sourceFile.value = rows.value.length ? (rows.value[rows.value.length - 1].source_file || '') : ''
  } finally {
    loading.value = false
  }
}

async function onFileChange(file) {
  const raw = file?.raw
  if (!raw) return
  const name = (raw.name || '').toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
    ElMessage.error('仅支持 Excel 文件(.xlsx/.xls)')
    return
  }
  if (raw.size > 20 * 1024 * 1024) {
    ElMessage.error('文件超过 20MB 上限')
    return
  }
  uploading.value = true
  try {
    const res = await uploadScenicLedger(props.scenicId, raw)
    ElMessage.success(`已导入 ${res.inserted} 行核销数据`)
    await load()
  } catch {
    ElMessage.error('上传失败，请检查文件内容')
  } finally {
    uploading.value = false
  }
}

async function onClear() {
  try {
    await ElMessageBox.confirm(
      `确定清空【${props.scenicId}】景区的全部核销台账数据吗？此操作不可恢复。`,
      '清空确认',
      { type: 'warning', confirmButtonText: '确定清空', cancelButtonText: '取消' }
    )
  } catch { return }
  try {
    await clearScenicLedger(props.scenicId)
    ElMessage.success('已清空该景区台账')
    await load()
  } catch {
    ElMessage.error('清空失败')
  }
}

// scenicId 变化即切换作用域、重载对应景区数据（严格隔离）
watch(() => props.scenicId, load, { immediate: true })
</script>

<style scoped lang="scss">
.scenic-ledger { margin-top: 8px; }
.ledger-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}
.ledger-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  .el-icon { color: var(--el-color-primary); }
}
.ledger-ops { display: flex; gap: 8px; align-items: center; }
.ledger-tip { margin-bottom: 12px; }
</style>

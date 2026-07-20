<template>
  <div class="ticket-ledger" v-loading="loading">
    <!-- 顶部：标题 + 比例配置 + 操作 -->
    <div class="tl-head">
      <div class="tl-title">
        <el-icon><Tickets /></el-icon>
        <span>门票平台核销业务台账</span>
        <el-tag size="small" effect="plain">共 {{ savedRows.length }} 期</el-tag>
      </div>
      <div class="tl-ops">
        <div class="rate-box">
          <span>核销率</span>
          <el-input-number
            v-model="ratePctHexiao" :min="0" :max="100" :step="1" :precision="2"
            size="small" controls-position="right" style="width: 108px"
          /><span class="pct">%</span>
        </div>
        <div class="rate-box">
          <span>服务费率</span>
          <el-input-number
            v-model="ratePctFee" :min="0" :max="100" :step="1" :precision="2"
            size="small" controls-position="right" style="width: 108px"
          /><span class="pct">%</span>
        </div>
        <el-upload
          :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" multiple
          :on-change="onFileChange"
        >
          <el-button type="primary" :icon="UploadFilled" :loading="parsing">批量上传对账明细</el-button>
        </el-upload>
        <el-button :icon="Refresh" @click="loadSaved">刷新</el-button>
        <el-button
          type="success" plain :icon="Download"
          :disabled="!savedRows.length" @click="onExport"
        >导出Excel</el-button>
      </div>
    </div>

    <el-alert
      type="info" :closable="false" show-icon class="tl-tip"
      title="流程：批量上传对账明细 → 自动识别周期并算出「服务商到账金额」→ 在下表确认/录入「出版应得到账金额」→ 系统按核销率/服务费率算出景区核销、锦盈结算、实收服务费 → 保存生成台账 → 导出标准 Excel。"
    />

    <!-- 待确认区：上传解析后的可编辑草稿表 -->
    <el-card v-if="draftRows.length" shadow="never" class="tl-draft">
      <template #header>
        <div class="draft-header">
          <span><el-icon><EditPen /></el-icon> 待确认台账（{{ draftRows.length }} 期）—— 请录入「出版应得到账金额」与手工字段</span>
          <div>
            <el-radio-group v-model="saveMode" size="small">
              <el-radio-button label="replace">覆盖现有台账</el-radio-button>
              <el-radio-button label="append">追加到台账</el-radio-button>
            </el-radio-group>
            <el-button type="primary" size="small" :icon="Check" :loading="saving" @click="onSave">保存生成台账</el-button>
            <el-button size="small" text @click="draftRows = []">清空草稿</el-button>
          </div>
        </div>
      </template>

      <el-table :data="draftRows" border size="small" class="draft-table">
        <el-table-column label="付款日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.pay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工选择" style="width: 130px" />
          </template>
        </el-table-column>
        <el-table-column label="平台" width="110">
          <template #default="{ row }">
            <el-select v-model="row.platform" size="small" placeholder="选择" style="width: 92px">
              <el-option v-for="p in PLATFORMS" :key="p" :label="p" :value="p" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="景区门票" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.ticket_product" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="核对日期（自动）" width="170" prop="check_date_text" />
        <el-table-column label="服务商到账（自动）" width="140" align="right">
          <template #default="{ row }">{{ fmtMoney(row.supplier_received) }}</template>
        </el-table-column>
        <el-table-column label="出版应得到账金额 ★" width="170" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.publisher_due" :min="0" :precision="2" :step="1000"
              size="small" controls-position="right" style="width: 150px"
            />
          </template>
        </el-table-column>
        <el-table-column label="景区核销金额" width="130" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(calcHexiao(row.publisher_due)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="锦盈结算金额" width="130" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(calcJinying(row.publisher_due)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实收服务费" width="120" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(calcFee(row.publisher_due)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回款日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.repay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工" style="width: 130px" />
          </template>
        </el-table-column>
        <el-table-column label="回款金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.repay_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width: 120px" />
          </template>
        </el-table-column>
        <el-table-column label="来源文件" min-width="200" prop="source_file" show-overflow-tooltip />
      </el-table>
    </el-card>

    <!-- 已保存台账 -->
    <el-table :data="savedRows" border stripe size="small" class="saved-table" :show-summary="savedRows.length > 0" :summary-method="summary">
      <el-table-column type="index" label="#" width="46" align="center" />
      <el-table-column label="付款日期" width="110" prop="pay_date" />
      <el-table-column label="平台" width="80" prop="platform" />
      <el-table-column label="景区门票" min-width="160" prop="ticket_product" show-overflow-tooltip />
      <el-table-column label="核对日期" width="160" prop="check_date_text" />
      <el-table-column label="景区核销金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.hexiao_amount) }}</template>
      </el-table-column>
      <el-table-column label="锦盈结算金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.jinying_amount) }}</template>
      </el-table-column>
      <el-table-column label="实收服务费" width="120" align="right">
        <template #default="{ row }">{{ fmtMoney(row.service_fee) }}</template>
      </el-table-column>
      <el-table-column label="回款日期" width="110" prop="repay_date" />
      <el-table-column label="回款金额" width="130" align="right">
        <template #default="{ row }">{{ row.repay_amount != null ? fmtMoney(row.repay_amount) : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openEdit(row)">回款/编辑</el-button>
          <el-button size="small" text type="danger" @click="onDeleteRow(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无台账，请上传对账明细并保存生成</template>
    </el-table>

    <!-- 编辑单行弹窗（回款为主） -->
    <el-dialog v-model="editVisible" title="编辑台账行" width="440px">
      <el-form label-width="120px" v-if="editRow">
        <el-form-item label="付款日期">
          <el-date-picker v-model="editForm.pay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="editForm.platform" style="width: 100%">
            <el-option v-for="p in PLATFORMS" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="出版应得到账">
          <el-input-number v-model="editForm.publisher_due" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="回款日期">
          <el-date-picker v-model="editForm.repay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="回款金额">
          <el-input-number v-model="editForm.repay_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingEdit" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Download, Tickets, EditPen, Check } from '@element-plus/icons-vue'
import {
  parseTicketFiles, getTicketLedger, saveTicketLedger,
  updateTicketRow, deleteTicketRow, fetchTicketLedgerExportBlob
} from '@/api/ticketLedger'
import { downloadBlob } from '@/utils/file'

const props = defineProps({
  scenicId: { type: String, required: true }
})

const PLATFORMS = ['抖音', '美团', '携程', '同程']

const loading = ref(false)
const parsing = ref(false)
const saving = ref(false)
const savedRows = ref([])
const draftRows = ref([])
const saveMode = ref('replace')

// 比例（百分数展示，默认 90 / 4）
const ratePctHexiao = ref(90)
const ratePctFee = ref(4)
const rateHexiao = computed(() => Number(ratePctHexiao.value) / 100)
const rateFee = computed(() => Number(ratePctFee.value) / 100)

function round2(n) {
  return Math.round((Number(n) || 0) * 100) / 100
}
function calcHexiao(b) { return round2((Number(b) || 0) * rateHexiao.value) }
function calcFee(b) { return round2((Number(b) || 0) * rateFee.value) }
function calcJinying(b) { return round2(calcHexiao(b) + calcFee(b)) }

function fmtMoney(n) {
  const v = Number(n)
  if (Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadSaved() {
  if (!props.scenicId) return
  loading.value = true
  try {
    const res = await getTicketLedger(props.scenicId)
    savedRows.value = res.rows || []
  } finally {
    loading.value = false
  }
}

async function onFileChange(file, fileList) {
  // el-upload multiple 会逐个回调；聚合去重后统一解析一次
  const raws = fileList.map((f) => f.raw).filter(Boolean)
  if (!raws.length) return
  // 校验
  for (const r of raws) {
    const name = (r.name || '').toLowerCase()
    if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
      ElMessage.error(`${r.name}：仅支持 Excel(.xlsx/.xls)`)
      return
    }
  }
  parsing.value = true
  try {
    const res = await parseTicketFiles(props.scenicId, raws)
    ;(res.warnings || []).forEach((w) => ElMessage.warning(w))
    draftRows.value = (res.files || []).map((f) => ({
      pay_date: null,
      platform: '抖音',
      ticket_product: f.ticket_product || '水上世界/童话世界/海洋王国',
      check_date_text: f.check_date_text,
      period_text: f.period_text,
      period_start: f.period_start,
      period_end: f.period_end,
      supplier_received: f.supplier_received,
      publisher_due: Number(f.suggested_publisher_due) || 0,
      order_count: f.order_count,
      repay_date: null,
      repay_amount: null,
      source_file: f.source_file
    }))
    ElMessage.success(`解析完成：成功 ${res.succeeded} 个，失败 ${res.failed} 个。请确认「出版应得到账金额」。`)
  } catch {
    ElMessage.error('解析失败，请检查文件内容')
  } finally {
    parsing.value = false
  }
}

async function onSave() {
  if (!draftRows.value.length) return
  const rows = draftRows.value.map((r) => ({
    pay_date: r.pay_date,
    platform: r.platform,
    ticket_product: r.ticket_product,
    check_date_text: r.check_date_text,
    period_text: r.period_text,
    period_start: r.period_start,
    period_end: r.period_end,
    supplier_received: r.supplier_received,
    publisher_due: r.publisher_due,
    rate_hexiao: rateHexiao.value,
    rate_fee: rateFee.value,
    order_count: r.order_count,
    repay_date: r.repay_date,
    repay_amount: r.repay_amount,
    source_file: r.source_file
  }))
  saving.value = true
  try {
    const res = await saveTicketLedger(props.scenicId, rows, saveMode.value)
    savedRows.value = res.rows || []
    draftRows.value = []
    ElMessage.success('已保存生成台账')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// —— 编辑单行 ——
const editVisible = ref(false)
const editRow = ref(null)
const savingEdit = ref(false)
const editForm = reactive({ pay_date: null, platform: '', publisher_due: 0, repay_date: null, repay_amount: null })

function openEdit(row) {
  editRow.value = row
  editForm.pay_date = row.pay_date
  editForm.platform = row.platform
  editForm.publisher_due = Number(row.publisher_due) || 0
  editForm.repay_date = row.repay_date
  editForm.repay_amount = row.repay_amount != null ? Number(row.repay_amount) : null
  editVisible.value = true
}

async function onSaveEdit() {
  if (!editRow.value) return
  savingEdit.value = true
  try {
    await updateTicketRow(props.scenicId, editRow.value.id, {
      pay_date: editForm.pay_date,
      platform: editForm.platform,
      publisher_due: editForm.publisher_due,
      repay_date: editForm.repay_date,
      repay_amount: editForm.repay_amount
    })
    editVisible.value = false
    await loadSaved()
    ElMessage.success('已更新')
  } catch {
    ElMessage.error('更新失败')
  } finally {
    savingEdit.value = false
  }
}

async function onDeleteRow(row) {
  try {
    await ElMessageBox.confirm(`确定删除该期台账（${row.check_date_text || row.id}）吗？`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await deleteTicketRow(props.scenicId, row.id)
    await loadSaved()
    ElMessage.success('已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function onExport() {
  try {
    const blob = await fetchTicketLedgerExportBlob(props.scenicId)
    downloadBlob(blob, `业务台账-${props.scenicId}.xlsx`)
  } catch {
    ElMessage.error('导出失败')
  }
}

// el-table 合计行
function summary({ columns, data }) {
  const sums = []
  const moneyCols = { 5: 'hexiao_amount', 6: 'jinying_amount', 7: 'service_fee', 9: 'repay_amount' }
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const key = moneyCols[idx]
    if (key) {
      const total = data.reduce((acc, r) => acc + (Number(r[key]) || 0), 0)
      sums[idx] = fmtMoney(total)
    } else {
      sums[idx] = ''
    }
  })
  return sums
}

watch(() => props.scenicId, loadSaved, { immediate: true })
</script>

<style scoped lang="scss">
.ticket-ledger { margin-top: 6px; }
.tl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}
.tl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  .el-icon { color: var(--el-color-primary); }
}
.tl-ops { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.rate-box {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  .pct { color: var(--el-text-color-secondary); }
}
.tl-tip { margin-bottom: 12px; }
.tl-draft { margin-bottom: 16px; border: 1px solid var(--el-color-primary-light-5); }
.draft-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  font-weight: 600;
  > div { display: flex; align-items: center; gap: 8px; }
}
.draft-table :deep(.el-table__cell) { padding: 4px 0; }
.calc { color: var(--el-color-primary); font-weight: 600; }
.saved-table { margin-top: 4px; }
</style>

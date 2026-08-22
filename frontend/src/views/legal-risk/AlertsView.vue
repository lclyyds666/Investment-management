<template>
  <section class="alerts-page">
    <header class="page-head">
      <div><span>DEADLINE CONTROL</span><h1>预警任务</h1></div>
      <div class="head-actions">
        <el-button v-if="isSuperuser" :icon="Connection" :loading="testing" @click="testRobot">测试钉钉</el-button>
        <el-button v-if="isSuperuser" :icon="RefreshRight" :loading="scanning" @click="runScan">立即扫描</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </header>

    <div class="alert-summary">
      <button type="button" @click="setStatus('pending')"><span>待处理</span><strong>{{ counts.pending }}</strong></button>
      <button type="button" @click="setStatus('processing')"><span>处理中</span><strong>{{ counts.processing }}</strong></button>
      <button type="button" @click="filters.level = 'critical'; search()"><span>紧急事项</span><strong class="critical">{{ counts.critical }}</strong></button>
      <button type="button" @click="setStatus('completed')"><span>已完成</span><strong>{{ counts.completed }}</strong></button>
    </div>

    <div class="filter-band">
      <el-select v-model="filters.status" clearable placeholder="处理状态">
        <el-option v-for="item in ALERT_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.alert_type" clearable placeholder="预警类型">
        <el-option v-for="item in ALERT_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.level" clearable placeholder="预警级别">
        <el-option label="紧急" value="critical" /><el-option label="警告" value="warning" /><el-option label="一般" value="normal" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="search">查询</el-button>
      <el-button :icon="Refresh" @click="reset">重置</el-button>
    </div>

    <div class="table-shell" v-loading="loading">
      <el-table :data="page.items" stripe>
        <el-table-column label="级别" width="86"><template #default="{ row }"><el-tag :type="levelType(row.level)" effect="dark">{{ levelLabel(row.level) }}</el-tag></template></el-table-column>
        <el-table-column label="预警事项" min-width="190"><template #default="{ row }">{{ alertTypeLabel(row.alert_type) }}</template></el-table-column>
        <el-table-column label="案件" width="120"><template #default="{ row }"><el-button link type="primary" @click="openCase(row.case_id)">案件 #{{ row.case_id }}</el-button></template></el-table-column>
        <el-table-column prop="trigger_date" label="触发日" width="110" />
        <el-table-column prop="due_date" label="截止日" width="110" />
        <el-table-column label="处理状态" width="105"><template #default="{ row }"><el-tag effect="plain">{{ alertStatusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="result" label="处理结果" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" min-width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManageAlerts && row.status === 'pending'" link type="primary" @click="start(row)">开始办理</el-button>
            <el-button v-if="canManageAlerts && ['pending', 'processing'].includes(row.status)" data-test="complete-alert" link type="success" @click="openFinish(row, 'complete')">完成</el-button>
            <el-button v-if="canManageAlerts && ['pending', 'processing'].includes(row.status)" link type="info" @click="openFinish(row, 'close')">关闭</el-button>
            <el-button link @click="showDeliveries(row)">投递记录</el-button>
            <el-button v-if="isSuperuser" link type="warning" @click="resend(row)">重发</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !page.items.length" description="暂无符合条件的预警" />
      <el-pagination v-if="page.total" v-model:current-page="filters.page" v-model:page-size="filters.page_size" :total="page.total" layout="total, sizes, prev, pager, next" @change="load" />
    </div>

    <el-dialog v-model="finishDialog.visible" :title="finishDialog.action === 'complete' ? '完成预警' : '关闭预警'" width="520px">
      <el-form ref="finishForm" :model="finishDialog" :rules="{ result: [{ required: true, message: '请填写处理结果', trigger: 'blur' }] }" label-position="top">
        <el-form-item label="处理结果" prop="result"><el-input v-model="finishDialog.result" type="textarea" :rows="5" maxlength="2000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button @click="finishDialog.visible = false">取消</el-button><el-button type="primary" :loading="finishDialog.saving" @click="submitFinish">确认</el-button></template>
    </el-dialog>

    <el-drawer v-model="deliveryDrawer" title="钉钉投递记录" size="560px">
      <el-table :data="deliveries" stripe>
        <el-table-column prop="stage_key" label="提醒阶段" min-width="110" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="attempts" label="次数" width="70" />
        <el-table-column prop="last_sent_at" label="最后发送" min-width="160" />
        <el-table-column prop="failure_reason" label="失败原因" min-width="180" show-overflow-tooltip />
      </el-table>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Connection, Refresh, RefreshRight, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  closeAlert, completeAlert, getAlertCounts, getAlertDeliveries, listAlerts,
  resendAlert, scanAlerts, startAlert, testDingTalk
} from '@/api/legalRisk'
import { useLegalAlertsStore } from '@/store/legalAlerts'
import { usePortalStore } from '@/store/portal'
import { ALERT_STATUS_OPTIONS, ALERT_TYPE_OPTIONS, alertStatusLabel, alertTypeLabel, cleanParams } from '@/constants/legalRisk'
import { LEGAL_CAPABILITIES, hasLegalCapability } from '@/utils/legalCapabilities'

const route = useRoute()
const router = useRouter()
const portalStore = usePortalStore()
const alertStore = useLegalAlertsStore()
const isSuperuser = computed(() => portalStore.isSuperuser)
const canManageAlerts = computed(() => hasLegalCapability(
  portalStore.permissions?.permissions || [],
  LEGAL_CAPABILITIES.MANAGE_ALERT,
  isSuperuser.value
))
const loading = ref(false)
const scanning = ref(false)
const testing = ref(false)
const deliveryDrawer = ref(false)
const deliveries = ref([])
const finishForm = ref()
const page = reactive({ items: [], total: 0 })
const counts = reactive({ pending: 0, processing: 0, completed: 0, critical: 0 })
const filters = reactive({ status: String(route.query.status || ''), alert_type: '', level: '', page: 1, page_size: 20 })
const finishDialog = reactive({ visible: false, saving: false, action: 'complete', row: null, result: '' })

const levelLabel = (v) => ({ critical: '紧急', warning: '警告', normal: '一般' }[v] || v)
const levelType = (v) => ({ critical: 'danger', warning: 'warning', normal: 'info' }[v] || 'info')
const openCase = (id) => router.push(`/investment/legal-risk/cases/${id}`)

async function load() {
  loading.value = true
  try {
    const [data, badge, pending, processing, completed] = await Promise.all([
      listAlerts(cleanParams(filters)), getAlertCounts(),
      listAlerts({ status: 'pending', page: 1, page_size: 1 }),
      listAlerts({ status: 'processing', page: 1, page_size: 1 }),
      listAlerts({ status: 'completed', page: 1, page_size: 1 })
    ])
    Object.assign(page, data)
    Object.assign(counts, { critical: badge.critical || 0, pending: pending.total, processing: processing.total, completed: completed.total })
    alertStore.refresh()
  } finally { loading.value = false }
}
function search() { filters.page = 1; load() }
function reset() { Object.assign(filters, { status: '', alert_type: '', level: '', page: 1, page_size: 20 }); load() }
function setStatus(status) { filters.status = status; search() }
async function start(row) { await startAlert(row.id); ElMessage.success('预警已进入办理'); load() }
function openFinish(row, action) { Object.assign(finishDialog, { visible: true, action, row, result: '' }) }
async function submitFinish() {
  await finishForm.value.validate()
  finishDialog.saving = true
  try {
    const fn = finishDialog.action === 'complete' ? completeAlert : closeAlert
    await fn(finishDialog.row.id, finishDialog.result)
    finishDialog.visible = false
    ElMessage.success(finishDialog.action === 'complete' ? '预警已完成' : '预警已关闭')
    load()
  } finally { finishDialog.saving = false }
}
async function showDeliveries(row) { deliveries.value = await getAlertDeliveries(row.id); deliveryDrawer.value = true }
async function resend(row) { await resendAlert(row.id); ElMessage.success('已创建钉钉重发任务'); showDeliveries(row) }
async function runScan() {
  scanning.value = true
  try { const result = await scanAlerts(); ElMessage.success(`扫描完成，新增 ${result.alerts_created} 项预警`); load() } finally { scanning.value = false }
}
async function testRobot() {
  testing.value = true
  try { await testDingTalk(); ElMessage.success('钉钉测试消息发送成功') } finally { testing.value = false }
}
onMounted(load)
</script>

<style scoped>
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 16px; padding: 4px 0 16px 16px; border-bottom: 1px solid var(--el-border-color-lighter); border-left: 4px solid var(--brand-vermilion); }
.page-head span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; letter-spacing: 0; }
.page-head h1 { margin: 4px 0 0; font-size: 25px; letter-spacing: 0; }
.head-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.alert-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px; border: 1px solid var(--el-border-color-lighter); }
.alert-summary button { display: flex; min-height: 86px; padding: 16px 20px; flex-direction: column; align-items: flex-start; border: 0; border-right: 1px solid var(--el-border-color-lighter); color: inherit; background: var(--surface-solid); cursor: pointer; }
.alert-summary button:last-child { border-right: 0; }
.alert-summary span { color: var(--el-text-color-secondary); font-size: 12px; }
.alert-summary strong { margin-top: 8px; font-family: var(--font-data); font-size: 25px; }
.alert-summary .critical { color: var(--el-color-danger); }
.filter-band { display: grid; grid-template-columns: repeat(3, minmax(150px, 1fr)) auto auto; gap: 10px; margin-bottom: 14px; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); }
.table-shell { min-width: 0; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); overflow-x: auto; }
@media (max-width: 780px) { .page-head { align-items: flex-start; flex-direction: column; } .alert-summary { grid-template-columns: repeat(2, 1fr); } .filter-band { grid-template-columns: 1fr; } }
</style>

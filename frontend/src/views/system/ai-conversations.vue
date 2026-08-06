<template>
  <main class="audit-page">
    <header class="audit-page__header">
      <div>
        <p class="section-kicker">系统管理 / AI</p>
        <h1>AI 会话审计</h1>
        <p class="audit-page__intro">信息维护员可查看会话运行记录，并按规定原因清理内容。</p>
      </div>
      <el-tag type="info" effect="plain">只读查看 · 超级管理员</el-tag>
    </header>

    <el-alert v-if="loadError" title="审计数据加载失败，请重试。" type="error" :closable="false" show-icon class="audit-page__alert" />

    <el-tabs v-model="activeTab" class="audit-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="会话列表" name="conversations">
        <el-form class="filter-form" inline @submit.prevent="loadConversations(1)">
          <el-form-item label="用户">
            <el-input v-model="filters.userId" placeholder="用户 ID" clearable style="width: 130px" />
          </el-form-item>
          <el-form-item label="开始日期">
            <el-date-picker v-model="filters.startedAt" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" clearable />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="filters.endedAt" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" clearable />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filters.status" placeholder="全部" clearable style="width: 130px">
              <el-option label="活跃" value="active" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input v-model="filters.keyword" placeholder="标题或消息关键词" clearable style="width: 190px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadConversations(1)">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="loading" :data="conversations" row-key="id" class="audit-table" @row-click="openDetail">
          <el-table-column prop="id" label="会话 ID" width="100" />
          <el-table-column prop="owner_id" label="用户 ID" width="100" />
          <el-table-column prop="title" label="会话标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }"><el-tag size="small" type="success">{{ statusLabel(row.status) }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="last_active_at" label="最近活动" min-width="180" />
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openDetail(row)">查看详情</el-button>
              <el-button link type="danger" @click.stop="openDelete(row)">清理会话</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="暂无会话记录" /></template>
        </el-table>

        <div class="pagination-row">
          <span>共 {{ total }} 条</span>
          <el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50]" layout="sizes, prev, pager, next" @current-change="loadConversations" @size-change="loadConversations(1)" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="删除审计" name="audits">
        <el-table v-loading="auditLoading" :data="audits" row-key="id" class="audit-table">
          <el-table-column prop="id" label="记录 ID" width="100" />
          <el-table-column prop="conversation_id" label="原会话 ID" width="110" />
          <el-table-column prop="owner_id" label="原用户 ID" width="110" />
          <el-table-column prop="actor_id" label="操作人 ID" width="110" />
          <el-table-column prop="mode" label="清理方式" width="110" />
          <el-table-column prop="deleted_message_count" label="消息数" width="90" />
          <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
          <el-table-column prop="deleted_at" label="时间" min-width="180" />
          <template #empty><el-empty description="暂无删除审计" /></template>
        </el-table>
        <div class="pagination-row">
          <span>共 {{ auditTotal }} 条</span>
          <el-pagination v-model:current-page="auditPage" v-model:page-size="auditSize" :total="auditTotal" layout="prev, pager, next" @current-change="loadAudits" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailVisible" title="会话详情（只读）" size="min(88vw, 760px)">
      <template v-if="detail">
        <dl class="detail-meta">
          <div><dt>会话 ID</dt><dd>{{ detail.id }}</dd></div>
          <div><dt>用户 ID</dt><dd>{{ detail.owner_id }}</dd></div>
          <div><dt>标题</dt><dd>{{ detail.title }}</dd></div>
          <div><dt>最近活动</dt><dd>{{ detail.last_active_at }}</dd></div>
        </dl>
        <section class="detail-messages" aria-label="会话消息">
          <article v-for="message in detail.messages || []" :key="message.id" class="detail-message">
            <header><strong>{{ message.role === 'user' ? '用户' : 'AI 助手' }}</strong><span>{{ message.status }}</span></header>
            <p>{{ message.content }}</p>
            <small v-if="message.tool_calls?.length">已记录 {{ message.tool_calls.length }} 个授权数据工具调用</small>
          </article>
          <el-empty v-if="!detail.messages?.length" description="暂无消息" />
        </section>
      </template>
      <el-skeleton v-else :rows="6" animated />
    </el-drawer>

    <el-dialog v-model="deleteVisible" title="清理 AI 会话" width="min(92vw, 520px)" @closed="resetDeleteDialog">
      <p class="delete-warning">清理会永久删除会话消息和工具轨迹，仅保留不含内容的删除审计记录。</p>
      <el-form label-position="top">
        <el-form-item label="清理原因（2-200 字）" required>
          <el-input v-model="deleteReason" type="textarea" :rows="4" maxlength="200" show-word-limit placeholder="请输入可追溯的业务原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button data-testid="confirm-admin-delete" type="danger" :loading="deleting" :disabled="!canDelete" @click="confirmDelete">确认清理</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '@/api/aiAssistant'

const activeTab = ref('conversations')
const loading = ref(false)
const auditLoading = ref(false)
const loadError = ref(false)
const conversations = ref([])
const audits = ref([])
const total = ref(0)
const auditTotal = ref(0)
const page = ref(1)
const size = ref(20)
const auditPage = ref(1)
const auditSize = ref(20)
const detailVisible = ref(false)
const detail = ref(null)
const deleteVisible = ref(false)
const deleting = ref(false)
const deleteReason = ref('')
const deleteTarget = ref(null)
const filters = reactive({ userId: '', startedAt: '', endedAt: '', status: '', keyword: '' })

const canDelete = computed(() => {
  const value = deleteReason.value.trim()
  return value.length >= 2 && value.length <= 200 && !deleting.value
})

function statusLabel(value) {
  return value === 'active' ? '活跃' : value || '未知'
}

function dateBoundary(value, end = false) {
  if (!value) return undefined
  return `${value}T${end ? '23:59:59' : '00:00:00'}`
}

function conversationParams(targetPage = page.value) {
  const params = { page: targetPage, size: size.value }
  if (filters.userId.trim()) params.user_id = Number(filters.userId)
  if (filters.startedAt) params.started_at = dateBoundary(filters.startedAt)
  if (filters.endedAt) params.ended_at = dateBoundary(filters.endedAt, true)
  if (filters.status) params.status = filters.status
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  return params
}

async function loadConversations(targetPage = page.value) {
  page.value = targetPage
  loading.value = true
  loadError.value = false
  try {
    const result = await api.listAdminConversations(conversationParams(targetPage))
    conversations.value = result?.items || []
    total.value = result?.total || 0
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function loadAudits(targetPage = auditPage.value) {
  auditPage.value = targetPage
  auditLoading.value = true
  try {
    const result = await api.listDeletionAudits({ page: targetPage, size: auditSize.value })
    audits.value = result?.items || []
    auditTotal.value = result?.total || 0
  } catch {
    loadError.value = true
  } finally {
    auditLoading.value = false
  }
}

function handleTabChange(name) {
  if (name === 'audits' && !audits.value.length && !auditTotal.value) loadAudits(1)
}

function resetFilters() {
  Object.assign(filters, { userId: '', startedAt: '', endedAt: '', status: '', keyword: '' })
  loadConversations(1)
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await api.getAdminConversation(row.id)
  } catch {
    detailVisible.value = false
  }
}

function openDelete(row) {
  deleteTarget.value = row
  deleteReason.value = ''
  deleteVisible.value = true
}

async function confirmDelete() {
  if (!canDelete.value || !deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteAdminConversation(deleteTarget.value.id, deleteReason.value.trim())
    ElMessage.success('会话已清理，删除审计已记录。')
    deleteVisible.value = false
    await Promise.all([loadConversations(Math.min(page.value, Math.max(1, Math.ceil((total.value - 1) / size.value)))), loadAudits(auditPage.value)])
  } catch {
    ElMessage.error('会话清理失败，请稍后重试。')
  } finally {
    deleting.value = false
  }
}

function resetDeleteDialog() {
  deleteReason.value = ''
  deleteTarget.value = null
}

onMounted(() => loadConversations(1))
</script>

<style scoped>
.audit-page {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: 24px clamp(16px, 2.4vw, 36px) 36px;
}

.audit-page__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
}

.section-kicker {
  margin: 0 0 5px;
  color: var(--brand-vermilion);
  font-family: var(--font-data);
  font-size: 11px;
  font-weight: 750;
}

h1 { margin: 0; color: var(--el-text-color-primary); font-family: var(--font-display); font-size: 24px; }
.audit-page__intro { margin: 8px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.audit-page__alert { margin-bottom: 16px; }
.audit-tabs { min-height: 420px; }
.filter-form { padding: 16px; border: 1px solid var(--surface-border); background: var(--surface-muted); }
.audit-table { margin-top: 14px; }
.pagination-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 16px; color: var(--el-text-color-secondary); font-size: 12px; }
.detail-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 0 0 20px; }
.detail-meta div { padding: 10px 12px; border: 1px solid var(--surface-border); background: var(--surface-muted); }
.detail-meta dt { color: var(--el-text-color-secondary); font-size: 12px; }
.detail-meta dd { margin: 4px 0 0; color: var(--el-text-color-primary); overflow-wrap: anywhere; }
.detail-messages { display: grid; gap: 12px; }
.detail-message { padding: 13px; border-left: 3px solid var(--brand-lake); background: var(--surface-muted); }
.detail-message header { display: flex; justify-content: space-between; gap: 12px; color: var(--el-text-color-secondary); font-size: 12px; }
.detail-message p { margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--el-text-color-regular); line-height: 1.7; }
.detail-message small { display: block; margin-top: 8px; color: var(--el-text-color-placeholder); }
.delete-warning { margin-top: 0; color: var(--el-color-danger); line-height: 1.6; }
@media (max-width: 719px) {
  .audit-page { padding: 16px 12px 28px; }
  .audit-page__header { align-items: flex-start; flex-direction: column; }
  .filter-form { display: grid; grid-template-columns: minmax(0, 1fr); }
  .filter-form .el-form-item { margin-right: 0; }
  .pagination-row { align-items: flex-start; flex-direction: column; }
  .detail-meta { grid-template-columns: minmax(0, 1fr); }
}
</style>

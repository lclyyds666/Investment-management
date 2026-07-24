<template>
  <div class="customer">
    <ProTable
      ref="tableRef"
      title="客户档案管理"
      :fetch="listCustomers"
      :columns="columns"
      :search-keys="['name', 'customer_code', 'contact']"
      search-placeholder="搜索客户名称 / ID / 联系人"
      empty-text="暂无客户数据"
    >
      <template #toolbar>
        <el-button v-if="canEdit" type="primary" :icon="Plus" @click="openCreate">新建客户</el-button>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
      </template>

      <template #material="{ row }">
        <el-tag v-if="row.material_count" type="success" size="small" effect="plain">
          {{ row.material_count }} 个附件
        </el-tag>
        <span v-else class="muted">—</span>
      </template>

      <template #actions="{ row }">
        <el-button size="small" link :icon="View" @click="openView(row)">查看</el-button>
        <el-button size="small" type="success" link :icon="MagicStick" @click="openResearch(row)">AI</el-button>
        <el-button v-if="canEdit" size="small" type="primary" link class="op-edit" :icon="Edit" @click="openEdit(row)">编辑</el-button>
        <el-button v-if="canEdit" size="small" type="danger" link :icon="Delete" @click="onDelete(row)">删除</el-button>
      </template>
    </ProTable>

    <!-- 新建/编辑 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑客户' : '新建客户'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" class="customer-form">
        <el-form-item label="客户ID" prop="customer_code">
          <el-input v-model="form.customer_code" :disabled="isEdit" placeholder="如 KH-010" />
        </el-form-item>
        <el-form-item label="客户名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="社会信用代码" prop="social_credit_code"><el-input v-model="form.social_credit_code" placeholder="统一社会信用代码(18 位大写字母/数字)" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="联系人"><el-input v-model="form.contact" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="电话" prop="phone"><el-input v-model="form.phone" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item label="资料">
          <div class="files">
            <!-- 已入库资料（biz_customer_material，查看/AI 同源）；编辑态可即时删除 -->
            <el-tag
              v-for="m in dialogMaterials"
              :key="'m' + m.id"
              type="success"
              closable
              @close="removeExistingMaterial(m)"
              class="file-tag"
            >
              <el-icon><Document /></el-icon> {{ m.filename }}
            </el-tag>
            <!-- 本次待上传：保存时统一提交并解析入库 -->
            <el-tag
              v-for="(f, i) in pendingFiles"
              :key="'p' + i"
              closable
              @close="pendingFiles.splice(i, 1)"
              class="file-tag"
            >
              <el-icon><Document /></el-icon> {{ f.name }}（待上传）
            </el-tag>
          </div>
          <el-upload
            action="#" multiple :auto-upload="false" :show-file-list="false"
            accept=".pdf,.docx,.xlsx" :on-change="onFileChange"
          >
            <el-button size="small" :icon="UploadFilled">上传资料（PDF / Word / Excel）</el-button>
          </el-upload>
          <div class="upload-hint">保存后自动解析入库，「查看」与「AI 分析」将同步读取</div>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看 -->
    <el-drawer v-model="viewVisible" title="客户详情" size="520px">
      <el-descriptions v-if="current" :column="1" border>
        <el-descriptions-item label="客户ID">{{ current.customer_code }}</el-descriptions-item>
        <el-descriptions-item label="客户名称">{{ current.name }}</el-descriptions-item>
        <el-descriptions-item label="社会信用代码">{{ current.social_credit_code || '—' }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ current.contact || '—' }}</el-descriptions-item>
        <el-descriptions-item label="电话">{{ current.phone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="地址">{{ current.address || '—' }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ current.remark || '无' }}</el-descriptions-item>
        <el-descriptions-item label="资料">
          <div v-if="viewMaterials.length">
            <div v-for="m in viewMaterials" :key="m.id" class="file-line">
              <el-icon><Document /></el-icon>
              <span class="fname">{{ m.filename }}</span>
              <el-button size="small" link type="primary" @click="previewFile(m)">预览</el-button>
              <el-button size="small" link @click="downloadFile(m)">下载</el-button>
            </div>
          </div>
          <span v-else class="muted">无（可在「编辑」或「AI」中上传资料）</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>

    <!-- AI 智能调研 -->
    <CustomerResearchDialog v-model="researchVisible" :customer="researchCustomer" />
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, View, Edit, Delete, Document, UploadFilled, MagicStick } from '@element-plus/icons-vue'
import { listCustomers, createCustomer, updateCustomer, deleteCustomer, listMaterials, uploadMaterials, deleteMaterial, fetchMaterialBlob } from '@/api/customer'
import CustomerResearchDialog from '@/components/CustomerResearchDialog.vue'
import ProTable from '@/components/ProTable.vue'
import { computed } from 'vue'
import { ROLES } from '@/constants/business'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
// 新建/编辑/删除客户档案：仅业务经办 + 信息维护(超管)
const canEdit = computed(() => userStore.isSuperuser || userStore.role === ROLES.BUSINESS_HANDLER)

const columns = [
  { prop: 'customer_code', label: '客户ID', width: 120 },
  { prop: 'name', label: '客户名称', minWidth: 200, showOverflowTooltip: true },
  { prop: 'contact', label: '联系人', width: 110 },
  { prop: 'phone', label: '电话', width: 150 },
  { prop: 'address', label: '地址', minWidth: 180, showOverflowTooltip: true },
  { label: '资料', width: 120, align: 'center', slot: 'material' },
  { label: '操作', width: 270, align: 'center', fixed: 'right', slot: 'actions' }
]

const tableRef = ref()
const reload = () => tableRef.value?.reload()

const dialogVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const emptyForm = () => ({ customer_code: '', name: '', social_credit_code: '', contact: '', phone: '', address: '', remark: '' })
const form = reactive(emptyForm())
// 资料统一走真实 materials 表：dialogMaterials 为已入库项，pendingFiles 为本次待上传文件
const dialogMaterials = ref([])
const pendingFiles = ref([])
const ALLOW_EXT = ['.pdf', '.docx', '.xlsx']
// 选填字段仅在非空时校验格式(避免空值被 pattern 拦截)
const optional = (re, message) => ({
  validator: (_r, v, cb) => (!v || re.test(v) ? cb() : cb(new Error(message))),
  trigger: 'blur'
})
const rules = {
  customer_code: [{ required: true, message: '请输入客户ID', trigger: 'blur' }],
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  social_credit_code: [optional(/^[0-9A-Z]{18}$/, '统一社会信用代码应为 18 位大写字母或数字')],
  phone: [optional(/^(1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$/, '请输入有效的手机号或座机号')]
}
function openCreate() {
  isEdit.value = false; editingId.value = null
  dialogMaterials.value = []; pendingFiles.value = []
  Object.assign(form, emptyForm()); formRef.value?.clearValidate?.(); dialogVisible.value = true
}
async function openEdit(row) {
  isEdit.value = true; editingId.value = row.id
  pendingFiles.value = []; dialogMaterials.value = []
  Object.assign(form, {
    customer_code: row.customer_code, name: row.name, social_credit_code: row.social_credit_code || '',
    contact: row.contact, phone: row.phone,
    address: row.address, remark: row.remark
  })
  formRef.value?.clearValidate?.(); dialogVisible.value = true
  // 载入该客户已入库资料（与查看/AI 同一数据源）
  try { dialogMaterials.value = await listMaterials(row.id) } catch { /* 资料加载失败不阻断编辑 */ }
}
function onFileChange(file) {
  const raw = file?.raw
  if (!raw) return
  const name = (raw.name || '').toLowerCase()
  if (!ALLOW_EXT.some((e) => name.endsWith(e))) {
    ElMessage.warning(`仅支持 PDF / Word(.docx) / Excel(.xlsx)：已忽略 ${raw.name}`)
    return
  }
  pendingFiles.value.push(raw)
}
// 编辑态即时删除已入库资料
async function removeExistingMaterial(m) {
  try {
    await deleteMaterial(editingId.value, m.id)
    dialogMaterials.value = dialogMaterials.value.filter((x) => x.id !== m.id)
    ElMessage.success('已删除该资料')
  } catch { ElMessage.error('删除失败') }
}
async function onSave() {
  await formRef.value?.validate()
  saving.value = true
  try {
    let cid = editingId.value
    if (isEdit.value) {
      const { customer_code, ...rest } = form
      await updateCustomer(editingId.value, { ...rest })
    } else {
      const created = await createCustomer({ ...form })
      cid = created?.id
    }
    // 资料：客户存好后统一走真实上传接口，落入 biz_customer_material（查看/AI 同源）
    if (pendingFiles.value.length && cid) {
      try {
        const res = await uploadMaterials(cid, pendingFiles.value)
        const okCount = res?.succeeded?.length || 0
        const failed = res?.failed || []
        if (failed.length) {
          ElMessage.warning(`资料上传成功 ${okCount} 个，失败 ${failed.length} 个`)
        }
      } catch {
        ElMessage.warning('客户已保存，但资料上传失败，请在编辑中重试')
      }
    }
    ElMessage.success(isEdit.value ? '修改成功' : '创建成功')
    dialogVisible.value = false; reload()
  } finally { saving.value = false }
}
async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  await deleteCustomer(row.id); ElMessage.success('删除成功'); reload()
}

const viewVisible = ref(false)
const current = ref(null)
const viewMaterials = ref([])
async function openView(row) {
  current.value = row
  viewVisible.value = true
  viewMaterials.value = []
  try { viewMaterials.value = await listMaterials(row.id) } catch { /* 忽略资料加载失败 */ }
}
async function previewFile(m) {
  try {
    const blob = await fetchMaterialBlob(current.value.id, m.id)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch { ElMessage.error('预览失败') }
}
async function downloadFile(m) {
  try {
    const blob = await fetchMaterialBlob(current.value.id, m.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = m.filename
    a.click()
    URL.revokeObjectURL(a.href)
  } catch { ElMessage.error('下载失败') }
}

// AI 智能调研
const researchVisible = ref(false)
const researchCustomer = ref({})
function openResearch(row) { researchCustomer.value = row; researchVisible.value = true }
</script>

<style scoped lang="scss">
/* 表单标签不换行，避免「社会信用代码」等长标签跨行 */
.customer-form :deep(.el-form-item__label) { white-space: nowrap; }
.muted { color: var(--el-text-color-placeholder); }
.files { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; width: 100%; }
.file-tag { display: inline-flex; align-items: center; gap: 4px; }
.upload-hint { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.4; }
.file-line { display: flex; align-items: center; gap: 6px; padding: 3px 0; }

/* 「编辑」按钮:无背景色,文字随主题自适应(暗黑近白 / 明亮深色)+ 轻微加粗 */
:deep(.op-edit.el-button.is-link) {
  color: var(--el-text-color-primary);
  font-weight: 600;
  background-color: transparent;
}
:deep(.op-edit.el-button.is-link:hover),
:deep(.op-edit.el-button.is-link:focus) {
  color: var(--el-color-primary);
  background-color: transparent;
}
</style>

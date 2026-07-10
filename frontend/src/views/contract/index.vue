<template>
  <div class="contract" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header"><span>合同管理</span></div>
      </template>

      <!-- 工具栏：新建 + 搜索 + 刷新 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索合同编号 / 名称 / 客户 / 乙方" clearable class="search-input">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="toolbar-right">
          <el-button v-if="isBusinessHandler" type="primary" :icon="Plus" @click="openCreate">
            新建合同
          </el-button>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </div>

      <el-table :data="filteredList" border stripe>
        <el-table-column prop="contract_no" label="合同编号" width="150" />
        <el-table-column prop="title" label="合同名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="130" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.contract_type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户" min-width="130" show-overflow-tooltip />
        <el-table-column label="金额(元)" width="130" align="right">
          <template #default="{ row }">{{ Number(row.amount).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="状态 / 当前环节" width="160" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_META[row.status]?.type">{{ row.status_label }}</el-tag>
            <div v-if="row.current_role_label" class="cur-role">→ {{ row.current_role_label }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" align="center">
          <template #default="{ row }">
            <el-button size="small" link :icon="View" @click="openDetail(row)">详情</el-button>
            <template v-if="isBusinessHandler && ['draft', 'rejected'].includes(row.status)">
              <el-button size="small" type="primary" link :icon="Edit" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="primary" link @click="onSubmit(row)">提交审批</el-button>
              <el-button size="small" type="danger" link :icon="Delete" @click="onDelete(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>暂无合同数据</template>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑合同 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑合同' : '新建合同'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="单据类型" prop="contract_type">
          <el-radio-group v-model="form.contract_type">
            <el-radio-button :value="CONTRACT_TYPES.PAYMENT">业务付款审批单</el-radio-button>
            <el-radio-button :value="CONTRACT_TYPES.BUSINESS">业务审批单</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="合同编号" prop="contract_no">
          <el-input v-model="form.contract_no" :disabled="isEdit" placeholder="如 HT-2026-010" />
        </el-form-item>
        <el-form-item label="合同名称" prop="title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="申请部门"><el-input v-model="form.department" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务类型"><el-input v-model="form.business_type" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="客户名称"><el-input v-model="form.customer_name" /></el-form-item>
        <el-form-item label="乙方"><el-input v-model="form.party_b" /></el-form-item>
        <el-form-item label="金额(元)" prop="amount">
          <el-input-number v-model="form.amount" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="签订日期">
          <el-date-picker v-model="form.sign_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
        <el-form-item label="合同附件">
          <el-upload
            class="upload-mock"
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-exceed="() => ElMessage.warning('仅可上传一个附件（演示）')"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">点击或拖拽文件到此处<em>上传合同附件</em></div>
            <template #tip>
              <div class="upload-tip">支持 PDF / Word / 图片，单个 ≤ 20MB（演示区域，不会真实上传）</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 合同详情（流转时间轴 + 打印审批单） -->
    <ContractDetailDrawer v-model="detailVisible" :contract-id="detailId" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Edit, Delete, Refresh, View, UploadFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { ROLES, CONTRACT_TYPES, STATUS_META } from '@/constants/business'
import ContractDetailDrawer from '@/components/ContractDetailDrawer.vue'
import {
  listContracts, createContract, updateContract, deleteContract, submitContract
} from '@/api/contract'

const userStore = useUserStore()
const isBusinessHandler = computed(
  () => userStore.role === ROLES.BUSINESS_HANDLER || userStore.isSuperuser
)

const loading = ref(false)
const list = ref([])
const keyword = ref('')
const filteredList = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return list.value
  return list.value.filter((c) =>
    [c.contract_no, c.title, c.customer_name, c.party_b]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  )
})

async function load() {
  loading.value = true
  try {
    list.value = await listContracts()
  } finally {
    loading.value = false
  }
}

// 新建 / 编辑
const dialogVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const emptyForm = () => ({
  contract_no: '',
  title: '',
  contract_type: CONTRACT_TYPES.PAYMENT,
  department: '',
  business_type: '',
  customer_name: '',
  party_a: '山东出版供应链管理公司',
  party_b: '',
  amount: 0,
  sign_date: null,
  remark: ''
})
const form = reactive(emptyForm())
const rules = {
  contract_no: [{ required: true, message: '请输入合同编号', trigger: 'blur' }],
  title: [{ required: true, message: '请输入合同名称', trigger: 'blur' }]
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  Object.assign(form, emptyForm())
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true
  editingId.value = row.id
  Object.assign(form, {
    contract_no: row.contract_no,
    title: row.title,
    contract_type: row.contract_type,
    department: row.department,
    business_type: row.business_type,
    customer_name: row.customer_name,
    party_a: row.party_a,
    party_b: row.party_b,
    amount: Number(row.amount),
    sign_date: row.sign_date || null,
    remark: row.remark
  })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
async function onSave() {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (isEdit.value) {
      const { contract_no, ...rest } = form
      await updateContract(editingId.value, { ...rest })
      ElMessage.success('修改成功')
    } else {
      await createContract({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}
function onFileChange(file) {
  ElMessage.success(`已选择附件：${file.name}（演示，未真实上传）`)
}

async function onSubmit(row) {
  await submitContract(row.id)
  ElMessage.success('已提交审批，合同进入 7 级审批流')
  load()
}
async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除合同「${row.title}」(${row.contract_no})吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await deleteContract(row.id)
  ElMessage.success('删除成功')
  load()
}

// 详情抽屉
const detailVisible = ref(false)
const detailId = ref(null)
function openDetail(row) {
  detailId.value = row.id
  detailVisible.value = true
}

onMounted(load)
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}
.search-input { max-width: 340px; }
.toolbar-right { display: flex; gap: 8px; }
.cur-role { margin-top: 4px; font-size: 12px; color: #e6a23c; }
.upload-mock {
  width: 100%;
  :deep(.el-upload),
  :deep(.el-upload-dragger) { width: 100%; }
  :deep(.el-upload-dragger) { padding: 16px; }
}
.upload-tip { color: #a8abb2; font-size: 12px; margin-top: 4px; }
</style>

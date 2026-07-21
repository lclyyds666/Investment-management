<template>
  <div class="org" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>用户管理 / 组织架构</span>
          <div class="ops">
            <el-button v-if="isSuperuser" type="primary" :icon="Plus" @click="openCreate">新建用户</el-button>
            <el-button :icon="Refresh" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="7 级角色权限体系：业务经办 → 业务复核 → 风控审核 → 财务经办 → 财务复核 → 供管公司负责人 → 投资公司负责人"
        class="mb"
      />

      <!-- 搜索筛选 -->
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索账号 / 姓名 / 部门"
          clearable
          style="width: 220px"
          :prefix-icon="Search"
          @keyup.enter="load"
          @clear="load"
        />
        <el-select v-model="filters.role" placeholder="角色" clearable style="width: 160px" @change="load">
          <el-option v-for="(label, val) in ROLE_LABELS" :key="val" :label="label" :value="val" />
        </el-select>
        <el-select v-model="filters.is_active" placeholder="状态" clearable style="width: 120px" @change="load">
          <el-option label="启用" :value="true" />
          <el-option label="停用" :value="false" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="load">查询</el-button>
      </div>

      <el-table :data="users" border stripe>
        <el-table-column type="index" label="#" width="56" align="center" />
        <el-table-column prop="full_name" label="姓名" width="110" />
        <el-table-column prop="username" label="登录账号" width="120" />
        <el-table-column label="角色" min-width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" min-width="120" />
        <el-table-column label="电子签名" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.has_signature ? 'success' : 'info'" size="small" effect="plain">
              {{ row.has_signature ? '已设置' : '未设置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="超管" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_superuser" type="success" size="small">超管</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isSuperuser" label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" @click="onResetPassword(row)">重置密码</el-button>
            <el-button size="small" type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑弹窗 -->
    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑用户' : '新建用户'" width="480px">
      <el-form ref="formRef" :model="dialog.form" :rules="formRules" label-width="90px">
        <el-form-item label="登录账号" prop="username">
          <el-input v-model="dialog.form.username" :disabled="dialog.isEdit" placeholder="登录账号" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="dialog.form.full_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item v-if="!dialog.isEdit" label="初始密码" prop="password">
          <el-input v-model="dialog.form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="dialog.form.role" placeholder="选择角色" style="width: 100%">
            <el-option v-for="(label, val) in ROLE_LABELS" :key="val" :label="label" :value="val" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门" prop="department">
          <el-input v-model="dialog.form.department" placeholder="所属部门" />
        </el-form-item>
        <el-form-item label="超级管理员">
          <el-switch v-model="dialog.form.is_superuser" />
          <span class="hint">超管不受角色权限限制，可审批任意环节</span>
        </el-form-item>
        <el-form-item v-if="dialog.isEdit" label="账号状态">
          <el-switch v-model="dialog.form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Edit, Delete, Search } from '@element-plus/icons-vue'
import { ROLE_LABELS, ROLES } from '@/constants/business'
import { useUserStore } from '@/store/user'
import {
  listUsers, createUser, updateUser, setUserActive, resetUserPassword, deleteUser
} from '@/api/user'

const userStore = useUserStore()
const isSuperuser = ref(userStore.isSuperuser)

const loading = ref(false)
const users = ref([])
const filters = reactive({ keyword: '', role: null, is_active: null })

const formRef = ref()
const dialog = reactive({
  visible: false,
  isEdit: false,
  saving: false,
  editId: null,
  form: {}
})

const formRules = {
  username: [{ required: true, message: '请输入登录账号', trigger: 'blur' }],
  full_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

function emptyForm() {
  return {
    username: '',
    full_name: '',
    password: '',
    role: ROLES.BUSINESS_HANDLER,
    department: '',
    is_superuser: false,
    is_active: true
  }
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.role) params.role = filters.role
    if (filters.is_active !== null) params.is_active = filters.is_active
    users.value = await listUsers(params)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dialog.isEdit = false
  dialog.editId = null
  dialog.form = emptyForm()
  dialog.visible = true
  formRef.value?.clearValidate?.()
}

function openEdit(row) {
  dialog.isEdit = true
  dialog.editId = row.id
  dialog.form = {
    username: row.username,
    full_name: row.full_name,
    role: row.role,
    department: row.department,
    is_superuser: row.is_superuser,
    is_active: row.is_active
  }
  dialog.visible = true
  formRef.value?.clearValidate?.()
}

async function onSave() {
  await formRef.value?.validate()
  dialog.saving = true
  try {
    if (dialog.isEdit) {
      await updateUser(dialog.editId, {
        full_name: dialog.form.full_name,
        role: dialog.form.role,
        department: dialog.form.department,
        is_superuser: dialog.form.is_superuser,
        is_active: dialog.form.is_active
      })
      ElMessage.success('用户已更新')
    } else {
      await createUser({
        username: dialog.form.username,
        full_name: dialog.form.full_name,
        password: dialog.form.password,
        role: dialog.form.role,
        department: dialog.form.department,
        is_superuser: dialog.form.is_superuser
      })
      ElMessage.success('用户创建成功')
    }
    dialog.visible = false
    load()
  } finally {
    dialog.saving = false
  }
}

async function toggleActive(row) {
  const next = !row.is_active
  await setUserActive(row.id, next)
  ElMessage.success(next ? '已启用' : '已停用')
  load()
}

async function onResetPassword(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      `重置【${row.full_name || row.username}】的密码。留空则重置为系统默认密码（123456）。`,
      '重置密码',
      { confirmButtonText: '确定重置', cancelButtonText: '取消', inputPlaceholder: '新密码（可留空）', inputType: 'password' }
    )
    await resetUserPassword(row.id, value || undefined)
    ElMessage.success(value ? '密码已重置' : '密码已重置为默认 123456')
  } catch (e) {
    // 取消
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户【${row.full_name || row.username}】？该操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    await deleteUser(row.id)
    ElMessage.success('用户已删除')
    load()
  } catch (e) {
    // 取消
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.ops { display: flex; gap: 8px; }
.mb { margin-bottom: 14px; }
.filters { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>

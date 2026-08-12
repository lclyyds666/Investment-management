<template>
  <div class="position-console">
    <section class="position-list">
      <header><div><small>组织授权</small><h2>岗位与权限</h2></div><el-button type="primary" @click="createPosition">新建岗位</el-button></header>
      <el-table :data="positions" row-key="id" @row-click="selectPosition">
        <el-table-column prop="code" label="岗位编码" min-width="220" />
        <el-table-column prop="name" label="岗位名称" min-width="140" />
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="权限数" width="100"><template #default="{ row }">{{ row.permissions?.length || 0 }}</template></el-table-column>
      </el-table>
    </section>
    <section class="template-detail">
      <h2>{{ form.id ? '岗位模板' : '新建岗位' }}</h2>
      <el-form :model="form" label-width="88px">
        <el-form-item label="岗位编码"><el-input v-model="form.code" :disabled="Boolean(form.id)" /></el-form-item>
        <el-form-item label="岗位名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="岗位类别"><el-select v-model="form.category"><el-option v-for="category in categories" :key="category" :label="category" :value="category" /></el-select></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
        <el-form-item label="变更原因" required><el-input v-model="reason" maxlength="200" show-word-limit /></el-form-item>
      </el-form>
      <div class="template-actions"><span>已配置 {{ form.permissions.length }} 项权限</span><el-button @click="drawerVisible=true">编辑权限模板</el-button></div>
      <el-button type="primary" :disabled="!reason.trim()" @click="save">保存岗位模板</el-button>
    </section>
  </div>
  <el-drawer v-model="drawerVisible" title="岗位权限模板" size="min(720px, 96vw)">
    <p class="drawer-note">权限按平台/模块分组；保存岗位时将完整替换当前岗位模板。</p>
    <div v-for="(grant, index) in form.permissions" :key="grant.key" class="grant-row">
      <el-select v-model="grant.permission_code" filterable placeholder="选择权限"><el-option-group v-for="group in permissionGroups" :key="group.label" :label="group.label"><el-option v-for="permission in group.permissions" :key="permission.code" :label="permission.name || permission.code" :value="permission.code" /></el-option-group></el-select>
      <el-select v-model="grant.data_scope"><el-option v-for="scope in scopes" :key="scope" :label="scope" :value="scope" /></el-select>
      <el-input v-model="grant.scope_ref" :disabled="blankScope(grant.data_scope)" placeholder="范围引用" />
      <el-button text type="danger" @click="removeGrant(index)">移除</el-button>
    </div>
    <el-button @click="addGrant">添加权限</el-button>
  </el-drawer>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/organization'
import { useOrganizationStore } from '@/store/organization'

const store = useOrganizationStore()
const positions = computed(() => store.positions)
const drawerVisible = ref(false)
const reason = ref('')
const form = reactive({ id: null, code: '', name: '', category: 'business', is_active: true, permissions: [] })
const categories = ['executive', 'department', 'business', 'governance', 'external', 'duty']
const scopes = ['platform', 'company', 'department', 'business_domain', 'own', 'participated', 'assigned']
const blankScope = scope => ['own', 'participated', 'assigned'].includes(scope)
const permissionGroups = computed(() => Object.values((store.permissions || []).reduce((groups, permission) => {
  const label = permission.resource || permission.code.split('.').slice(0, -1).join('.')
  ;(groups[label] ||= { label, permissions: [] }).permissions.push(permission)
  return groups
}, {})))
const grant = item => ({ key: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`, permission_code: item?.permission_code || '', data_scope: item?.data_scope || 'company', scope_ref: item?.scope_ref || '' })
function selectPosition(position) { Object.assign(form, { ...position, permissions: (position.permissions || []).map(grant) }); reason.value = '' }
function createPosition() { Object.assign(form, { id: null, code: '', name: '', category: 'business', is_active: true, permissions: [] }); reason.value = '' }
function addGrant() { form.permissions.push(grant()) }
function removeGrant(index) { form.permissions.splice(index, 1) }
function payloadGrants() { return form.permissions.filter(item => item.permission_code).map(({ permission_code, data_scope, scope_ref }) => ({ permission_code, data_scope, scope_ref: blankScope(data_scope) ? '' : scope_ref.trim() })) }
async function save() {
  if (!reason.value.trim()) return
  const payload = { code: form.code.trim(), name: form.name.trim(), category: form.category, is_active: form.is_active }
  if (!payload.code || !payload.name) return ElMessage.error('请填写岗位编码和岗位名称')
  try {
    await ElMessageBox.confirm('保存将完整替换该岗位的权限模板，确认继续？', '确认保存', { type: 'warning' })
    const position = form.id ? await api.updatePosition(form.id, payload, reason.value.trim()) : await api.createPosition(payload, reason.value.trim())
    await api.replacePositionPermissions(position.id || form.id, payloadGrants(), reason.value.trim())
    await store.loadPositions(true)
    selectPosition((store.positions || []).find(item => item.id === (position.id || form.id)) || { ...position, permissions: payloadGrants() })
    ElMessage.success('岗位模板已保存')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error.response?.data?.detail?.message || '岗位模板保存失败') }
}
onMounted(async () => { await Promise.all([store.loadPositions(), store.loadPermissions()]); if (positions.value[0]) selectPosition(positions.value[0]); else createPosition() })
</script>

<style scoped>
.position-console{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(320px,.8fr);gap:18px;padding:20px;min-height:100%;background:var(--app-bg)}.position-list,.template-detail{padding:18px;background:var(--el-bg-color);border:1px solid var(--surface-border)}header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}header small{color:var(--brand-vermilion);font-weight:700}h2{margin:2px 0;font-family:var(--font-display)}.template-actions{display:flex;justify-content:space-between;align-items:center;margin:18px 0}.grant-row{display:grid;grid-template-columns:minmax(180px,2fr) 130px minmax(140px,1fr) auto;gap:8px;margin-bottom:10px}.drawer-note{color:var(--el-text-color-secondary)}@media(max-width:900px){.position-console{grid-template-columns:1fr}.grant-row{grid-template-columns:1fr}}
</style>

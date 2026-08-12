<template>
  <section class="assignment-console">
    <header><div><small>组织授权</small><h2>人员任职</h2></div><div class="user-picker"><el-input v-model="userId" placeholder="用户 ID" /><el-button @click="loadAssignments">载入任职</el-button></div></header>
    <p class="notice">保存会完整替换该人员的任职集合；同一组织可保留多条不同岗位或任期的记录。</p>
    <article v-for="(assignment, index) in assignments" :key="assignment.key" data-testid="assignment-row" :class="['assignment-row', { conflict: assignment.conflict }]">
      <div class="row-heading"><b>任职 {{ index + 1 }}</b><el-button text type="danger" @click="removeAssignment(index)">移除</el-button></div>
      <div class="row-grid">
        <el-select v-model="assignment.organization_code" placeholder="组织"><el-option v-for="organization in organizations" :key="organization.code" :label="organization.name" :value="organization.code" /></el-select>
        <el-select v-model="assignment.position_code" placeholder="岗位"><el-option v-for="position in positions" :key="position.code" :label="position.name" :value="position.code" /></el-select>
        <el-date-picker v-model="assignment.valid_from" value-format="YYYY-MM-DD" type="date" placeholder="生效日期" />
        <el-date-picker v-model="assignment.valid_until" value-format="YYYY-MM-DD" type="date" clearable placeholder="截止日期" />
        <el-select v-model="assignment.status"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select>
      </div>
      <div v-if="positionFor(assignment)?.category === 'governance'" class="special-fields"><b>治理范围</b><el-select v-model="assignment.governance_scope_type"><el-option label="公司" value="company" /><el-option label="部门" value="department" /><el-option label="业务域" value="business_domain" /></el-select><el-input v-model="assignment.governance_scope_ref" placeholder="范围编码" /></div>
      <div v-if="positionFor(assignment)?.category === 'external'" class="special-fields"><b>外聘法律顾问</b><el-input v-model="assignment.provider_name" placeholder="服务单位" /><el-input v-model="assignment.service_scopes" placeholder="服务范围，以逗号分隔" /></div>
    </article>
    <el-button data-testid="add-assignment" @click="addAssignment">添加任职</el-button>
    <footer><el-input v-model="reason" maxlength="200" show-word-limit placeholder="变更原因（必填）" /><el-button type="primary" :disabled="!reason.trim() || !userId" @click="save">保存全部任职</el-button></footer>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/organization'
import { useOrganizationStore } from '@/store/organization'

const route = useRoute(); const store = useOrganizationStore(); const userId = ref(String(route.query.user_id || '')); const reason = ref(''); const assignments = ref([])
const positions = computed(() => store.positions || [])
const organizations = computed(() => { const walk = nodes => nodes.flatMap(node => [node, ...walk(node.children || [])]); return walk(store.tree || []) })
const item = source => ({ key: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`, id: source?.id, organization_code: source?.organization?.code || source?.organization_code || '', position_code: source?.position?.code || source?.position_code || '', valid_from: source?.valid_from || '', valid_until: source?.valid_until || null, status: source?.status || 'active', governance_scope_type: source?.governance_scopes?.[0]?.scope_type || 'company', governance_scope_ref: source?.governance_scopes?.[0]?.scope_ref || '', provider_name: source?.external?.provider_name || '', service_scopes: source?.external?.service_scopes?.join(', ') || '', conflict: false })
const positionFor = assignment => positions.value.find(position => position.code === assignment.position_code)
function addAssignment() { assignments.value.push(item()) }
function removeAssignment(index) { assignments.value.splice(index, 1) }
async function loadAssignments() { if (!userId.value) return; assignments.value = (await api.getUserAssignments(userId.value)).map(item) }
function validateExternal() { return assignments.value.every(assignment => { const isLegal = assignment.position_code === 'external.legal_counsel'; return !isLegal || (assignment.valid_until && assignment.provider_name.trim() && assignment.service_scopes.split(',').every(scope => scope.trim()) && assignment.service_scopes.trim()) }) }
function payload() { return { assignments: assignments.value.map(assignment => { const position = positionFor(assignment); return { organization_code: assignment.organization_code, position_code: assignment.position_code, valid_from: assignment.valid_from, valid_until: assignment.valid_until || null, status: assignment.status, governance_scopes: position?.category === 'governance' ? [{ scope_type: assignment.governance_scope_type, scope_ref: assignment.governance_scope_ref.trim() }] : [], external: position?.category === 'external' ? { provider_name: assignment.provider_name.trim(), service_scopes: assignment.service_scopes.split(',').map(scope => scope.trim()).filter(Boolean) } : null } }) } }
function highlightConflicts(ids) { const conflicts = new Set((ids || []).map(String)); assignments.value.forEach(assignment => { assignment.conflict = conflicts.has(String(assignment.id)) }) }
async function save() {
  if (!reason.value.trim() || !userId.value) return
  if (!validateExternal()) return ElMessage.error('外聘法律顾问必须设置截止日期、服务单位和服务范围')
  assignments.value.forEach(assignment => { assignment.conflict = false })
  try { await ElMessageBox.confirm('保存将完整替换该人员的任职集合，确认继续？', '确认保存', { type: 'warning' }); assignments.value = (await api.replaceUserAssignments(userId.value, payload(), reason.value.trim())).map(item); ElMessage.success('人员任职已保存') }
  catch (error) { const detail = error.response?.data?.detail; if (detail?.code === 'assignment_workflow_conflict') { highlightConflicts(detail.assignment_ids); ElMessage.error(detail.message) } else if (error !== 'cancel' && error !== 'close') ElMessage.error(detail?.message || '人员任职保存失败') }
}
onMounted(async () => { await Promise.all([store.loadTree(), store.loadPositions()]); if (userId.value) await loadAssignments() })
</script>

<style scoped>
.assignment-console{padding:20px;min-height:100%;background:var(--app-bg)}header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}header small{color:var(--brand-vermilion);font-weight:700}h2{margin:2px 0;font-family:var(--font-display)}.user-picker{display:flex;gap:8px}.notice{margin:16px 0;color:var(--el-text-color-secondary)}.assignment-row{margin:12px 0;padding:14px;background:var(--el-bg-color);border:1px solid var(--surface-border);border-left:4px solid transparent}.assignment-row.conflict{border-color:var(--el-color-danger);border-left-color:var(--el-color-danger);background:var(--el-color-danger-light-9)}.row-heading{display:flex;justify-content:space-between;margin-bottom:10px}.row-grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px}.special-fields{display:flex;align-items:center;gap:10px;margin-top:10px}.special-fields .el-input{max-width:280px}footer{display:flex;gap:12px;margin-top:20px;align-items:center}footer .el-input{max-width:540px}@media(max-width:900px){.row-grid{grid-template-columns:1fr 1fr}.special-fields,footer{align-items:stretch;flex-direction:column}.special-fields .el-input,footer .el-input{max-width:none}}
</style>

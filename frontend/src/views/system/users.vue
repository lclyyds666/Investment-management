<template>
  <ProTable ref="tableRef" title="人员账号" :fetch="fetchUsers" :columns="columns" row-key="id">
    <template #toolbar><el-button type="primary" @click="openCreate">新建账号</el-button></template>
    <template #prepend><div class="filters"><el-select v-model="filters.organization_code" placeholder="组织筛选" clearable @change="reload"><el-option v-for="item in organizations" :key="item.code" :label="item.name" :value="item.code" /></el-select><el-select v-model="filters.position_code" placeholder="岗位筛选" clearable @change="reload"><el-option v-for="item in positions" :key="item.code" :label="item.name" :value="item.code" /></el-select></div></template>
    <template #assignments="{ row }"><div class="assignment-trail"><el-tag v-for="item in row.assignment_summaries" :key="item.assignment_id" effect="plain">{{ item.organization_name }} / {{ item.position_name }}</el-tag><span v-if="!row.assignment_summaries?.length">—</span></div></template>
    <template #legalAlert="{ row }"><el-tag size="small" :type="row.legal_alert_enabled ? 'success' : 'info'">{{ row.legal_alert_enabled ? '已开启' : '未开启' }}</el-tag></template>
    <template #signature="{ row }"><el-tag size="small" :type="row.has_signature ? 'success' : 'info'">{{ row.has_signature ? '已设置' : '未设置' }}</el-tag></template>
    <template #actions="{ row }"><el-button size="small" @click="openEdit(row)">编辑</el-button><el-button size="small" @click="router.push({ name: 'SystemAssignments', query: { user_id: row.id } })">任职</el-button><el-button size="small" @click="confirmResetPassword(row.id)">重置密码</el-button></template>
  </ProTable>
  <el-dialog v-model="dialog.visible" :title="dialog.id ? '编辑账号' : '新建账号'" width="480px"><el-form :model="dialog.form" label-width="104px"><el-form-item label="登录账号"><el-input v-model="dialog.form.username" :disabled="Boolean(dialog.id)" /></el-form-item><el-form-item label="姓名"><el-input v-model="dialog.form.full_name" /></el-form-item><el-form-item v-if="!dialog.id" label="初始密码"><el-input v-model="dialog.form.password" type="password" /></el-form-item><el-form-item label="钉钉手机号"><el-input v-model="dialog.form.mobile" maxlength="11" inputmode="numeric" placeholder="用于群机器人手机号 @" /></el-form-item><el-form-item label="法务提醒"><el-switch v-model="dialog.form.legal_alert_enabled" /></el-form-item><el-form-item v-if="dialog.id" label="启用"><el-switch v-model="dialog.form.is_active" /></el-form-item></el-form><template #footer><el-button @click="dialog.visible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProTable from '@/components/ProTable.vue'
import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getOrganizationTree, listPositions } from '@/api/organization'
const router = useRouter(); const tableRef = ref(); const organizations = ref([]); const positions = ref([]); const filters = reactive({ organization_code: '', position_code: '' }); const dialog = reactive({ visible:false, id:null, form:{} })
const columns = [{ prop:'full_name', label:'姓名', minWidth:100 }, { prop:'username', label:'登录账号', minWidth:120 }, { label:'任职身份', slot:'assignments', minWidth:240 }, { prop:'mobile', label:'钉钉手机号', minWidth:130 }, { label:'法务提醒', slot:'legalAlert', width:100 }, { label:'电子签名', slot:'signature', width:100 }, { label:'操作', slot:'actions', width:220 }]
const reload=()=>tableRef.value?.reload(); const fetchUsers=()=>listUsers(Object.fromEntries(Object.entries(filters).filter(([,value])=>value)))
function flatten(nodes){ return nodes.flatMap(item=>[item,...flatten(item.children||[])]) }
async function openCreate(){ dialog.id=null; dialog.form={ username:'', full_name:'', password:'', mobile:'', legal_alert_enabled:false }; dialog.visible=true }
function openEdit(row){ dialog.id=row.id; dialog.form={ username:row.username, full_name:row.full_name, mobile:row.mobile || '', legal_alert_enabled:Boolean(row.legal_alert_enabled), is_active:row.is_active }; dialog.visible=true }
async function save(){ const mobile=(dialog.form.mobile || '').trim(); if(mobile && !/^1[3-9]\d{9}$/.test(mobile)){ ElMessage.warning('请输入 11 位中国大陆手机号'); return } if(dialog.form.legal_alert_enabled && !mobile){ ElMessage.warning('开启法务提醒前请填写钉钉手机号'); return } const payload={ full_name:dialog.form.full_name, mobile:mobile || null, legal_alert_enabled:dialog.form.legal_alert_enabled }; if(dialog.id){ payload.is_active=dialog.form.is_active; await updateUser(dialog.id,payload) } else { await createUser({ ...dialog.form, ...payload }) } dialog.visible=false; ElMessage.success('账号已保存'); reload() }
async function confirmResetPassword(userId){ try { await ElMessageBox.confirm('重置后用户需要使用新密码重新登录；确认继续？', '重置密码', { type:'warning', confirmButtonText:'确认重置', cancelButtonText:'取消' }); await resetUserPassword(userId); ElMessage.success('密码已重置') } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('重置密码失败') } }
onMounted(async()=>{ organizations.value=flatten(await getOrganizationTree()); positions.value=await listPositions() })
</script>
<style scoped>.filters{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}.assignment-trail{display:flex;flex-wrap:wrap;gap:6px}.assignment-trail :deep(.el-tag){border-left:3px solid var(--brand-vermilion)}</style>

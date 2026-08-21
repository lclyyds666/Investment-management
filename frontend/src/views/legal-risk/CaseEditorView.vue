<template>
  <section class="editor-page" v-loading="loading">
    <header class="editor-header">
      <el-button :icon="ArrowLeft" text circle aria-label="返回" @click="$router.back()" />
      <div><span>{{ isEdit ? 'EDIT CASE' : 'NEW DRAFT' }}</span><h1>{{ isEdit ? '编辑案件基础信息' : '新建案件草稿' }}</h1></div>
      <el-tag v-if="caseData.stage" :type="caseData.stage === 'draft' ? 'info' : 'success'">{{ caseData.stage === 'draft' ? '草稿' : '正式案件' }}</el-tag>
    </header>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="case-form">
      <section class="form-section">
        <h2>案件识别</h2>
        <div class="form-grid">
          <el-form-item v-if="!isEdit && isSuperuser" label="代理发起组织编码" prop="organization_code" class="wide">
            <el-input v-model="form.organization_code" :disabled="initiatorOptionsLoading" placeholder="超级管理员请输入发起组织编码" />
          </el-form-item>
          <el-form-item v-else-if="!isEdit && initiatorOptions.length" label="案件发起组织" prop="initiator_assignment_id" class="wide">
            <el-select v-model="form.initiator_assignment_id" :loading="initiatorOptionsLoading" placeholder="请选择案件发起组织">
              <el-option v-for="option in initiatorOptions" :key="option.assignment_id" :value="option.assignment_id" :label="`${option.company_name} / ${option.organization_name} / ${option.position_name || option.position_code}`" />
            </el-select>
          </el-form-item>
          <el-alert
            v-else-if="!isEdit && initiatorOptionsLoaded"
            class="wide"
            type="warning"
            :closable="false"
            show-icon
            :title="initiatorOptionsFailed ? '案件发起任职加载失败，请稍后重试' : '当前账号没有有效的案件发起任职'"
          />
          <el-form-item label="案件名称" prop="case_name" class="wide"><el-input v-model="form.case_name" maxlength="255" show-word-limit /></el-form-item>
          <el-form-item label="案由"><el-input v-model="form.cause_of_action" /></el-form-item>
          <el-form-item label="受理法院"><el-input v-model="form.court" /></el-form-item>
          <el-form-item label="法院案号"><el-input v-model="form.court_case_no" /></el-form-item>
          <el-form-item label="保密等级"><el-select v-model="form.confidentiality_level"><el-option label="内部" value="internal" /><el-option label="机密" value="confidential" /></el-select></el-form-item>
        </div>
      </section>

      <section class="form-section">
        <h2>诉讼标的额</h2>
        <div class="form-grid">
          <el-form-item label="标的额（元）" prop="subject_amount"><el-input-number v-model="form.subject_amount" :min="0" :precision="2" :controls="false" /></el-form-item>
          <el-form-item label="案件负责人"><el-input v-model="form.responsible_user_name" clearable maxlength="64" placeholder="请输入与账号姓名一致的姓名" @input="responsibleNameDirty = true" /></el-form-item>
          <el-form-item label="律师事务所"><el-input v-model="form.law_firm" /></el-form-item>
          <el-form-item label="承办律师"><el-input v-model="form.attorney_name" /></el-form-item>
        </div>
      </section>

      <section class="form-section">
        <h2>案情与请求</h2>
        <div class="form-grid">
          <el-form-item label="案情摘要" class="wide"><el-input v-model="form.case_summary" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="诉讼/仲裁请求" class="wide"><el-input v-model="form.claims" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="可供执行财产情况" class="wide"><el-input v-model="form.enforcement_property_status" type="textarea" :rows="3" /></el-form-item>
        </div>
      </section>

      <section v-if="isEdit && caseData.stage === 'formal'" class="form-section">
        <h2>结案信息</h2>
        <div class="form-grid">
          <el-form-item label="结案日期"><el-date-picker v-model="form.closed_date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="结案结果摘要" class="wide"><el-input v-model="form.closure_summary" type="textarea" :rows="4" /></el-form-item>
        </div>
      </section>
    </el-form>

    <footer class="editor-actions">
      <el-button @click="$router.back()">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!isEdit && !canCreateCase" :icon="Check" @click="save">保存</el-button>
    </footer>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ArrowLeft, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { createCase, getCase, listLegalInitiatorOptions, listLegalUserOptions, updateCase } from '@/api/legalRisk'
import { usePortalStore } from '@/store/portal'
import { responsibleUserPatch } from '@/utils/legalCaseForm'

const route = useRoute()
const router = useRouter()
const portalStore = usePortalStore()
const formRef = ref()
const loading = ref(false)
const saving = ref(false)
const caseData = reactive({})
const users = ref([])
const initiatorOptions = ref([])
const initiatorOptionsLoading = ref(false)
const initiatorOptionsLoaded = ref(false)
const initiatorOptionsFailed = ref(false)
const responsibleNameDirty = ref(false)
const isEdit = computed(() => Boolean(route.params.caseId))
const isSuperuser = computed(() => portalStore.isSuperuser)
const form = reactive({
  case_name: '', cause_of_action: '', court: '', court_case_no: '', subject_amount: 0,
  responsible_user_name: '', confidentiality_level: 'internal', law_firm: '', attorney_name: '',
  case_summary: '', claims: '', enforcement_property_status: '', closed_date: null, closure_summary: '',
  initiator_assignment_id: null, organization_code: ''
})
const rules = {
  case_name: [{ required: true, message: '请输入案件名称', trigger: 'blur' }],
  initiator_assignment_id: [{ required: true, message: '请选择案件发起组织', trigger: 'change' }],
  organization_code: [{ required: true, message: '请输入代理发起组织编码', trigger: 'blur' }]
}
const canCreateCase = computed(() => initiatorOptionsLoaded.value && (
  isSuperuser.value
    ? Boolean(form.organization_code.trim())
    : form.initiator_assignment_id !== null
))

function initiatorWarning() {
  if (initiatorOptionsFailed.value) return '案件发起任职加载失败，请稍后重试'
  if (initiatorOptions.value.length) return '请选择有效的案件发起任职'
  return '当前账号没有有效的案件发起任职'
}

async function loadInitiatorOptions() {
  initiatorOptionsLoaded.value = false
  initiatorOptionsFailed.value = false
  form.initiator_assignment_id = null
  if (isSuperuser.value) {
    initiatorOptions.value = []
    initiatorOptionsLoaded.value = true
    return
  }
  initiatorOptionsLoading.value = true
  try {
    initiatorOptions.value = await listLegalInitiatorOptions('case')
    if (initiatorOptions.value.length === 1) {
      form.initiator_assignment_id = initiatorOptions.value[0].assignment_id
    }
  } catch {
    initiatorOptions.value = []
    initiatorOptionsFailed.value = true
    ElMessage.warning('案件发起任职加载失败，请稍后重试')
  } finally {
    initiatorOptionsLoading.value = false
    initiatorOptionsLoaded.value = true
  }
}

onMounted(async () => {
  loading.value = true
  try {
    users.value = await listLegalUserOptions()
    if (!isEdit.value) {
      await loadInitiatorOptions()
      return
    }
    const data = await getCase(route.params.caseId)
    Object.assign(caseData, data)
    Object.keys(form).forEach((key) => { form[key] = data[key] ?? form[key] })
    form.responsible_user_name = data.responsible_user_name || users.value.find(
      (user) => Number(user.id) === Number(data.responsible_user_id)
    )?.name || ''
    responsibleNameDirty.value = false
  } finally { loading.value = false }
})

async function save() {
  if (!isEdit.value && !canCreateCase.value) {
    ElMessage.warning(initiatorWarning())
    return
  }
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.responsible_user_name
    Object.assign(payload, responsibleUserPatch({
      isEdit: isEdit.value,
      dirty: responsibleNameDirty.value,
      name: form.responsible_user_name
    }))
    if (!isEdit.value) {
      delete payload.closed_date
      delete payload.closure_summary
      if (isSuperuser.value) delete payload.initiator_assignment_id
      else delete payload.organization_code
    } else {
      delete payload.initiator_assignment_id
      delete payload.organization_code
    }
    const data = isEdit.value
      ? await updateCase(route.params.caseId, { ...payload, version: caseData.version })
      : await createCase(payload)
    ElMessage.success(isEdit.value ? '案件基础信息已更新' : '草稿已保存')
    router.replace(`/investment/legal-risk/cases/${data.id}`)
  } catch (error) {
    if (error.response?.status === 409) ElMessage.warning('案件已被其他人员修改，请返回详情刷新后重试')
  } finally { saving.value = false }
}
</script>

<style scoped>
.editor-page { max-width: 1040px !important; min-width: 0; }
.editor-header { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 14px; margin-bottom: 16px; }
.editor-header span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; letter-spacing: 0; }
.editor-header h1 { margin: 3px 0 0; font-size: 24px; letter-spacing: 0; }
.case-form { display: grid; gap: 14px; }
.form-section { padding: 20px; border: 1px solid var(--el-border-color-lighter); border-left: 3px solid var(--divider-rail); background: var(--surface-solid); }
.form-section h2 { margin: 0 0 16px; font-size: 16px; letter-spacing: 0; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 20px; }
.wide { grid-column: 1 / -1; }
.form-grid :deep(.el-select), .form-grid :deep(.el-input-number) { width: 100%; }
.editor-actions { position: sticky; bottom: 0; display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; padding: 14px 0; border-top: 1px solid var(--el-border-color-lighter); background: color-mix(in srgb, var(--app-bg) 92%, transparent); backdrop-filter: blur(8px); }
@media (max-width: 680px) { .form-grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } .form-section { padding: 16px; } }
</style>

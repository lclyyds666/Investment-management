<template>
  <el-dialog :model-value="modelValue" width="560px" title="改派审批任务" destroy-on-close @close="close">
    <div class="task-context">
      <span>治理待办</span>
      <strong>{{ task?.target_title }}</strong>
      <p>{{ task?.node_name }} · {{ task?.required_position_name || task?.required_position_code }}</p>
    </div>
    <div class="field">
      <label>接任人员</label>
      <el-select v-model="userId" class="full" placeholder="选择符合精确岗位的人员">
        <el-option
          v-for="candidate in candidates"
          :key="candidate.user_id"
          :value="candidate.user_id"
          :disabled="candidate.disabled"
          :label="`${candidate.full_name} · ${candidate.organization_name}`"
        />
      </el-select>
      <small>原办理人 {{ task?.previous_assignee?.full_name || '已移除' }} 不可再次选择。</small>
    </div>
    <div class="field">
      <label>改派原因</label>
      <el-input v-model="reason" type="textarea" :rows="3" maxlength="200" show-word-limit placeholder="说明岗位或人员失效情况（必填）" />
    </div>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">确认改派</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listWorkflowCandidates, reassignWorkflowTask } from '@/api/workflow'

const props = defineProps({ modelValue: Boolean, task: { type: Object, default: null } })
const emit = defineEmits(['update:modelValue', 'reassigned'])
const candidates = ref([])
const userId = ref(null)
const reason = ref('')
const submitting = ref(false)
const canSubmit = computed(() => Boolean(userId.value && reason.value.trim()))

async function loadCandidates() {
  if (!props.task?.id) return
  const result = await listWorkflowCandidates({ taskId: props.task.id })
  candidates.value = result.map(candidate => ({
    ...candidate,
    disabled: Number(candidate.user_id) === Number(props.task.previous_assignee?.id)
  }))
}

function close() { emit('update:modelValue', false) }
async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    await reassignWorkflowTask(props.task.id, userId.value, reason.value.trim())
    ElMessage.success('审批任务已改派')
    emit('reassigned')
    close()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail?.message || '改派失败，请刷新队列后重试')
  } finally {
    submitting.value = false
  }
}

watch(() => [props.modelValue, props.task?.id], async ([visible]) => {
  if (!visible) return
  userId.value = null
  reason.value = ''
  await loadCandidates()
}, { immediate: true })

defineExpose({ candidates, userId, reason, submit })
</script>

<style scoped>
.task-context { padding: 14px 16px; border-left: 3px solid var(--brand-vermilion); background: var(--el-fill-color-lighter); }
.task-context span { display: block; color: var(--brand-vermilion); font-size: 11px; font-weight: 700; letter-spacing: .12em; }
.task-context strong { display: block; margin-top: 5px; font-size: 16px; }
.task-context p { margin: 4px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.field { margin-top: 18px; }
.field label { display: block; margin-bottom: 7px; font-weight: 600; }
.field small { display: block; margin-top: 6px; color: var(--el-text-color-secondary); }
.full { width: 100%; }
</style>

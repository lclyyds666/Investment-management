<template>
  <div class="approval" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>审批中心</span>
          <span class="my-role">
            当前身份：<el-tag type="warning" size="small">{{ userStore.roleLabel || '—' }}</el-tag>
            <span class="hint">仅显示流转到「我」这一环节、待我处理的合同</span>
          </span>
        </div>
      </template>

      <el-table :data="pending" border stripe>
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
        <el-table-column label="当前环节" width="130" align="center">
          <template #default="{ row }">
            <el-tag type="warning" size="small">{{ row.current_role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" align="center">
          <template #default="{ row }">
            <el-button size="small" :icon="View" @click="openDetail(row)">查看详情</el-button>
            <el-button size="small" type="success" @click="openAction(row, 'approve')">通过</el-button>
            <el-button size="small" type="danger" @click="openAction(row, 'reject')">驳回</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无待您审批的合同</template>
      </el-table>
    </el-card>

    <!-- 通过 / 驳回 -->
    <el-dialog
      v-model="visible"
      :title="action === 'approve' ? '审批通过 - 审批意见' : '驳回 - 请输入驳回原因'"
      width="480px"
    >
      <el-alert
        v-if="action === 'approve'"
        type="success"
        :closable="false"
        show-icon
        title="通过后将自动附加您的电子签名，并流转至下一审批环节"
        class="mb"
      />
      <el-form ref="formRef" :model="fm" :rules="rules">
        <el-form-item prop="comment">
          <el-input
            v-model="fm.comment"
            type="textarea"
            :rows="4"
            :placeholder="action === 'approve' ? '请输入审批意见（可选）' : '请输入驳回原因（必填）'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button :type="action === 'approve' ? 'success' : 'danger'" :loading="saving" @click="confirm">
          确认{{ action === 'approve' ? '通过' : '驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉 -->
    <ContractDetailDrawer v-model="detailVisible" :contract-id="detailId" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { View } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import ContractDetailDrawer from '@/components/ContractDetailDrawer.vue'
import { listTodo, approveContract, rejectContract } from '@/api/contract'

const userStore = useUserStore()
const loading = ref(false)
const pending = ref([])

async function load() {
  loading.value = true
  try {
    pending.value = await listTodo()
  } finally {
    loading.value = false
  }
}

// 通过 / 驳回
const visible = ref(false)
const saving = ref(false)
const current = ref(null)
const action = ref('approve')
const formRef = ref()
const fm = reactive({ comment: '' })
const rules = computed(() => ({
  comment:
    action.value === 'reject'
      ? [{ required: true, message: '请输入驳回原因', trigger: 'blur' }]
      : []
}))

function openAction(row, act) {
  current.value = row
  action.value = act
  fm.comment = ''
  visible.value = true
  formRef.value?.clearValidate?.()
}
async function confirm() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (action.value === 'approve') {
      await approveContract(current.value.id, fm.comment)
      ElMessage.success('已通过并附加电子签名')
    } else {
      await rejectContract(current.value.id, fm.comment)
      ElMessage.success('已驳回')
    }
    visible.value = false
    load()
  } finally {
    saving.value = false
  }
}

// 详情
const detailVisible = ref(false)
const detailId = ref(null)
function openDetail(row) {
  detailId.value = row.id
  detailVisible.value = true
}

onMounted(load)
</script>

<style scoped lang="scss">
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.my-role {
  font-size: 13px;
  color: #606266;
  .hint { margin-left: 10px; color: #a8abb2; font-size: 12px; }
}
.mb { margin-bottom: 12px; }
</style>

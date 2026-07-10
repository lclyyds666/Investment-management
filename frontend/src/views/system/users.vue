<template>
  <div class="org" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>组织架构 / 人员</span>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="7 级角色权限体系：业务经办 → 业务复核 → 风控审核 → 财务经办 → 财务复核 → 供管公司负责人 → 投资公司负责人"
        class="mb"
      />

      <el-table :data="users" border stripe>
        <el-table-column type="index" label="#" width="56" align="center" />
        <el-table-column prop="full_name" label="姓名" width="120" />
        <el-table-column prop="username" label="登录账号" width="130" />
        <el-table-column label="角色" min-width="150">
          <template #default="{ row }">
            <el-tag size="small">{{ row.role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" min-width="130" />
        <el-table-column label="电子签名" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.has_signature ? 'success' : 'info'" size="small" effect="plain">
              {{ row.has_signature ? '已设置' : '未设置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="超管" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_superuser" type="success" size="small">超管</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { listUsers } from '@/api/user'

const loading = ref(false)
const users = ref([])

async function load() {
  loading.value = true
  try {
    users.value = await listUsers()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.mb { margin-bottom: 14px; }
</style>

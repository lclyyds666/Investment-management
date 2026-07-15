<template>
  <div class="approval">
    <el-card shadow="never">
      <template #header>
        <div class="card-header"><span>业务审批</span></div>
      </template>
      <el-empty description="日常业务审批功能建设中，敬请期待" :image-size="140">
        <template #image>
          <el-icon class="wip-icon"><Stamp /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Stamp } from '@element-plus/icons-vue'
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.approval :deep(.el-empty) { padding: 48px 0; }
.wip-icon {
  font-size: 96px;
  color: var(--el-color-primary);
  opacity: 0.55;
}
</style>

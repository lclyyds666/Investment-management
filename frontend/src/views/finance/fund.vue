<template>
  <div class="fund">
    <el-card shadow="never">
      <template #header>
        <div class="card-header"><span>资金管理</span></div>
      </template>
      <el-empty description="功能建设中，敬请期待" :image-size="140">
        <template #image>
          <el-icon class="wip-icon"><Coin /></el-icon>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { Coin } from '@element-plus/icons-vue'
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.fund :deep(.el-empty) { padding: 48px 0; }
.wip-icon {
  font-size: 96px;
  color: var(--el-color-primary);
  opacity: 0.55;
}
</style>

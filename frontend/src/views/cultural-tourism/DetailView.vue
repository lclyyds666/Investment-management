<template>
  <div class="ct-detail">
    <!-- 返回 + 标题 -->
    <div class="ct-detail-head">
      <el-button :icon="ArrowLeft" @click="goBack">返回文旅业务</el-button>
      <h2 v-if="spot" class="ct-detail-title">{{ spot.name }}</h2>
    </div>

    <template v-if="spot">
      <!-- 顶部：平台入口 -->
      <el-card shadow="never" class="ct-section">
        <template #header>
          <div class="sec-header"><el-icon><Link /></el-icon><span>平台入口</span></div>
        </template>
        <div class="platform-grid">
          <a
            v-for="p in spot.platformList"
            :key="p.key"
            class="platform-item"
            :href="p.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="platform-badge" :style="{ background: p.color }">{{ p.name.slice(0, 1) }}</span>
            <span class="platform-name">{{ p.name }}</span>
            <el-icon class="platform-go"><TopRight /></el-icon>
          </a>
        </div>
      </el-card>

      <!-- 底部：核销数据台账（作用域组件，scenicId 作为 Props 传入） -->
      <el-card shadow="never" class="ct-section">
        <ScenicLedger :scenic-id="scenicId" />
      </el-card>
    </template>

    <el-empty v-else description="未找到该景区" :image-size="90">
      <el-button type="primary" @click="goBack">返回文旅业务</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Link, TopRight } from '@element-plus/icons-vue'
import { getScenicById } from '@/constants/scenic'
import ScenicLedger from '@/components/ScenicLedger.vue'

const route = useRoute()
const router = useRouter()

// 通过动态路由参数识别当前景区（数据作用域键）
const scenicId = computed(() => String(route.params.scenicId || ''))
const spot = computed(() => getScenicById(scenicId.value))

function goBack() {
  router.push('/cultural-tourism')
}
</script>

<style scoped lang="scss">
.ct-detail { padding: 4px; }
.ct-detail-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}
.ct-detail-title {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--el-text-color-primary);
}
.ct-section { margin-bottom: 16px; }
.sec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  .el-icon { color: var(--el-color-primary); }
}
/* 平台入口：图标/名称规律排列 */
.platform-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
.platform-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  text-decoration: none;
  color: var(--el-text-color-primary);
  transition: all 0.2s ease;
  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 4px 14px rgba(34, 211, 238, 0.2);
    transform: translateY(-2px);
  }
}
.platform-badge {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 800;
  font-size: 16px;
  flex-shrink: 0;
}
.platform-name { flex: 1; font-weight: 600; }
.platform-go { color: var(--el-text-color-secondary); }
</style>

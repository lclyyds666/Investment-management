<template>
  <div class="ct-detail">
    <!-- 返回 + 标题 -->
    <div class="ct-detail-head">
      <el-button :icon="ArrowLeft" @click="goBack">返回文旅业务</el-button>
      <h2 v-if="spot" class="ct-detail-title">{{ spot.name }}</h2>
    </div>

    <template v-if="spot">
      <!-- 顶部：平台入口（分组展示：景区平台 / 门票平台） -->
      <el-card shadow="never" class="ct-section">
        <template #header>
          <div class="sec-header"><el-icon><Link /></el-icon><span>平台入口</span></div>
        </template>

        <div
          v-for="group in platformGroups"
          :key="group.key"
          class="entry-group"
        >
          <div class="group-title">
            <span class="group-dot" :class="group.key"></span>{{ group.title }}
          </div>
          <div v-if="group.items.length" class="platform-grid">
            <a
              v-for="p in group.items"
              :key="p.key"
              class="platform-item"
              :href="p.url"
              target="_blank"
              rel="noopener noreferrer"
              :title="`前往 ${p.name}·${spot.name}`"
            >
              <img class="platform-logo" :src="p.logo" :alt="p.name" loading="lazy" />
              <span class="platform-name">{{ p.name }}</span>
              <el-icon class="platform-go"><TopRight /></el-icon>
            </a>
          </div>
          <div v-else class="entry-empty">暂无入口</div>
        </div>
      </el-card>

      <!-- 底部：核销数据台账（按平台类型分选项卡；scenicId 作为数据作用域键） -->
      <el-card shadow="never" class="ct-section">
        <el-tabs v-model="ledgerTab" class="ledger-tabs">
          <el-tab-pane label="门票平台核销台账" name="ticket">
            <TicketLedger :scenic-id="scenicId" />
            <!-- 原始明细预览（保留，可折叠对照/校验） -->
            <el-collapse class="raw-collapse">
              <el-collapse-item name="raw">
                <template #title>
                  <el-icon><Files /></el-icon>
                  <span style="margin-left: 6px">原始核销明细预览（对照/校验用）</span>
                </template>
                <ScenicLedger :scenic-id="scenicId" />
              </el-collapse-item>
            </el-collapse>
          </el-tab-pane>

          <el-tab-pane label="景区平台核销台账" name="scenic">
            <el-empty description="景区平台核销台账开发中，敬请期待" :image-size="90" />
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>

    <el-empty v-else description="未找到该景区" :image-size="90">
      <el-button type="primary" @click="goBack">返回文旅业务</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Link, TopRight, Files } from '@element-plus/icons-vue'
import { getScenicById } from '@/constants/scenic'
import ScenicLedger from '@/components/ScenicLedger.vue'
import TicketLedger from '@/components/TicketLedger.vue'

// 核销台账选项卡：门票平台（本期实现）/ 景区平台（占位待开发）
const ledgerTab = ref('ticket')

const route = useRoute()
const router = useRouter()

// 通过动态路由参数识别当前景区（数据作用域键）
const scenicId = computed(() => String(route.params.scenicId || ''))
const spot = computed(() => getScenicById(scenicId.value))

// 平台入口分组：景区平台入口 / 门票平台入口（空数组渲染「暂无入口」空状态）
const platformGroups = computed(() => {
  const s = spot.value
  if (!s) return []
  return [
    { key: 'scenic', title: '景区平台入口', items: s.scenicPlatforms || [] },
    { key: 'ticket', title: '门票平台入口', items: s.ticketPlatforms || [] }
  ]
})

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
/* 平台入口·分组 */
.entry-group {
  & + .entry-group {
    margin-top: 20px;
    padding-top: 18px;
    border-top: 1px dashed var(--el-border-color);
  }
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}
.group-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  &.scenic { background: var(--el-color-primary); }
  &.ticket { background: #f59e0b; }
}
.entry-empty {
  color: var(--el-text-color-secondary);
  font-style: italic;
  font-size: 13px;
  padding: 6px 2px;
}

/* 平台入口：Logo + 名称规律排列 */
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
    .platform-logo { transform: scale(1.12); }
    .platform-go { color: var(--el-color-primary); }
  }
}
.platform-logo {
  height: 30px;
  width: auto;
  max-width: 80px;
  flex-shrink: 0;
  display: block;
  object-fit: contain;
  transition: transform 0.2s ease;
}
.platform-name { flex: 1; font-weight: 600; }
.platform-go {
  color: var(--el-text-color-secondary);
  transition: color 0.2s ease;
}

/* 响应式：窄屏单列，标题与列表左对齐 */
@media (max-width: 640px) {
  .platform-grid { grid-template-columns: 1fr; }
}
</style>

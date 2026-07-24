<template>
  <div class="ct-detail">
    <!-- 返回 + 标题 -->
    <div class="ct-detail-head">
      <el-button :icon="ArrowLeft" @click="goBack">返回文旅业务</el-button>
      <h2 v-if="spot" class="ct-detail-title">{{ spot.name }}</h2>
    </div>

    <template v-if="spot">
      <!-- 经营数据 + 平台入口：左右两栏，等高自适应（矮的一栏底部留白） -->
      <div class="ct-cols">
      <!-- ① 经营数据（3 张指标卡竖排，随框宽自适应） -->
      <el-card shadow="never" class="ct-section ct-col">
        <template #header>
          <div class="sec-header"><el-icon><TrendCharts /></el-icon><span>经营数据</span></div>
        </template>
        <div class="biz-grid">
          <div v-for="m in bizMetrics" :key="m.key" class="biz-card" :class="m.key">
            <div class="biz-icon"><el-icon><component :is="m.icon" /></el-icon></div>
            <div class="biz-body">
              <div class="biz-value">
                {{ m.value }}<span v-if="m.unit" class="biz-unit">{{ m.unit }}</span>
              </div>
              <div class="biz-label">{{ m.label }}</div>
            </div>
          </div>
        </div>
        <div class="biz-note">
          <el-icon><InfoFilled /></el-icon>
          <span>销售额 = 门票+酒店核销台账「结算金额」之和；核销数 = 对账明细订单数；核销率 = 实收/结算为正数的订单占比。随台账实时更新（本景区独立）。</span>
        </div>
      </el-card>

      <!-- ② 平台入口（分组展示：景区酒店平台 / 景区门票平台；平台卡两列等大） -->
      <el-card shadow="never" class="ct-section ct-col">
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
      </div>

      <!-- ③ 底部：核销数据台账（折叠面板，默认收起；点击标题栏平滑展开） -->
      <el-collapse v-model="ledgerActive" class="ledger-collapse">
        <el-collapse-item name="ledger">
          <template #title>
            <div class="ledger-title">
              <el-icon><Tickets /></el-icon>
              <span>核销数据台账</span>
              <el-tag size="small" type="info" effect="plain" round>Excel 上传 · 汇总</el-tag>
            </div>
          </template>

          <el-tabs v-model="ledgerTab" class="ledger-tabs">
            <el-tab-pane label="景区门票核销台账" name="ticket">
              <TicketLedger :scenic-id="scenicId" />
              <!-- 原始核销明细预览（对照/校验用）：仅展示已保存的对账明细源文件，点击查看/下载 -->
              <el-collapse class="raw-collapse">
                <el-collapse-item name="raw">
                  <template #title>
                    <el-icon><Files /></el-icon>
                    <span style="margin-left: 6px">原始核销明细预览（对照/校验用）</span>
                  </template>
                  <TicketDetailFiles :scenic-id="scenicId" />
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>

            <el-tab-pane label="景区酒店核销台账" name="scenic">
              <HotelLedger :scenic-id="scenicId" />
              <!-- 原始核销明细预览（对照/校验用）：仅列源文件，可查看/下载 -->
              <el-collapse class="raw-collapse">
                <el-collapse-item name="raw-hotel">
                  <template #title>
                    <el-icon><Files /></el-icon>
                    <span style="margin-left: 6px">原始核销明细预览（对照/校验用）</span>
                  </template>
                  <HotelDetailFiles :scenic-id="scenicId" />
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>
          </el-tabs>
        </el-collapse-item>
      </el-collapse>
    </template>

    <el-empty v-else description="未找到该景区" :image-size="90">
      <el-button type="primary" @click="goBack">返回文旅业务</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Link, TopRight, Files, Tickets, TrendCharts, InfoFilled,
  Checked, Money, DataLine
} from '@element-plus/icons-vue'
import { getScenicById } from '@/constants/scenic'
import { getScenicMetrics } from '@/api/scenic'
import TicketLedger from '@/components/TicketLedger.vue'
import TicketDetailFiles from '@/components/TicketDetailFiles.vue'
import HotelLedger from '@/components/HotelLedger.vue'
import HotelDetailFiles from '@/components/HotelDetailFiles.vue'

// 核销台账选项卡：门票平台（本期实现）/ 景区平台（占位待开发）
const ledgerTab = ref('ticket')
// 台账折叠面板：默认收起（空数组即全部收起）
const ledgerActive = ref([])

const route = useRoute()
const router = useRouter()

// 通过动态路由参数识别当前景区（数据作用域键）
const scenicId = computed(() => String(route.params.scenicId || ''))
const spot = computed(() => getScenicById(scenicId.value))

// 经营数据（每景区独立，源自门票+酒店核销台账实时聚合）
const metrics = ref({ sales: 0, writeoff_count: 0, positive_count: 0, rate: 0 })
function fmtNum(n) { return Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
async function loadMetrics() {
  if (!scenicId.value) return
  try { metrics.value = await getScenicMetrics(scenicId.value) } catch { /* 拦截器已提示 */ }
}
watch(scenicId, loadMetrics, { immediate: true })

const bizMetrics = computed(() => [
  { key: 'sales', label: '销售额', value: fmtNum(metrics.value.sales), unit: '元', icon: Money },
  { key: 'month', label: '核销数', value: fmtNum(metrics.value.writeoff_count), unit: '笔', icon: Checked },
  { key: 'rate', label: '核销率', value: fmtNum(metrics.value.rate), unit: '%', icon: DataLine }
])

// 平台入口分组：景区酒店平台入口 / 景区门票平台入口（空数组渲染「暂无入口」空状态）
const platformGroups = computed(() => {
  const s = spot.value
  if (!s) return []
  return [
    { key: 'scenic', title: '景区酒店平台入口', items: s.scenicPlatforms || [] },
    { key: 'ticket', title: '景区门票平台入口', items: s.ticketPlatforms || [] }
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
/* 经营数据 + 平台入口 左右两栏：等高（align-items:stretch 使两栏同高=较高者，较矮者底部留白） */
.ct-cols {
  display: flex;
  align-items: stretch;
  gap: 16px;
  margin-bottom: 16px;
}
.ct-col {
  flex: 1 1 0;
  min-width: 0;
  margin-bottom: 0;
}
.sec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  .el-icon { color: var(--el-color-primary); }
}

/* ① 经营数据·指标卡：竖排铺满栏宽（数字再长也不溢出） */
.biz-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.biz-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  transition: all 0.2s ease;
  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 4px 16px rgba(34, 211, 238, 0.14);
    transform: translateY(-2px);
  }
}
.biz-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--el-color-primary-light-9);
  .el-icon { font-size: 24px; color: var(--el-color-primary); }
}
.biz-card.sales .biz-icon { background: rgba(245, 158, 11, 0.14); .el-icon { color: #f59e0b; } }
.biz-card.rate .biz-icon  { background: rgba(16, 185, 129, 0.14); .el-icon { color: #10b981; } }
.biz-card.month .biz-icon { background: rgba(139, 92, 246, 0.14); .el-icon { color: #8b5cf6; } }
.biz-body { min-width: 0; flex: 1; }
.biz-value {
  font-size: 24px;
  font-weight: 800;
  line-height: 1.2;
  color: var(--el-text-color-primary);
  overflow-wrap: anywhere;   /* 数字过长时在框内换行，不溢出到框外 */
}
.biz-unit {
  font-size: 13px;
  font-weight: 600;
  margin-left: 4px;
  color: var(--el-text-color-secondary);
}
.biz-label {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.biz-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  .el-icon { color: var(--el-color-info); }
}

/* ② 平台入口·分组 */
.entry-group {
  & + .entry-group {
    margin-top: 22px;
    padding-top: 20px;
    border-top: 1px dashed var(--el-border-color);
  }
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 15px;
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

/* 平台入口：两列等大网格；所有平台卡尺寸/高度一致（同栏同 grid + 固定最小高度） */
.platform-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.platform-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  min-width: 0;
  min-height: 68px;
  box-sizing: border-box;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  text-decoration: none;
  color: var(--el-text-color-primary);
  transition: all 0.2s ease;
  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 6px 20px rgba(34, 211, 238, 0.22);
    transform: translateY(-3px);
    .platform-logo { transform: scale(1.12); }
    .platform-go { color: var(--el-color-primary); }
  }
}
.platform-logo {
  height: 40px;
  width: 40px;
  flex-shrink: 0;
  display: block;
  object-fit: contain;
  transition: transform 0.2s ease;
}
.platform-name {
  flex: 1;
  min-width: 0;
  font-weight: 700;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.platform-go {
  color: var(--el-text-color-secondary);
  font-size: 18px;
  flex-shrink: 0;
  transition: color 0.2s ease;
}

/* ③ 核销数据台账·折叠面板 */
.ledger-collapse {
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  :deep(.el-collapse-item__header) {
    padding: 4px 18px;
    height: 58px;
    font-size: 15px;
    font-weight: 700;
    border-bottom: none;
  }
  :deep(.el-collapse-item__wrap) { border-bottom: none; }
  :deep(.el-collapse-item__content) { padding: 4px 18px 18px; }
}
.ledger-title {
  display: flex;
  align-items: center;
  gap: 8px;
  .el-icon { color: var(--el-color-primary); font-size: 18px; }
}

/* 响应式：窄屏两栏改上下堆叠；平台卡改单列 */
@media (max-width: 900px) {
  .ct-cols { flex-direction: column; }
  .ct-col { margin-bottom: 0; }
}
@media (max-width: 640px) {
  .platform-grid { grid-template-columns: 1fr; }
}
</style>

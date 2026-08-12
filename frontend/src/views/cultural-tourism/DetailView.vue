<template>
  <div class="ct-detail">
    <!-- 返回 + 标题 -->
    <div class="ct-detail-head">
      <div class="head-copy">
        <el-button class="back-button" text :icon="ArrowLeft" @click="goBack">返回文旅业务</el-button>
        <p class="page-eyebrow">SCENIC LEDGER</p>
        <h1 v-if="spot" class="page-title ct-detail-title">{{ spot.name }}</h1>
        <p v-if="spot" class="page-subtitle">平台入口、经营指标与核销台账均按当前景区独立归集。</p>
      </div>
      <div v-if="spot" class="module-tags">
        <el-tag v-if="ticketEnabled" effect="plain" round>门票业务</el-tag>
        <el-tag v-if="hotelEnabled" type="success" effect="plain" round>酒店业务</el-tag>
      </div>
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
          <span>销售额 = 门票+酒店核销台账「结算金额」之和；核销数 = 对账明细订单数。随台账实时更新（本景区独立）。</span>
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
              :style="{ '--platform-color': p.color }"
            >
              <img class="platform-logo" :src="p.logo" :alt="p.name" loading="lazy" />
              <span class="platform-name">{{ p.name }}</span>
              <el-icon class="platform-go"><TopRight /></el-icon>
            </a>
          </div>
          <el-empty v-else class="entry-empty" :image-size="46" description="当前景区暂未配置平台入口" />
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
            <el-tab-pane v-if="ticketEnabled" label="景区门票核销台账" name="ticket">
              <TicketLedger :scenic-id="scenicId" />
              <!-- 原始核销明细预览（对照/校验用）：仅展示已保存的对账明细源文件，点击查看/下载 -->
              <el-collapse class="raw-collapse">
                <el-collapse-item name="raw">
                  <template #title>
                    <el-icon><Files /></el-icon>
                    <span class="raw-title">原始核销明细预览（对照/校验用）</span>
                  </template>
                  <TicketDetailFiles :scenic-id="scenicId" />
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>

            <el-tab-pane v-if="hotelEnabled" label="景区酒店核销台账" name="scenic">
              <HotelLedger :scenic-id="scenicId" />
              <!-- 原始核销明细预览（对照/校验用）：仅列源文件，可查看/下载 -->
              <el-collapse class="raw-collapse">
                <el-collapse-item name="raw-hotel">
                  <template #title>
                    <el-icon><Files /></el-icon>
                    <span class="raw-title">原始核销明细预览（对照/校验用）</span>
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
  Checked, Money
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
const ticketEnabled = computed(() => spot.value?.ticketEnabled !== false)
const hotelEnabled = computed(() => spot.value?.hotelEnabled === true)

// 景区没有酒店业务时只显示门票台账；反之亦然，避免空模块触发无意义请求。
watch([ticketEnabled, hotelEnabled], () => {
  if (ticketEnabled.value) ledgerTab.value = 'ticket'
  else if (hotelEnabled.value) ledgerTab.value = 'scenic'
})

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
  { key: 'month', label: '核销数', value: fmtNum(metrics.value.writeoff_count), unit: '笔', icon: Checked }
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
  router.push({ name: 'CulturalTourism' })
}
</script>

<style scoped lang="scss">
.ct-detail { padding: 2px; }
.ct-detail-head {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-6);
  margin-bottom: var(--space-6);
  padding: 4px 4px 20px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  &::before {
    position: absolute;
    top: 36px;
    bottom: 20px;
    left: 0;
    width: 4px;
    border-radius: var(--radius-xs);
    background: var(--divider-rail);
    content: '';
  }
}
.head-copy { min-width: 0; }
.back-button { margin: 0 0 var(--space-4) -12px; color: var(--el-text-color-secondary); }
.ct-detail-title {
  max-width: 860px;
}
.module-tags { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; padding-bottom: 4px; }
.ct-section { margin-bottom: 16px; }
/* 经营数据 + 平台入口 左右两栏：等高（align-items:stretch 使两栏同高=较高者，较矮者底部留白） */
.ct-cols {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  align-items: stretch;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
}
.ct-col {
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
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.biz-card {
  min-width: 0;
  padding: clamp(18px, 2vw, 28px);
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  transition: all var(--motion-base) ease;
  &:hover {
    border-color: var(--surface-border-strong);
    box-shadow: var(--surface-shadow);
    transform: translateY(-3px);
  }
}
.biz-icon {
  width: 42px;
  height: 42px;
  margin-bottom: var(--space-5);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--el-color-primary-light-9);
  .el-icon { font-size: 24px; color: var(--el-color-primary); }
}
.biz-card.sales .biz-icon { background: color-mix(in srgb, var(--metric-warning) 14%, transparent); .el-icon { color: var(--metric-warning); } }
.biz-card.rate .biz-icon  { background: color-mix(in srgb, var(--metric-profit) 14%, transparent); .el-icon { color: var(--metric-profit); } }
.biz-card.month .biz-icon { background: color-mix(in srgb, var(--metric-realized) 14%, transparent); .el-icon { color: var(--metric-realized); } }
.biz-body { min-width: 0; flex: 1; }
.biz-value {
  font-size: clamp(25px, 2.3vw, 38px);
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
  &.ticket { background: var(--brand-vermilion); }
}
.entry-empty {
  padding: 0;
  :deep(.el-empty__description) { margin-top: 4px; }
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
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  text-decoration: none;
  color: var(--el-text-color-primary);
  transition: all var(--motion-base) ease;
  &:hover {
    border-color: var(--platform-color, var(--el-color-primary));
    box-shadow: var(--surface-shadow);
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
  filter: drop-shadow(0 5px 8px color-mix(in srgb, var(--platform-color, var(--el-color-primary)) 18%, transparent));
  transition: transform var(--motion-base) ease;
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
  transition: color var(--motion-base) ease;
}

/* ③ 核销数据台账·折叠面板 */
.ledger-collapse {
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
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
.raw-title { margin-left: 6px; }
.ledger-title {
  display: flex;
  align-items: center;
  gap: 8px;
  .el-icon { color: var(--el-color-primary); font-size: 18px; }
}

/* 响应式：窄屏两栏改上下堆叠；平台卡改单列 */
@media (max-width: 900px) {
  .ct-detail-head { align-items: flex-start; flex-direction: column; }
  .module-tags { justify-content: flex-start; }
  .ct-cols { grid-template-columns: 1fr; }
  .ct-col { margin-bottom: 0; }
}
@media (max-width: 640px) {
  .biz-grid { grid-template-columns: 1fr; }
  .platform-grid { grid-template-columns: 1fr; }
}
</style>

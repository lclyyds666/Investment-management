<template>
  <div class="ct-main">
    <header class="page-intro ct-intro">
      <div>
        <p class="page-eyebrow">SCENIC OPERATIONS</p>
        <h1 class="page-title">文旅业务</h1>
        <p class="page-subtitle">按景区进入独立经营空间，集中查看平台入口、经营指标与核销台账。</p>
      </div>
      <div class="ct-head-actions">
        <el-button :icon="Setting" @click="configDialog?.open()">景区配置</el-button>
        <div class="ct-summary" aria-label="景区数量">
          <strong>{{ scenicSpots.length }}</strong>
          <span>个景区<br />统一运营</span>
        </div>
      </div>
    </header>

    <div class="ct-grid">
      <div
        v-for="spot in scenicSpots"
        :key="spot.id"
        class="ct-card"
        role="button"
        tabindex="0"
        @click="goDetail(spot.id)"
        @keyup.enter="goDetail(spot.id)"
      >
        <div class="ct-card-img">
          <img
            v-if="!failed[spot.id]"
            :src="spot.imagePath"
            :alt="spot.name"
            @error="failed[spot.id] = true"
          />
          <div v-else class="ct-card-fallback">
            <el-icon><Place /></el-icon>
          </div>
          <div class="ct-card-shade"></div>
          <div class="ct-card-content">
            <div class="ct-card-meta">
              <span v-if="spot.ticketEnabled">门票台账</span>
              <span v-if="spot.hotelEnabled">酒店台账</span>
            </div>
            <div class="ct-card-bottom">
              <div>
                <h2>{{ spot.name }}</h2>
                <p>{{ spot.id }}</p>
              </div>
              <span class="ct-enter"><el-icon><ArrowRight /></el-icon></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <ScenicConfigDialog ref="configDialog" />
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Place, Setting } from '@element-plus/icons-vue'
import { scenicSpots } from '@/constants/scenic'
import ScenicConfigDialog from '@/components/ScenicConfigDialog.vue'

const router = useRouter()
const failed = reactive({}) // 图片加载失败 → 降级占位
const configDialog = ref(null)

function goDetail(id) {
  router.push({ name: 'CulturalTourismDetail', params: { scenicId: id } })
}
</script>

<style scoped lang="scss">
.ct-main {
  padding: 4px 2px 28px;
}
.ct-intro { margin-inline: auto; }
.ct-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ct-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
  color: var(--el-text-color-secondary);
  background: var(--surface);
  box-shadow: var(--surface-shadow);
  font-size: 12px;
  line-height: 1.45;
  strong {
    color: var(--brand-lake);
    font-family: var(--font-data);
    font-size: 32px;
    line-height: 1;
  }
}
.ct-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(16px, 1.8vw, 28px);
  max-width: var(--page-max-width);
  margin: 0 auto;
}
.ct-card {
  min-width: 0;
  cursor: pointer;
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--surface-shadow);
  transition: all var(--motion-base) ease;
  &:hover,
  &:focus-visible {
    border-color: var(--surface-border-strong);
    transform: translateY(-5px);
    box-shadow: var(--surface-shadow-raised);
    .ct-card-img img { transform: scale(1.045); }
    .ct-enter { color: var(--el-color-white); background: var(--brand-vermilion); transform: translateX(3px); }
  }
}
.ct-card-img {
  position: relative;
  height: clamp(220px, 20vw, 330px);
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 700ms cubic-bezier(0.2, 0.7, 0.2, 1);
  }
}
.ct-card-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    transparent 28%,
    color-mix(in srgb, var(--screen-bg) 86%, transparent)
  );
}
.ct-card-content {
  position: absolute;
  inset: 0;
  padding: clamp(16px, 1.6vw, 24px);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  color: var(--el-color-white);
}
.ct-card-meta {
  display: flex;
  gap: 8px;
  span {
    padding: 5px 9px;
    border: 1px solid color-mix(in srgb, var(--screen-text) 34%, transparent);
    border-radius: var(--el-border-radius-round);
    background: color-mix(in srgb, var(--screen-bg) 34%, transparent);
    backdrop-filter: blur(10px);
    font-size: 11px;
    font-weight: 650;
  }
}
.ct-card-bottom {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  h2 { margin: 0; font-family: var(--font-display); font-size: clamp(20px, 1.55vw, 28px); font-weight: 800; letter-spacing: 0.03em; }
  p { margin: 6px 0 0; color: color-mix(in srgb, var(--screen-text) 68%, transparent); font-family: var(--font-data); font-size: 11px; letter-spacing: 0.06em; }
}
.ct-enter {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--screen-text) 44%, transparent);
  border-radius: 50%;
  background: color-mix(in srgb, var(--screen-bg) 32%, transparent);
  transition: all var(--motion-base) ease;
}
.ct-card-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--brand-ink), var(--brand-lake));
  .el-icon {
    font-size: 52px;
    color: color-mix(in srgb, var(--el-color-white) 85%, transparent);
  }
}

@media (max-width: 1180px) {
  .ct-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ct-card-img { height: 280px; }
}

@media (max-width: 720px) {
  .ct-head-actions { width: 100%; justify-content: space-between; }
  .ct-summary { align-self: stretch; justify-content: center; }
  .ct-grid { grid-template-columns: 1fr; }
  .ct-card-img { height: 250px; }
}
</style>

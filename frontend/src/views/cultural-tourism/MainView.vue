<template>
  <div class="ct-main">
    <h1 class="ct-title">文旅业务</h1>
    <p class="ct-subtitle">选择景区，查看平台入口与核销数据台账</p>

    <div class="ct-grid">
      <div
        v-for="spot in scenicSpots"
        :key="spot.id"
        class="ct-card"
        @click="goDetail(spot.id)"
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
          <div class="ct-card-mask"></div>
          <span class="ct-card-name">{{ spot.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Place } from '@element-plus/icons-vue'
import { scenicSpots } from '@/constants/scenic'

const router = useRouter()
const failed = reactive({}) // 图片加载失败 → 降级占位

function goDetail(id) {
  router.push(`/cultural-tourism/${id}`)
}
</script>

<style scoped lang="scss">
.ct-main {
  padding: 8px 4px 24px;
}
.ct-title {
  text-align: center;
  margin: 18px 0 6px;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 4px;
  background: linear-gradient(90deg, #39c5ff, #22d3ee);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.ct-subtitle {
  text-align: center;
  margin: 0 0 26px;
  color: #909399;
  font-size: 14px;
}
/* Grid：每行严格 3 个卡片，卡片间距 40px */
.ct-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 40px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 4px 8px 8px;
  box-sizing: border-box;
}
.ct-card {
  cursor: pointer;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 4px 18px rgba(4, 20, 48, 0.18);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 28px rgba(34, 211, 238, 0.28);
  }
}
.ct-card-img {
  position: relative;
  height: 168px;
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}
.ct-card-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0e2450, #1c9be6);
  .el-icon {
    font-size: 52px;
    color: rgba(255, 255, 255, 0.85);
  }
}
.ct-card-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0) 45%, rgba(4, 20, 48, 0.72) 100%);
}
.ct-card-name {
  position: absolute;
  left: 14px;
  bottom: 12px;
  right: 14px;
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}
</style>

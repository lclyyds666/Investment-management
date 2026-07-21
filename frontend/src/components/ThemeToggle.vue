<template>
  <!-- 主题切换按钮:明亮显示太阳、暗黑显示月亮;悬停 Tooltip 提示目标模式 -->
  <el-tooltip :content="tip" placement="bottom" :show-after="200">
    <button class="theme-toggle" type="button" :aria-label="tip" @click="onToggle">
      <el-icon :size="18">
        <Sunny v-if="isDark" />
        <Moon v-else />
      </el-icon>
    </button>
  </el-tooltip>
</template>

<script setup>
import { computed } from 'vue'
import { Sunny, Moon } from '@element-plus/icons-vue'
import { useThemeStore } from '@/store/theme'

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.mode === 'dark')
// 暗色态下按钮引导「切回明亮」,反之亦然
const tip = computed(() => (isDark.value ? '切换至明亮模式' : '切换至暗黑模式'))

function onToggle() {
  themeStore.toggle()
}
</script>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--chrome-header-border, var(--el-border-color));
  border-radius: 50%;
  background: transparent;
  color: var(--chrome-title-color, var(--el-text-color-primary));
  cursor: pointer;
  transition: all 0.2s ease;
}
.theme-toggle:hover {
  color: var(--tech-cyan);
  border-color: var(--tech-cyan);
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.35);
  transform: rotate(18deg);
}
</style>

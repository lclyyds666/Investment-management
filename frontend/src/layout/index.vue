<template>
  <el-container class="app-wrapper">
    <el-aside width="220px" class="sidebar">
      <div class="logo">出版供应链平台</div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="transparent"
        text-color="#a9c2e0"
        active-text-color="#22d3ee"
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.meta.icon" /></el-icon>
          <span>{{ item.meta.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="title">山东出版供应链管理公司业务平台</span>
        <el-dropdown @command="onCommand">
          <span class="user">
            {{ userStore.userInfo?.full_name || '用户' }}
            <el-tag size="small" type="warning" effect="plain">{{ roleLabel }}</el-tag>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile" :icon="User">个人设置</el-dropdown-item>
              <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, User, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { roleLabel as toRoleLabel } from '@/constants/business'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

// 优先用后端返回的角色中文名，回退到本地映射
const roleLabel = computed(() => userStore.roleLabel || toRoleLabel(userStore.role))

// 从路由表生成菜单，并按角色过滤
const menus = computed(() => {
  const root = router.options.routes.find((r) => r.path === '/')
  return (root?.children || [])
    .filter((c) => c.meta?.title)
    .filter((c) => userStore.hasRole(c.meta.roles))
    .map((c) => ({ path: '/' + c.path, meta: c.meta }))
})

function onCommand(cmd) {
  if (cmd === 'logout') {
    userStore.logout()
    router.replace('/login')
  } else if (cmd === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped lang="scss">
.app-wrapper {
  height: 100%;
}
/* 深色霓虹侧边栏 */
.sidebar {
  background: linear-gradient(180deg, #0a1b3a 0%, #071228 100%);
  position: relative;
  border-right: 1px solid rgba(34, 211, 238, 0.14);
  .logo {
    height: 60px;
    line-height: 60px;
    text-align: center;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1px;
    background: linear-gradient(90deg, #39c5ff, #22d3ee);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-shadow: 0 0 18px rgba(34, 211, 238, 0.4);
    border-bottom: 1px solid rgba(34, 211, 238, 0.14);
  }
  :deep(.el-menu) {
    border-right: none;
    padding: 8px;
  }
  :deep(.el-menu-item) {
    height: 46px;
    border-radius: 8px;
    margin-bottom: 4px;
  }
  :deep(.el-menu-item:hover) {
    background: rgba(34, 211, 238, 0.08) !important;
    color: #d7f6ff !important;
  }
  :deep(.el-menu-item.is-active) {
    background: linear-gradient(90deg, rgba(34, 211, 238, 0.22), rgba(28, 155, 230, 0.05)) !important;
    box-shadow: inset 3px 0 0 #22d3ee, 0 0 16px rgba(34, 211, 238, 0.18);
  }
}
/* 玻璃质感顶栏 */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(90deg, #0a1b3a, #0e2450);
  border-bottom: 1px solid rgba(34, 211, 238, 0.2);
  box-shadow: 0 2px 16px rgba(4, 20, 48, 0.4);
  .title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
    background: linear-gradient(90deg, #eafcff, #7fd8ff);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .user {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    outline: none;
    color: #cfe6ff;
  }
}
</style>

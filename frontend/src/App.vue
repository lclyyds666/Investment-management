<template>
  <!-- 全局配置容器:承载 locale 等全局配置,与 <html class="dark"> 的主题机制协同。
       等价于 antd 的 ConfigProvider(主题切换由 store/theme.js 驱动 html.dark 完成)。 -->
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>

<script setup>
// 根组件
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>

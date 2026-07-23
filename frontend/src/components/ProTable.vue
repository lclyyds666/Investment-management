<template>
  <el-card shadow="never" class="pro-table">
    <!-- 头部：标题 + 关键词搜索 + 右侧工具区(slot) -->
    <template #header>
      <div class="pt-header">
        <span class="pt-title">{{ title }}</span>
        <div class="pt-tools">
          <el-input
            v-if="searchKeys.length"
            v-model="keyword"
            :placeholder="searchPlaceholder"
            :prefix-icon="Search"
            clearable
            class="pt-search"
          />
          <slot name="toolbar" :reload="reload" />
        </div>
      </div>
    </template>

    <!-- 首屏加载：骨架屏(优于转圈遮罩的感知速度) -->
    <el-skeleton v-if="firstLoading" :rows="6" animated />

    <!-- 加载失败:错误态 + 重试(区别于「暂无数据」) -->
    <el-empty v-else-if="error" :image-size="90" description="加载失败，请检查网络后重试">
      <el-button type="primary" :icon="Refresh" @click="reload">重新加载</el-button>
    </el-empty>

    <!-- 正常表格：重载时用 v-loading 遮罩(已有数据不闪骨架) -->
    <template v-else>
      <el-table
        v-loading="loading"
        :data="pagedRows"
        :row-key="rowKey"
        border
        stripe
        :height="height"
      >
        <el-table-column
          v-for="col in columns"
          :key="col.prop || col.label"
          :prop="col.slot || col.formatter ? undefined : col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          :align="col.align"
          :fixed="col.fixed"
          :sortable="col.sortable"
          :show-overflow-tooltip="col.showOverflowTooltip"
        >
          <template v-if="col.slot || col.formatter" #default="scope">
            <slot v-if="col.slot" :name="col.slot" :row="scope.row" :$index="scope.$index" />
            <template v-else>{{ col.formatter(scope.row) }}</template>
          </template>
        </el-table-column>
        <template #empty>{{ emptyText }}</template>
      </el-table>

      <!-- 分页:客户端分页(数据量增长后可平滑切换为服务端分页) -->
      <div v-if="showPagination" class="pt-pager">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="innerPageSize"
          :total="filteredRows.length"
          :page-sizes="pageSizes"
          layout="total, sizes, prev, pager, next, jumper"
          background
        />
      </div>
    </template>
  </el-card>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  // 标题
  title: { type: String, default: '' },
  // 数据获取函数:async () => Array。组件内部持有 loading/error 状态。
  fetch: { type: Function, required: true },
  // 列配置:[{ prop, label, width, minWidth, align, fixed, sortable,
  //           showOverflowTooltip, slot, formatter }]
  //   · slot:具名插槽渲染(如操作列、tag 列),插槽入参 { row, $index }
  //   · formatter:(row) => string,轻量文本格式化(如金额千分位)
  columns: { type: Array, required: true },
  // 参与关键词过滤的字段名;为空则不显示搜索框
  searchKeys: { type: Array, default: () => [] },
  searchPlaceholder: { type: String, default: '输入关键词搜索' },
  // 行 key
  rowKey: { type: String, default: 'id' },
  // 空数据文案
  emptyText: { type: String, default: '暂无数据' },
  // 分页
  pageSize: { type: Number, default: 10 },
  pageSizes: { type: Array, default: () => [10, 20, 50, 100] },
  // 表格固定高度(可选,不传则自适应内容)
  height: { type: [String, Number], default: undefined },
  // 是否挂载即加载
  immediate: { type: Boolean, default: true }
})

const emit = defineEmits(['loaded', 'error'])

const rows = ref([])
const loading = ref(false)
const firstLoading = ref(false)
const error = ref(false)
const loaded = ref(false)

const keyword = ref('')
const currentPage = ref(1)
const innerPageSize = ref(props.pageSize)

// 关键词过滤(客户端):命中任一 searchKey 即保留
const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw || !props.searchKeys.length) return rows.value
  return rows.value.filter((row) =>
    props.searchKeys.some((k) => String(row[k] ?? '').toLowerCase().includes(kw))
  )
})

const showPagination = computed(() => filteredRows.value.length > innerPageSize.value)

const pagedRows = computed(() => {
  if (!showPagination.value) return filteredRows.value
  const start = (currentPage.value - 1) * innerPageSize.value
  return filteredRows.value.slice(start, start + innerPageSize.value)
})

// 搜索或改页大小时回到第一页,避免停在越界页码
watch([keyword, innerPageSize], () => { currentPage.value = 1 })

async function reload() {
  loading.value = true
  if (!loaded.value) firstLoading.value = true
  error.value = false
  try {
    const data = await props.fetch()
    rows.value = Array.isArray(data) ? data : (data?.items ?? [])
    loaded.value = true
    emit('loaded', rows.value)
  } catch (e) {
    error.value = true
    emit('error', e) // 具体提示已由 axios 拦截器统一弹出
  } finally {
    loading.value = false
    firstLoading.value = false
  }
}

onMounted(() => { if (props.immediate) reload() })

// 供父组件在增删改后刷新
defineExpose({ reload })
</script>

<style scoped lang="scss">
.pt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.pt-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.pt-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pt-search {
  width: 220px;
}
.pt-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
/* 窄屏:搜索框占满一行,工具按钮换行不挤压标题 */
@media (max-width: 640px) {
  .pt-search { width: 100%; }
  .pt-tools { width: 100%; }
}
</style>

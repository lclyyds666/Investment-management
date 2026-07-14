<template>
  <el-dialog
    :model-value="modelValue"
    :title="`AI 智能调研 · ${customer?.name || ''}`"
    width="720px"
    top="6vh"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <!-- 1) 资料 -->
    <div class="block">
      <div class="block-title">
        <span>资料</span>
        <el-upload
          :auto-upload="false" :show-file-list="false" accept=".pdf,.docx" :on-change="onUpload"
        >
          <el-button size="small" type="primary" :icon="UploadFilled" :loading="uploading">
            上传资料（PDF / Docx）
          </el-button>
        </el-upload>
      </div>
      <el-table v-if="materials.length" :data="materials" size="small" border>
        <el-table-column prop="filename" label="文件" min-width="180" show-overflow-tooltip />
        <el-table-column prop="file_type" label="类型" width="70" align="center" />
        <el-table-column prop="page_count" label="页数" width="60" align="center" />
        <el-table-column label="关键信息" min-width="180">
          <template #default="{ row }">
            <span v-if="row.key_info?.capital || row.key_info?.credit_code" class="ki">
              {{ [row.key_info.capital && ('注册资本:' + row.key_info.capital),
                   row.key_info.credit_code && ('信用码:' + row.key_info.credit_code)].filter(Boolean).join(' / ') }}
            </span>
            <span v-else class="muted">未抽取到结构化字段</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="preview(row)">预览</el-button>
            <el-button size="small" link @click="download(row)">下载</el-button>
            <el-button size="small" link type="danger" @click="removeMaterial(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else :image-size="48" description="请先上传该客户的资料（PDF/Docx）" />
    </div>

    <!-- 2) 生成报告 + 分析状态栏 -->
    <div class="block">
      <div class="block-title">
        <span>尽职调查报告</span>
        <el-button
          type="success" :icon="MagicStick" :loading="generating"
          :disabled="!materials.length" @click="onGenerate"
        >
          {{ report ? '重新生成报告' : '生成调研报告' }}
        </el-button>
      </div>

      <!-- 分析状态栏 -->
      <el-steps v-if="generating" :active="step" finish-status="success" simple class="steps">
        <el-step title="读取准入资料" />
        <el-step title="联网检索资讯" />
        <el-step title="AI 智能综合" />
      </el-steps>

      <!-- 报告主体 -->
      <template v-if="report && !generating">
        <div class="rec-bar">
          <span>合作建议：</span>
          <el-tag :type="recType" size="large" effect="dark">{{ report.recommendation || '—' }}</el-tag>
          <el-tag class="engine" size="small" :type="report.engine === 'deepseek' ? 'success' : 'info'" effect="plain">
            {{ report.engine === 'deepseek' ? 'DeepSeek 综合' : '规则引擎(未接大模型)' }}
          </el-tag>
          <el-tag class="engine" size="small" :type="report.searched ? 'success' : 'warning'" effect="plain">
            {{ report.searched ? `已联网 · ${report.search_count} 条资讯` : '未联网核实' }}
          </el-tag>
        </div>

        <section class="rep-sec"><h4>【基础概况】</h4><p>{{ report.sections?.basic }}</p></section>
        <section class="rep-sec"><h4>【经营分析】</h4><p>{{ report.sections?.operation }}</p></section>
        <section class="rep-sec"><h4>【外部舆情】</h4><p>{{ report.sections?.sentiment }}</p></section>
        <section class="rep-sec"><h4>【AI 风险预警】</h4><p>{{ report.sections?.risk }}</p></section>
        <section v-if="report.sections?.key_risks?.length" class="rep-sec">
          <h4>关键风险点</h4>
          <ul><li v-for="(r, i) in report.sections.key_risks" :key="i">{{ r }}</li></ul>
        </section>

        <section class="rep-sec sources">
          <h4>信息来源</h4>
          <ol>
            <li v-for="s in webSources" :key="s.no">
              <a :href="s.ref" target="_blank" rel="noopener">{{ s.title }}</a>
              <span class="src-meta">{{ [s.site, s.date].filter(Boolean).join(' · ') }}</span>
            </li>
          </ol>
          <div v-for="(d, i) in docSources" :key="'d' + i" class="doc-src">
            📄 内部资料：{{ d.title }}（{{ d.ref }}）
          </div>
          <div v-if="!webSources.length" class="muted small">外部资讯：未联网核实（如需真实舆情/诉讼，请配置搜索 API Key）。</div>
        </section>

        <div class="report-actions">
          <el-button size="small" :icon="CopyDocument" @click="copyReport">复制全文</el-button>
          <span class="muted small">生成人：{{ report.created_by }} · {{ formatTime(report.created_at) }}</span>
        </div>
      </template>

      <el-empty v-else-if="!generating" :image-size="48" description="上传资料后点击「生成调研报告」" />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, MagicStick, CopyDocument } from '@element-plus/icons-vue'
import {
  listMaterials, uploadMaterial, deleteMaterial, fetchMaterialBlob,
  generateResearch, getResearch
} from '@/api/customer'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  customer: { type: Object, default: () => ({}) }
})
defineEmits(['update:modelValue'])

const materials = ref([])
const report = ref(null)
const uploading = ref(false)
const generating = ref(false)
const step = ref(0)
let stepTimer = null

const recType = computed(() => ({
  优先合作: 'success', 谨慎合作: 'warning', 严禁合作: 'danger'
}[report.value?.recommendation] || 'info'))
const webSources = computed(() => (report.value?.sources || []).filter((s) => s.type === 'web'))
const docSources = computed(() => (report.value?.sources || []).filter((s) => s.type === 'doc'))

async function onOpen() {
  report.value = null
  step.value = 0
  await Promise.all([loadMaterials(), loadReport()])
}

async function loadMaterials() {
  materials.value = await listMaterials(props.customer.id)
}
async function loadReport() {
  report.value = await getResearch(props.customer.id)
}

async function onUpload(f) {
  const raw = f.raw
  const name = (raw?.name || '').toLowerCase()
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
    ElMessage.error('仅支持 PDF / Docx 文件')
    return
  }
  uploading.value = true
  try {
    const res = await uploadMaterial(props.customer.id, raw)
    ElMessage.success('上传并解析成功')
    if (res?.warning) ElMessage.warning(res.warning)
    await loadMaterials()
  } finally {
    uploading.value = false
  }
}

async function removeMaterial(row) {
  await deleteMaterial(props.customer.id, row.id)
  ElMessage.success('已删除')
  await loadMaterials()
}

async function preview(row) {
  try {
    const blob = await fetchMaterialBlob(props.customer.id, row.id)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')  // PDF 内联预览；docx 由浏览器下载
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    ElMessage.error('预览失败')
  }
}

async function download(row) {
  try {
    const blob = await fetchMaterialBlob(props.customer.id, row.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = row.filename
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    ElMessage.error('下载失败')
  }
}

async function onGenerate() {
  generating.value = true
  step.value = 0
  // 分析状态栏：解析(已完成)→检索→综合，随请求推进（指示性）
  stepTimer = setInterval(() => { if (step.value < 2) step.value++ }, 4000)
  try {
    report.value = await generateResearch(props.customer.id)
    step.value = 3
    ElMessage.success('尽调报告已生成')
  } finally {
    clearInterval(stepTimer)
    generating.value = false
  }
}

function copyReport() {
  const md = report.value?.report_md || ''
  navigator.clipboard?.writeText(md).then(
    () => ElMessage.success('报告全文已复制'),
    () => ElMessage.error('复制失败')
  )
}

function formatTime(t) {
  return t ? String(t).slice(0, 19).replace('T', ' ') : ''
}
</script>

<style scoped lang="scss">
.block { margin-bottom: 18px; }
.block-title {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600; margin-bottom: 10px;
}
.steps { margin: 10px 0 6px; }
.rec-bar { display: flex; align-items: center; gap: 8px; margin: 6px 0 14px; flex-wrap: wrap; }
.rec-bar .engine { margin-left: 2px; }
.rep-sec { margin-bottom: 12px; }
.rep-sec h4 { margin: 0 0 4px; color: var(--el-color-primary); font-size: 14px; }
.rep-sec p { margin: 0; line-height: 1.7; color: var(--el-text-color-regular); }
.rep-sec ul, .rep-sec ol { margin: 4px 0; padding-left: 20px; line-height: 1.7; }
.sources a { color: var(--el-color-primary); word-break: break-all; }
.src-meta { color: var(--el-text-color-secondary); font-size: 12px; margin-left: 6px; }
.doc-src { font-size: 13px; color: var(--el-text-color-regular); padding: 2px 0; }
.report-actions { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.ki { font-size: 12px; color: var(--el-text-color-regular); }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 12px; }
</style>

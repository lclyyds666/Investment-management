<template>
  <el-card shadow="never" class="ai-card">
    <template #header>
      <div class="ai-header">
        <span class="ai-title"><span class="ai-emoji">🧠</span> AI 智能大脑分析</span>
        <el-button type="primary" :icon="MagicStick" :loading="loading" @click="diagnose">
          {{ result ? '重新诊断' : '一键诊断' }}
        </el-button>
      </div>
    </template>

    <div v-if="loading" class="ai-loading">
      <el-icon class="rotating"><Loading /></el-icon>
      <span>AI Agent 正在全面审计业务与财务数据…</span>
    </div>

    <el-empty v-else-if="!result" :image-size="70" description="点击「一键诊断」，AI 将审计经营/财务/审批数据并给出风险预警与资金管理建议" />

    <div v-else class="ai-body">
      <el-alert type="primary" :closable="false" class="ai-summary">
        <template #title><span class="summary-text">{{ result.summary }}</span></template>
      </el-alert>

      <el-row :gutter="12" class="ai-metrics">
        <el-col :span="6"><div class="m-box"><div class="m-label">利润率</div><div class="m-val">{{ result.metrics.margin }}%</div></div></el-col>
        <el-col :span="6"><div class="m-box"><div class="m-label">可用闲置资金</div><div class="m-val blue">¥{{ fmt(result.metrics.idle_funds) }}</div></div></el-col>
        <el-col :span="6"><div class="m-box"><div class="m-label">待开票金额</div><div class="m-val warn">¥{{ fmt(result.metrics.pending_invoice) }}</div></div></el-col>
        <el-col :span="6"><div class="m-box"><div class="m-label">审批中合同</div><div class="m-val">{{ result.metrics.pending_contracts }}</div></div></el-col>
      </el-row>

      <div class="ai-engine">
        <el-tag :type="result.engine === 'deepseek' ? 'success' : 'info'" size="small" effect="dark">
          {{ result.engine === 'deepseek' ? 'DeepSeek 大模型' : '内置规则引擎' }}
        </el-tag>
      </div>

      <div class="ai-cols">
        <div class="ai-col">
          <div class="col-title"><el-icon><WarningFilled /></el-icon> 业务风险预警</div>
          <div v-for="(r, i) in result.risks" :key="i" class="risk-item" :class="'lv-' + r.level">
            <div class="risk-head">
              <el-tag :type="lvType(r.level)" size="small" effect="dark">{{ r.level }}风险</el-tag>
              <span class="risk-title">{{ r.title }}</span>
            </div>
            <div class="risk-detail">{{ r.detail }}</div>
          </div>
        </div>
        <div class="ai-col">
          <div class="col-title"><el-icon><Coin /></el-icon> 闲置资金管理与投资建议</div>
          <div v-for="(s, i) in result.suggestions" :key="i" class="sug-item">
            <div class="sug-title">{{ i + 1 }}. {{ s.title }}</div>
            <div class="sug-detail">{{ s.detail }}</div>
          </div>
        </div>
      </div>
      <div class="ai-foot">
        ※ 以上由 AI 智能体基于平台真实经营/财务/审批数据实时分析生成，仅供经营决策参考。
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Loading, WarningFilled, Coin } from '@element-plus/icons-vue'
import { aiDiagnose } from '@/api/operation'

const loading = ref(false)
const result = ref(null)

const fmt = (v) => Number(v || 0).toLocaleString()
const lvType = (lv) => ({ 高: 'danger', 中: 'warning', 低: 'success' }[lv] || 'info')

async function diagnose() {
  loading.value = true
  result.value = null
  try {
    // 至少展示 800ms「分析中」动画，避免快速返回时闪烁
    const [res] = await Promise.all([aiDiagnose(), new Promise((r) => setTimeout(r, 800))])
    result.value = res
    ElMessage.success(res?.engine === 'deepseek' ? 'AI 诊断完成（DeepSeek）' : 'AI 诊断完成')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.ai-card {
  margin-top: 16px;
}
.ai-header { display: flex; align-items: center; justify-content: space-between; }
.ai-title { font-weight: 600; font-size: 15px; }
.ai-emoji { font-size: 18px; }
.ai-loading {
  display: flex; align-items: center; gap: 10px; justify-content: center;
  padding: 28px; color: var(--el-color-primary); font-size: 14px;
}
.rotating { animation: spin 1s linear infinite; font-size: 20px; }
@keyframes spin { to { transform: rotate(360deg); } }
.ai-summary { margin-bottom: 14px; }
.summary-text { font-size: 13px; line-height: 1.7; }
.ai-metrics { margin-bottom: 8px; }
.ai-engine { margin: 6px 0 2px; }
.m-box { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-light); border-radius: 8px; padding: 10px 12px; text-align: center; }
.m-label { font-size: 12px; color: var(--el-text-color-secondary); }
.m-val { margin-top: 4px; font-size: 20px; font-weight: 700; color: var(--el-text-color-primary); }
.m-val.blue { color: #409eff; }
.m-val.warn { color: #e6a23c; }
.ai-cols { display: flex; gap: 16px; margin-top: 14px; }
.ai-col { flex: 1; min-width: 0; }
.col-title { display: flex; align-items: center; gap: 6px; font-weight: 600; margin-bottom: 10px; color: var(--el-text-color-primary); }
.col-title .el-icon { color: var(--el-color-primary); }
.risk-item {
  border: 1px solid var(--el-border-color-light); border-left: 3px solid var(--el-border-color);
  border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; background: var(--el-fill-color-light);
  &.lv-高 { border-left-color: #f56c6c; }
  &.lv-中 { border-left-color: #e6a23c; }
  &.lv-低 { border-left-color: #67c23a; }
}
.risk-head { display: flex; align-items: center; gap: 8px; }
.risk-title { font-weight: 600; color: var(--el-text-color-primary); }
.risk-detail { margin-top: 6px; font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; }
.sug-item { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; background: var(--el-fill-color-light); }
.sug-title { font-weight: 600; color: var(--el-color-primary); }
.sug-detail { margin-top: 6px; font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; }
.ai-foot { margin-top: 8px; font-size: 12px; color: var(--el-text-color-placeholder); }
</style>

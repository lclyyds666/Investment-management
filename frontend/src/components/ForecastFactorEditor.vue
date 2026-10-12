<template>
  <section class="forecast-factor-editor">
    <div class="factor-toolbar">
      <button type="button" data-testid="add-factor" @click="addFactor">添加因素</button>
      <button type="button" data-testid="download-template" @click="downloadTemplate">下载模板</button>
      <label class="import-button">
        导入 Excel
        <input
          data-testid="factor-file"
          type="file"
          accept=".xlsx"
          @change="importFactors"
        >
      </label>
    </div>

    <div class="factor-table-wrap">
      <table class="factor-table">
        <thead>
          <tr>
            <th>开始日期</th><th>结束日期</th><th>景区</th><th>业务类型</th><th>平台</th>
            <th>因素类型</th><th>因素名称</th><th>影响比例</th><th>备注</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(factor, index) in factors" :key="index">
            <td><input type="date" :value="factor.start_date" @input="updateFactor(index, 'start_date', $event.target.value)"></td>
            <td><input type="date" :value="factor.end_date" @input="updateFactor(index, 'end_date', $event.target.value)"></td>
            <td><input :value="factor.scenic_id" placeholder="全部" @input="updateFactor(index, 'scenic_id', $event.target.value)"></td>
            <td>
              <select :value="factor.business_type" @change="updateFactor(index, 'business_type', $event.target.value)">
                <option value="">全部</option><option value="ticket">ticket</option><option value="hotel">hotel</option>
              </select>
            </td>
            <td><input :value="factor.platform" placeholder="全部" @input="updateFactor(index, 'platform', $event.target.value)"></td>
            <td>
              <select :value="factor.factor_type" @change="updateFactor(index, 'factor_type', $event.target.value)">
                <option v-for="type in factorTypes" :key="type" :value="type">{{ type }}</option>
              </select>
            </td>
            <td><input :data-testid="`factor-name-${index}`" :value="factor.name" maxlength="100" @input="updateFactor(index, 'name', $event.target.value)"></td>
            <td><input type="number" min="-0.8" max="2" step="0.01" :value="factor.impact_rate" @input="updateFactor(index, 'impact_rate', Number($event.target.value))"></td>
            <td><input :value="factor.remark" maxlength="500" @input="updateFactor(index, 'remark', $event.target.value)"></td>
            <td><button type="button" :data-testid="`remove-factor-${index}`" @click="removeFactor(index)">删除</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <ul v-if="importErrors.length" class="import-errors" aria-label="导入错误">
      <li v-for="error in importErrors" :key="`${error.row_no}-${error.message}`">
        第 {{ error.row_no }} 行：{{ error.message }}
      </li>
    </ul>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { downloadForecastFactorTemplate, parseForecastFactors } from '@/api/operation'

const factors = defineModel({ type: Array, default: () => [] })
const importErrors = ref([])
const factorTypes = ['天气', '节假日', '活动', '资讯']

function addFactor() {
  factors.value = [...factors.value, {
    start_date: '', end_date: '', scenic_id: '', business_type: '', platform: '',
    factor_type: '天气', name: '', impact_rate: 0, remark: ''
  }]
}

function updateFactor(index, field, value) {
  factors.value = factors.value.map((factor, itemIndex) => (
    itemIndex === index ? { ...factor, [field]: value } : factor
  ))
}

function removeFactor(index) {
  factors.value = factors.value.filter((_, itemIndex) => itemIndex !== index)
}

async function importFactors(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const result = await parseForecastFactors(file)
  factors.value = [...factors.value, ...(result.items || [])]
  importErrors.value = result.errors || []
  event.target.value = ''
}

async function downloadTemplate() {
  const blob = await downloadForecastFactorTemplate()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '经营预测影响因素模板.xlsx'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.forecast-factor-editor { display: grid; gap: 12px; }
.factor-toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
.factor-toolbar button, .import-button { border: 1px solid #b9c4d0; border-radius: 6px; background: #fff; padding: 7px 12px; cursor: pointer; }
.import-button input { display: none; }
.factor-table-wrap { overflow-x: auto; }
.factor-table { width: 100%; min-width: 1180px; border-collapse: collapse; }
.factor-table th, .factor-table td { border-bottom: 1px solid #e5e9ef; padding: 7px 5px; text-align: left; }
.factor-table input, .factor-table select { width: 100%; box-sizing: border-box; border: 1px solid #cfd6df; border-radius: 4px; padding: 6px; }
.import-errors { margin: 0; padding: 10px 14px 10px 32px; border-radius: 6px; background: #fff3f0; color: #b42318; }
</style>

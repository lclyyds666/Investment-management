<template>
  <el-dialog
    v-model="visible"
    title="景区配置"
    width="min(1180px, 96vw)"
    top="5vh"
    append-to-body
    destroy-on-close
    @open="loadConfigs"
  >
    <el-tabs v-model="activeTab" class="config-tabs">
      <el-tab-pane label="门票配置" name="ticket">
        <el-table
          v-loading="loading"
          :data="rows"
          border
          stripe
          size="small"
          max-height="68vh"
          class="config-table"
        >
      <el-table-column label="景区" prop="scenic_name" min-width="160" fixed="left" />

      <el-table-column label="默认门票名称" min-width="220">
        <template #default="{ row }">
          <el-input
            v-if="canEdit"
            v-model="row.default_ticket_product"
            maxlength="200"
            size="small"
          />
          <span v-else>{{ row.default_ticket_product }}</span>
        </template>
      </el-table-column>

      <el-table-column label="核销率" min-width="130" align="right">
        <template #default="{ row }">
          <div v-if="canEdit" class="percent-field">
            <el-input-number
              v-model="row.rateHexiaoPct"
              :min="0"
              :max="100"
              :precision="2"
              :step="1"
              :controls="false"
              size="small"
            />
            <span>%</span>
          </div>
          <span v-else>{{ formatPercent(row.rateHexiaoPct) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="结算费率" min-width="130" align="right">
        <template #default="{ row }">
          <div v-if="canEdit" class="percent-field">
            <el-input-number
              v-model="row.rateSettlePct"
              :min="0"
              :max="100"
              :precision="2"
              :step="1"
              :controls="false"
              size="small"
            />
            <span>%</span>
          </div>
          <span v-else>{{ formatPercent(row.rateSettlePct) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="服务商佣金率" min-width="150" align="right">
        <template #default="{ row }">
          <div v-if="canEdit" class="percent-field">
            <el-input-number
              v-model="row.commissionRatePct"
              :min="0"
              :max="100"
              :precision="2"
              :step="0.5"
              :controls="false"
              size="small"
            />
            <span>%</span>
          </div>
          <span v-else>{{ formatPercent(row.commissionRatePct) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="默认服务商佣金" min-width="170" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="canEdit"
            v-model="row.ticket_default_commission"
            :min="0"
            :precision="2"
            :step="100"
            :controls="false"
            size="small"
          />
          <span v-else>{{ formatCommission(row.ticket_default_commission) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="canEdit" label="操作" width="92" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            text
            size="small"
            :loading="savingId === row.scenic_id"
            @click="saveRow(row)"
          >保存</el-button>
        </template>
      </el-table-column>

          <template #empty>暂无景区配置</template>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="酒店配置" name="hotel">
        <el-table
          v-loading="loading"
          :data="rows"
          border
          stripe
          size="small"
          max-height="68vh"
          class="config-table"
        >
          <el-table-column label="景区" prop="scenic_name" min-width="160" fixed="left" />

          <el-table-column label="默认酒店名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="canEdit" v-model="row.default_hotel_name" maxlength="200" size="small" />
              <span v-else>{{ row.default_hotel_name }}</span>
            </template>
          </el-table-column>

          <el-table-column label="核销率" min-width="120" align="right">
            <template #default="{ row }">
              <div v-if="canEdit" class="percent-field">
                <el-input-number v-model="row.hotelRateHexiaoPct" :min="0" :max="100" :precision="2" :step="1" :controls="false" size="small" />
                <span>%</span>
              </div>
              <span v-else>{{ formatPercent(row.hotelRateHexiaoPct) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="结算费率" min-width="120" align="right">
            <template #default="{ row }">
              <div v-if="canEdit" class="percent-field">
                <el-input-number v-model="row.hotelRateSettlePct" :min="0" :max="100" :precision="2" :step="1" :controls="false" size="small" />
                <span>%</span>
              </div>
              <span v-else>{{ formatPercent(row.hotelRateSettlePct) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="服务商佣金率" min-width="145" align="right">
            <template #default="{ row }">
              <div v-if="canEdit" class="percent-field">
                <el-input-number v-model="row.hotelCommissionRatePct" :min="0" :max="100" :precision="2" :step="0.5" :controls="false" size="small" />
                <span>%</span>
              </div>
              <span v-else>{{ formatPercent(row.hotelCommissionRatePct) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="每间夜服务费（元/间夜）" min-width="180" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit" v-model="row.hotel_fee_per_night" :min="0" :precision="2" :step="1" :controls="false" size="small" />
              <span v-else>{{ formatYuan(row.hotel_fee_per_night) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="服务费算法" min-width="250">
            <template #default="{ row }">
              <el-radio-group v-if="canEdit" v-model="row.hotel_fee_algo" size="small">
                <el-radio :label="1">间夜服务费</el-radio>
                <el-radio :label="2">结算费率</el-radio>
              </el-radio-group>
              <span v-else>{{ Number(row.hotel_fee_algo) === 2 ? '结算费率' : '间夜服务费' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="启用平台" min-width="190">
            <template #default="{ row }">
              <el-checkbox-group v-if="canEdit" v-model="row.hotel_platforms" class="platform-options">
                <el-checkbox v-for="platform in HOTEL_PLATFORMS" :key="platform" :label="platform">{{ platform }}</el-checkbox>
              </el-checkbox-group>
              <span v-else>{{ row.hotel_platforms.join('、') }}</span>
            </template>
          </el-table-column>

          <el-table-column v-if="canEdit" label="操作" width="92" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" text size="small" :loading="hotelSavingId === row.scenic_id" @click="saveHotelRow(row)">保存</el-button>
            </template>
          </el-table-column>

          <template #empty>暂无景区配置</template>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getScenicConfigs, updateHotelScenicConfig, updateScenicConfig } from '@/api/scenic'
import { usePortalStore } from '@/store/portal'
import { canUsePermission } from '@/utils/businessAuthorization'

const portalStore = usePortalStore()
const visible = ref(false)
const loading = ref(false)
const savingId = ref('')
const hotelSavingId = ref('')
const rows = ref([])
const activeTab = ref('ticket')
const HOTEL_PLATFORMS = ['抖音', '美团', '携程']

const canEdit = computed(() => canUsePermission(portalStore, 'supply.scenic.update'))

function rateToPercent(value) {
  return Math.round((Number(value) || 0) * 10000) / 100
}

function mapConfig(config) {
  return {
    ...config,
    rateHexiaoPct: rateToPercent(config.ticket_rate_hexiao),
    rateSettlePct: rateToPercent(config.ticket_rate_settle),
    commissionRatePct: rateToPercent(config.ticket_commission_rate),
    hotelRateHexiaoPct: rateToPercent(config.hotel_rate_hexiao),
    hotelRateSettlePct: rateToPercent(config.hotel_rate_settle),
    hotelCommissionRatePct: rateToPercent(config.hotel_commission_rate),
    hotel_fee_per_night: Number(config.hotel_fee_per_night || 0),
    hotel_fee_algo: Number(config.hotel_fee_algo || 1),
    hotel_platforms: HOTEL_PLATFORMS.filter((platform) => (config.hotel_platforms || []).includes(platform)),
    ticket_default_commission: config.ticket_default_commission == null
      ? null
      : Number(config.ticket_default_commission)
  }
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}%`
}

function formatCommission(value) {
  if (value == null || value === '') return '自动'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatYuan(value) {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

async function loadConfigs() {
  loading.value = true
  try {
    rows.value = (await getScenicConfigs()).map(mapConfig)
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function saveRow(row) {
  const product = String(row.default_ticket_product || '').trim()
  if (!product) {
    ElMessage.warning('默认门票名称不能为空')
    return
  }
  const rates = [row.rateHexiaoPct, row.rateSettlePct, row.commissionRatePct]
  if (rates.some((value) => value == null || value === '' || !Number.isFinite(Number(value)))) {
    ElMessage.warning('核销率、结算费率和服务商佣金率不能为空')
    return
  }

  savingId.value = row.scenic_id
  try {
    const saved = await updateScenicConfig(row.scenic_id, {
      default_ticket_product: product,
      ticket_rate_hexiao: Number(row.rateHexiaoPct || 0) / 100,
      ticket_rate_settle: Number(row.rateSettlePct || 0) / 100,
      ticket_commission_rate: Number(row.commissionRatePct || 0) / 100,
      ticket_default_commission: row.ticket_default_commission == null
        ? null
        : Number(row.ticket_default_commission)
    })
    const index = rows.value.findIndex((item) => item.scenic_id === row.scenic_id)
    if (index >= 0) rows.value[index] = mapConfig(saved)
    ElMessage.success(`${saved.scenic_name}配置已保存`)
  } catch {
    // 请求拦截器统一展示错误信息。
  } finally {
    savingId.value = ''
  }
}

async function saveHotelRow(row) {
  const hotelName = String(row.default_hotel_name || '').trim()
  if (!hotelName) {
    ElMessage.warning('默认酒店名称不能为空')
    return
  }
  const rates = [row.hotelRateHexiaoPct, row.hotelRateSettlePct, row.hotelCommissionRatePct]
  if (rates.some((value) => value == null || value === '' || !Number.isFinite(Number(value)))) {
    ElMessage.warning('核销率、结算费率和服务商佣金率不能为空')
    return
  }

  hotelSavingId.value = row.scenic_id
  try {
    const saved = await updateHotelScenicConfig(row.scenic_id, {
      default_hotel_name: hotelName,
      hotel_rate_hexiao: Number(row.hotelRateHexiaoPct) / 100,
      hotel_rate_settle: Number(row.hotelRateSettlePct) / 100,
      hotel_commission_rate: Number(row.hotelCommissionRatePct) / 100,
      hotel_fee_per_night: Number(row.hotel_fee_per_night),
      hotel_fee_algo: Number(row.hotel_fee_algo),
      hotel_platforms: row.hotel_platforms
    })
    const index = rows.value.findIndex((item) => item.scenic_id === row.scenic_id)
    if (index >= 0) rows.value[index] = mapConfig(saved)
    ElMessage.success(`${saved.scenic_name}酒店配置已保存`)
  } catch {
    // 请求拦截器统一展示错误信息。
  } finally {
    hotelSavingId.value = ''
  }
}

function open() {
  visible.value = true
}

defineExpose({ open })
</script>

<style scoped lang="scss">
.config-table {
  width: 100%;
}

.config-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.platform-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.percent-field {
  display: grid;
  grid-template-columns: minmax(72px, 1fr) 18px;
  align-items: center;
  gap: 4px;

  :deep(.el-input-number) {
    width: 100%;
  }
}

:deep(.el-input-number) {
  width: 100%;
}

@media (max-width: 720px) {
  :deep(.el-dialog__body) {
    padding-inline: 12px;
  }
}
</style>

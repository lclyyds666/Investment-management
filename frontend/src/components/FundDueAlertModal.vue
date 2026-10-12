<template>
  <el-dialog
    v-model="alertStore.visible"
    width="760px"
    class="fund-alert-dialog"
    :close-on-click-modal="false"
    @opened="acknowledge"
  >
    <template #header>
      <div class="alert-heading">
        <span class="alert-kicker">FUND MATURITY</span>
        <h2>资金到期提醒</h2>
        <p>以下授信或借款需要关注，提醒关闭不会修改资金状态。</p>
      </div>
    </template>

    <section v-if="overdueItems.length" class="alert-group alert-group--overdue">
      <button class="group-heading" type="button" @click="goToFunds('overdue')">
        <span>已逾期</span><strong>{{ overdueItems.length }}</strong>
      </button>
      <article v-for="item in overdueItems" :key="`${item.id}-${item.stage}`" class="alert-row">
        <div class="risk-mark">逾</div>
        <div class="alert-copy">
          <strong>{{ categoryLabel(item.category) }} · {{ item.counterparty || '未填写对方单位' }}</strong>
          <span>{{ item.summary || '未填写摘要' }}</span>
        </div>
        <div class="alert-meta">
          <strong>{{ formatAmount(item.amount) }}</strong>
          <span>{{ item.maturity_date }} · 逾期 {{ Math.abs(item.days_remaining) }} 天</span>
        </div>
      </article>
    </section>

    <section v-if="dueSoonItems.length" class="alert-group alert-group--due">
      <button class="group-heading" type="button" @click="goToFunds('due_soon')">
        <span>即将到期</span><strong>{{ dueSoonItems.length }}</strong>
      </button>
      <article v-for="item in dueSoonItems" :key="`${item.id}-${item.stage}`" class="alert-row">
        <div class="risk-mark">期</div>
        <div class="alert-copy">
          <strong>{{ categoryLabel(item.category) }} · {{ item.counterparty || '未填写对方单位' }}</strong>
          <span>{{ item.summary || '未填写摘要' }}</span>
        </div>
        <div class="alert-meta">
          <strong>{{ formatAmount(item.amount) }}</strong>
          <span>{{ item.maturity_date }} · 剩余 {{ item.days_remaining }} 天</span>
        </div>
      </article>
    </section>

    <template #footer>
      <el-button @click="alertStore.visible = false">稍后处理</el-button>
      <el-button v-if="overdueItems.length" type="danger" plain @click="goToFunds('overdue')">查看逾期事项</el-button>
      <el-button v-else type="primary" @click="goToFunds('due_soon')">进入资金管理</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useFundAlertStore } from '@/store/fundAlerts'
import { formatWanFromYuan } from '@/utils/money'

defineOptions({ name: 'FundDueAlertModal' })

const router = useRouter()
const alertStore = useFundAlertStore()
const overdueItems = computed(() => alertStore.items.filter(item => item.stage === 'overdue'))
const dueSoonItems = computed(() => alertStore.items.filter(item => item.stage === 'due_soon'))

const categoryLabel = category => category === 'bank_credit' ? '银行授信' : '公司借款'
const formatAmount = value => `${formatWanFromYuan(value)} 万元`

async function acknowledge() {
  try {
    await alertStore.acknowledgeShown()
  } catch (_error) {
    // A failed receipt remains eligible for a later login retry.
  }
}

async function goToFunds(stage) {
  alertStore.visible = false
  await router.push({
    path: '/supplymanagement/finance/fund',
    query: { maturity_status: stage }
  })
}
</script>

<style scoped>
.alert-heading { display: grid; gap: 4px; }
.alert-kicker { color: #8b5e16; font-size: 11px; font-weight: 700; letter-spacing: .18em; }
.alert-heading h2 { margin: 0; color: #20242b; font-size: 24px; }
.alert-heading p { margin: 0; color: #737983; font-size: 13px; }
.alert-group { margin-top: 18px; border: 1px solid #e7e9ed; border-radius: 10px; overflow: hidden; }
.group-heading { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 11px 14px; border: 0; cursor: pointer; font: inherit; font-weight: 700; }
.group-heading strong { display: grid; place-items: center; min-width: 24px; height: 24px; border-radius: 12px; background: rgba(255,255,255,.72); }
.alert-group--overdue .group-heading { color: #9f2d27; background: #fff0ee; }
.alert-group--due .group-heading { color: #8b5e16; background: #fff7e6; }
.alert-row { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 14px; border-top: 1px solid #edf0f3; background: #fff; }
.risk-mark { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; color: #fff; font-weight: 800; background: #c24138; }
.alert-group--due .risk-mark { background: #c28720; }
.alert-copy, .alert-meta { display: grid; gap: 4px; }
.alert-copy span, .alert-meta span { color: #7c828c; font-size: 12px; }
.alert-meta { text-align: right; }
.alert-meta strong { color: #252a31; font-variant-numeric: tabular-nums; }
@media (max-width: 640px) { .alert-row { grid-template-columns: 34px 1fr; } .alert-meta { grid-column: 2; text-align: left; } }
</style>

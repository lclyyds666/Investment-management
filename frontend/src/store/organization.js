import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/organization'
import { buildOrganizationTree } from '@/utils/organizationTree'

export { buildOrganizationTree }

export const POSITION_NAMES_BY_CODE = Object.freeze({
  'investment.executive.chairman': '董事长',
  'investment.executive.general_manager': '总经理',
  'investment.executive.deputy_general_manager': '副总经理',
  'investment.department.director': '部门主任',
  'investment.department.deputy_director': '部门副主任',
  'investment.department.senior_manager': '高级经理',
  'investment.department.middle_manager': '中级经理',
  'investment.department.junior_manager': '初级经理',
  'supply.business_handler': '供管公司初级经理',
  'supply.business_reviewer': '供管公司中级经理',
  'supply.senior_manager': '供管公司高级经理',
  'supply.company_leader': '供管公司负责人',
  'supply.finance_handler': '投资公司资产财务部初级经理',
  'investment.asset_finance.middle_manager': '投资公司资产财务部中级经理',
  'investment.asset_finance.senior_manager': '投资公司资产财务部高级经理',
  'investment.asset_finance.deputy_director': '投资公司资产财务部副主任',
  'governance.supply_leader': '供管公司分管领导',
  'fund.chairman': '基金公司董事长',
  'fund.general_manager': '基金公司总经理',
  'governance.fund_leader': '基金公司分管领导',
  'investment.duty.supply_risk_review': '投资公司法务风控部主任',
  'investment.legal_risk.deputy_director': '投资公司法务风控部副主任',
  'investment.duty.supply_finance_review': '投资公司资产财务部主任',
  'zhanwei.general_manager': '总经理',
  'zhanwei.deputy_general_manager': '副总经理',
  'zhanwei.senior_manager': '高级经理',
  'zhanwei.middle_manager': '中级经理',
  'zhanwei.junior_manager': '初级经理',
  'xinhuaproperty.chairman': '董事长',
  'xinhuaproperty.general_manager': '总经理',
  'xinhuaproperty.deputy_general_manager': '副总经理',
  'xinhuaproperty.department.director': '部门主任',
  'xinhuaproperty.department.employee': '部门员工',
  'governance.zhanwei_leader': '展威科技分管领导',
  'external.legal_counsel': '外聘法律顾问'
})

export const canonicalPositionName = (position) => POSITION_NAMES_BY_CODE[position?.code] || position?.name || ''
export const canonicalPosition = (position) => ({ ...position, name: canonicalPositionName(position) })

export const useOrganizationStore = defineStore('organization', () => {
  const tree = ref([])
  const positions = ref([])
  const permissions = ref([])
  const loadTree = async (force = false) => (force || !tree.value.length) && (tree.value = buildOrganizationTree(await api.getOrganizationTree()))
  const loadPositions = async (force = false) => (force || !positions.value.length) && (positions.value = (await api.listPositions()).map(canonicalPosition))
  const loadPermissions = async (force = false) => (force || !permissions.value.length) && (permissions.value = await api.listPermissions())
  async function saveOrganization(payload, reason, id) {
    const item = id ? await api.updateOrganization(id, payload, reason) : await api.createOrganization(payload, reason)
    tree.value = []
    return item
  }
  return { tree, positions, permissions, loadTree, loadPositions, loadPermissions, saveOrganization }
})

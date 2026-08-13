import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/organization'
import { buildOrganizationTree } from '@/utils/organizationTree'

export { buildOrganizationTree }

export const useOrganizationStore = defineStore('organization', () => {
  const tree = ref([])
  const positions = ref([])
  const permissions = ref([])
  const loadTree = async (force = false) => (force || !tree.value.length) && (tree.value = buildOrganizationTree(await api.getOrganizationTree()))
  const loadPositions = async (force = false) => (force || !positions.value.length) && (positions.value = await api.listPositions())
  const loadPermissions = async (force = false) => (force || !permissions.value.length) && (permissions.value = await api.listPermissions())
  async function saveOrganization(payload, reason, id) {
    const item = id ? await api.updateOrganization(id, payload, reason) : await api.createOrganization(payload, reason)
    tree.value = []
    return item
  }
  return { tree, positions, permissions, loadTree, loadPositions, loadPermissions, saveOrganization }
})

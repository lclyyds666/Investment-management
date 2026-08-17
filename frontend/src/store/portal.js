import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getMyPortalPermissions, getPortalApplications } from '@/api/portal'

export const usePortalStore = defineStore('portal', () => {
  const applications = ref([])
  const permissions = ref({
    is_superuser: false,
    assignments: [],
    permissions: [],
    resources: [],
    company_roles: {}
  })
  const isLoaded = ref(false)
  const isSuperuser = computed(() => permissions.value.is_superuser)
  const assignments = computed(() => permissions.value.assignments || [])

  let inFlightPromise = null
  let contextVersion = 0

  function hasCompany(companyCode) {
    return isSuperuser.value
      || applications.value.some(item => item.code === companyCode && item.accessible)
  }

  function hasResource(resourceCode) {
    return isSuperuser.value || (permissions.value.resources || []).includes(resourceCode)
  }

  function hasPosition(positionCode) {
    return assignments.value.some(item => item.position_code === positionCode)
  }

  function hasPermission(permissionCode) {
    return isSuperuser.value
      || (permissions.value.permissions || []).some(item => item.code === permissionCode)
  }

  function companyRole(companyCode) {
    return permissions.value.company_roles?.[companyCode] || ''
  }

  function clearPortalContext() {
    contextVersion += 1
    inFlightPromise = null
    applications.value = []
    permissions.value = {
      is_superuser: false,
      assignments: [],
      permissions: [],
      resources: [],
      company_roles: {}
    }
    isLoaded.value = false
  }

  function loadPortalContext(force = false) {
    if (inFlightPromise) return inFlightPromise
    if (isLoaded.value && !force) return Promise.resolve()

    const loadVersion = contextVersion
    const loadPromise = Promise.all([
      getPortalApplications(),
      getMyPortalPermissions()
    ]).then(([loadedApplications, loadedPermissions]) => {
      if (loadVersion !== contextVersion) return
      applications.value = loadedApplications || []
      permissions.value = loadedPermissions || {
        is_superuser: false,
        assignments: [],
        permissions: [],
        resources: [],
        company_roles: {}
      }
      isLoaded.value = true
    }).finally(() => {
      if (inFlightPromise === loadPromise) inFlightPromise = null
    })

    inFlightPromise = loadPromise
    return loadPromise
  }

  return {
    applications,
    permissions,
    isLoaded,
    isSuperuser,
    assignments,
    hasCompany,
    hasResource,
    hasPosition,
    hasPermission,
    companyRole,
    loadPortalContext,
    clearPortalContext
  }
})

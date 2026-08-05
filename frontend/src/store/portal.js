import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getMyPortalPermissions, getPortalApplications } from '@/api/portal'

export const usePortalStore = defineStore('portal', () => {
  const applications = ref([])
  const permissions = ref({
    is_superuser: false,
    company_roles: {},
    resources: []
  })
  const isLoaded = ref(false)
  const isSuperuser = computed(() => permissions.value.is_superuser)

  let inFlightPromise = null
  let contextVersion = 0

  function companyRole(companyCode) {
    const companyRoles = permissions.value.company_roles || {}
    if (Array.isArray(companyRoles)) {
      return companyRoles.find((item) => item.company_code === companyCode)?.role || ''
    }
    return companyRoles[companyCode] || ''
  }

  function hasCompany(companyCode) {
    return isSuperuser.value || Boolean(companyRole(companyCode))
  }

  function hasResource(resourceCode) {
    return isSuperuser.value || (permissions.value.resources || []).includes(resourceCode)
  }

  function clearPortalContext() {
    contextVersion += 1
    inFlightPromise = null
    applications.value = []
    permissions.value = {
      is_superuser: false,
      company_roles: {},
      resources: []
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
        company_roles: {},
        resources: []
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
    companyRole,
    hasCompany,
    hasResource,
    loadPortalContext,
    clearPortalContext
  }
})

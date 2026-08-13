const redirectTo = (name) => (to) => ({
  name,
  params: to.params,
  query: to.query,
  hash: to.hash,
  replace: true
})

export const legacySupplyRedirects = [
  { path: '/dashboard', redirect: redirectTo('Dashboard') },
  { path: '/operation', redirect: redirectTo('Operation') },
  { path: '/cultural-tourism', redirect: redirectTo('CulturalTourism') },
  { path: '/cultural-tourism/:scenicId', redirect: redirectTo('CulturalTourismDetail') },
  { path: '/channel', redirect: redirectTo('CulturalTourism') },
  { path: '/channel/tourism', redirect: redirectTo('CulturalTourism') },
  { path: '/channel/other', redirect: redirectTo('CulturalTourism') },
  { path: '/finance/fund', redirect: redirectTo('FinanceFund') },
  { path: '/finance/invoice', redirect: redirectTo('Invoice') },
  { path: '/invoice', redirect: redirectTo('Invoice') },
  { path: '/contract', redirect: redirectTo('Contract') },
  { path: '/approval', redirect: redirectTo('Approval') },
  { path: '/customer', redirect: redirectTo('Customer') },
  { path: '/org', redirect: redirectTo('SystemUsers') },
  { path: '/audit', redirect: redirectTo('SystemAudit') },
  { path: '/profile', redirect: redirectTo('Profile') },
  { path: '/screen', redirect: redirectTo('Screen') }
]

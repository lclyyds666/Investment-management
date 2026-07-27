const PLATFORM_BRANDS = {
  douyin: { name: '抖音', logo: '/scenic/logos/douyin.png' },
  ctrip: { name: '携程', logo: '/scenic/logos/ctrip.png' },
  meituan: { name: '美团', logo: '/scenic/logos/meituan.png' },
  tongcheng: { name: '同程', logo: '/scenic/logos/tongcheng.png' }
}

const PLATFORM_ENTRIES = {
  'quancheng-ouleb': {
    hotel: [
      ['douyin', 'https://life.douyin.com'],
      ['ctrip', 'https://ebooking.ctrip.com'],
      ['meituan', 'https://me.meituan.com']
    ],
    ticket: []
  },
  'quanzhou-ouleb': {
    hotel: [
      ['douyin', 'https://life.douyin.com'],
      ['ctrip', 'https://ebooking.ctrip.com'],
      ['meituan', 'https://me.meituan.com']
    ],
    ticket: [['douyin', 'https://life.douyin.com']]
  },
  'fuzhou-ouleb': {
    hotel: [
      ['douyin', 'https://life.douyin.com'],
      ['meituan', 'https://me.meituan.com/login/index.html']
    ],
    ticket: [
      ['douyin', 'https://life.douyin.com'],
      ['meituan', 'https://mpc.meituan.com/#/ticket/finance/pre']
    ]
  },
  'zunyi-zoo': {
    hotel: [],
    ticket: [
      ['douyin', 'https://life.douyin.com'],
      ['ctrip', 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard'],
      ['meituan', 'https://mpc.meituan.com/#/ticket/finance/pre'],
      ['tongcheng', 'http://ebk.17u.cn/jingqu/']
    ]
  },
  'nanyang-wildlife': {
    hotel: [],
    ticket: [
      ['douyin', 'https://life.douyin.com'],
      ['ctrip', 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard'],
      ['meituan', 'https://mpc.meituan.com/#/ticket/product/new'],
      ['tongcheng', 'http://ebk.17u.cn/jingqu/']
    ]
  },
  guanquelou: {
    hotel: [],
    ticket: [
      ['douyin', 'https://life.douyin.com'],
      ['ctrip', 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard'],
      ['meituan', 'https://mpc.meituan.com/#/ticket/product/new'],
      ['tongcheng', 'http://ebk.17u.cn/jingqu/']
    ]
  }
}

function makeEntries(entries) {
  return entries.map(([key, url]) => ({
    key,
    name: PLATFORM_BRANDS[key].name,
    logo: PLATFORM_BRANDS[key].logo,
    url
  }))
}

export function getScenicPlatformGroups(scenicId) {
  const entries = PLATFORM_ENTRIES[scenicId] || { hotel: [], ticket: [] }
  return [
    { key: 'scenic', title: '景区酒店平台入口', items: makeEntries(entries.hotel) },
    { key: 'ticket', title: '景区门票平台入口', items: makeEntries(entries.ticket) }
  ]
}

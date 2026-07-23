// 文旅业务·景区配置（前端常量）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// imagePath 指向 public/scenic/{id}.jpg；缺图时 UI 自动降级为渐变占位卡。
// 平台入口拆分为两类：scenicPlatforms（景区平台入口）/ ticketPlatforms（门票平台入口）。
// platformList / 链接为占位示例，运营可按实际店铺主页替换。

// 各平台品牌配置：name 显示名、color 品牌色、logo 官方图标（public/scenic/logos/*.png）。
export const PLATFORM_BRANDS = {
  douyin: { name: '抖音', color: '#0b0b0f', logo: '/scenic/logos/douyin.png' },
  ctrip: { name: '携程', color: '#2577e3', logo: '/scenic/logos/ctrip.png' },
  meituan: { name: '美团', color: '#ffc300', logo: '/scenic/logos/meituan.png' },
  tongcheng: { name: '同程', color: '#800573', logo: '/scenic/logos/tongcheng.png' }
}

// 各平台「按景区名搜索」的兜底 URL 生成器（未配置真实主页时降级用）。
function searchUrl(key, name) {
  const q = encodeURIComponent(name)
  return {
    douyin: `https://www.douyin.com/search/${q}`,
    ctrip: `https://you.ctrip.com/searchsite/default/keyword.html?query=${q}`,
    meituan: `https://www.meituan.com/search/${q}`,
    tongcheng: `https://www.ly.com/scenery/scenerysearchlist?keyword=${q}`
  }[key]
}

// 构造单个入口项。
// item 可为两种写法：
//   1) 字符串 key（如 'douyin'）        → 直接降级为「按景区名搜索」的兜底链接
//   2) 对象 { key, url }（url 为真实主页）→ 直达该 URL；url 为空/缺省时同样降级搜索
// 即：运营把真实店铺/账号主页贴进 url 即可直达绑定账号，没贴的自动兜底，UI/逻辑无需改。
function entry(item, name) {
  const key = typeof item === 'string' ? item : item.key
  const customUrl = typeof item === 'string' ? '' : (item.url || '')
  const b = PLATFORM_BRANDS[key]
  return {
    key,
    name: b.name,
    color: b.color,
    logo: b.logo,
    url: customUrl.trim() || searchUrl(key, name),
    isBound: Boolean(customUrl.trim()) // 是否已配置真实主页（预留给 UI 标记「已绑定」）
  }
}

function makeEntries(name, items) {
  return items.map((it) => entry(it, name))
}

// 各景区平台入口映射（scenic=景区平台入口，ticket=门票平台入口；空数组即「暂无入口」）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// 本轮已将 id 与新景区名对齐（拼音标识）；旧 id 见 migrations/20260717_scenic_id_rename.sql 的映射。
//
// ★ 如何配置「直达绑定账号」的真实主页 URL（运营维护点）：
//   把对应平台从字符串写法改成对象写法，填上真实店铺/账号主页地址即可，例如：
//     scenic: [
//       { key: 'douyin', url: 'https://www.douyin.com/user/xxxxx' },  // 直达该抖音号主页
//       'ctrip',                                                       // 留字符串=仍按景区名搜索兜底
//       { key: 'meituan', url: 'https://www.meituan.com/shop/123456' }
//     ]
//   填了 url 就直达、UI 会标记为已绑定；没填的自动降级为「按景区名搜索」。改完前端重新构建部署即可。
const SCENIC_DEFS = [
  {
    id: 'quancheng-ouleb', name: '泉城欧乐堡', ext: 'png',
    scenic: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://ebooking.ctrip.com' },
      { key: 'meituan', url: 'https://me.meituan.com' }
    ],
    ticket: []
  },
  {
    id: 'quanzhou-ouleb', name: '泉州欧乐堡', ext: 'jpg',
    scenic: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://ebooking.ctrip.com' },
      { key: 'meituan', url: 'https://me.meituan.com' }
    ],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' }
    ]
  },
  {
    id: 'fuzhou-ouleb', name: '福州欧乐堡', ext: 'jpg',
    scenic: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'meituan', url: 'https://me.meituan.com/login/index.html' }
    ],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'meituan', url: 'https://mpc.meituan.com/#/ticket/finance/pre' }
    ]
  },
  {
    id: 'zunyi-zoo', name: '遵义动物园', ext: 'jpg',
    scenic: [],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard' },
      { key: 'meituan', url: 'https://mpc.meituan.com/#/ticket/finance/pre' },
      { key: 'tongcheng', url: 'http://ebk.17u.cn/jingqu/' }
    ]
  },
  {
    id: 'nanyang-wildlife', name: '南阳森林野生动物世界', ext: 'jpg',
    scenic: [],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard' },
      { key: 'meituan', url: 'https://mpc.meituan.com/#/ticket/product/new' },
      { key: 'tongcheng', url: 'http://ebk.17u.cn/jingqu/' }
    ]
  },
  {
    id: 'guanquelou', name: '鹳雀楼', ext: 'jpg',
    scenic: [],
    ticket: [
      { key: 'douyin', url: 'https://life.douyin.com' },
      { key: 'ctrip', url: 'https://vbooking.ctrip.com/micro/ivbk/accountV2/dashboard' },
      { key: 'meituan', url: 'https://mpc.meituan.com/#/ticket/product/new' },
      { key: 'tongcheng', url: 'http://ebk.17u.cn/jingqu/' }
    ]
  }
]

export const scenicSpots = SCENIC_DEFS.map((s) => ({
  id: s.id,
  name: s.name,
  imagePath: `/scenic/${s.id}.${s.ext}`,
  scenicPlatforms: makeEntries(s.name, s.scenic),
  ticketPlatforms: makeEntries(s.name, s.ticket)
}))

/** 按 id 取景区配置；未知 id 返回 null。 */
export function getScenicById(id) {
  return scenicSpots.find((s) => s.id === id) || null
}

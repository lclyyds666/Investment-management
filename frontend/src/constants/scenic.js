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
  c58: { name: '58同城', color: '#3cb034', logo: '/scenic/logos/c58.png' }
}

// 按平台 key 构造入口项（url 为按景区名的搜索占位，运营可替换为实际店铺主页）。
function entry(key, name) {
  const b = PLATFORM_BRANDS[key]
  const q = encodeURIComponent(name)
  const urlMap = {
    douyin: `https://www.douyin.com/search/${q}`,
    ctrip: `https://you.ctrip.com/searchsite/default/keyword.html?query=${q}`,
    meituan: `https://www.meituan.com/search/${q}`,
    c58: `https://www.58.com/sou/?key=${q}`
  }
  return { key, name: b.name, color: b.color, logo: b.logo, url: urlMap[key] }
}

function makeEntries(name, keys) {
  return keys.map((k) => entry(k, name))
}

// 各景区平台入口映射（scenic=景区平台入口，ticket=门票平台入口；空数组即「暂无入口」）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// 本轮已将 id 与新景区名对齐（拼音标识）；旧 id 见 migrations/20260717_scenic_id_rename.sql 的映射。
const SCENIC_DEFS = [
  { id: 'quancheng-ouleb', name: '泉城欧乐堡', ext: 'png', scenic: ['douyin', 'ctrip', 'meituan'], ticket: [] },
  { id: 'quanzhou-ouleb', name: '泉州欧乐堡', ext: 'jpg', scenic: ['douyin', 'ctrip', 'meituan'], ticket: ['douyin'] },
  { id: 'fuzhou-ouleb', name: '福州欧乐堡', ext: 'jpg', scenic: ['douyin', 'meituan'], ticket: ['douyin', 'meituan'] },
  { id: 'zunyi-zoo', name: '遵义动物园', ext: 'jpg', scenic: [], ticket: ['douyin', 'ctrip', 'meituan', 'c58'] },
  { id: 'nanyang-wildlife', name: '南阳森林野生动物世界', ext: 'jpg', scenic: [], ticket: ['douyin', 'ctrip', 'meituan'] }
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

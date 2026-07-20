// 文旅业务·景区配置（前端常量）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// imagePath 指向 public/scenic/{id}.jpg；缺图时 UI 自动降级为渐变占位卡。
// platformList / 链接为占位示例，运营可按实际店铺主页替换。

// 各平台品牌色（用于入口徽标）
export const PLATFORM_BRANDS = {
  douyin: { name: '抖音', color: '#fe2c55' },
  ctrip: { name: '携程', color: '#2577e3' },
  meituan: { name: '美团', color: '#ffb000' },
  dianping: { name: '大众点评', color: '#ff6633' }
}

function P(key, url) {
  return { key, name: PLATFORM_BRANDS[key].name, color: PLATFORM_BRANDS[key].color, url }
}

// 各平台按景区名称的搜索入口（占位示例，运营可替换为实际店铺主页）
function platforms(name) {
  const q = encodeURIComponent(name)
  return [
    P('douyin', `https://www.douyin.com/search/${q}`),
    P('ctrip', `https://you.ctrip.com/searchsite/default/keyword.html?query=${q}`),
    P('meituan', `https://www.meituan.com/search/${q}`),
    P('dianping', `https://www.dianping.com/search/keyword/${q}`)
  ]
}

// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// 本轮已将 id 与新景区名对齐（拼音标识）；旧 id 见 migrations/20260717_scenic_id_rename.sql 的映射，
// 数据库如有历史台账会随迁移脚本同步更新（当前空表，脚本为幂等 no-op）。
export const scenicSpots = [
  { id: 'quancheng-ouleb', name: '泉城欧乐堡', imagePath: '/scenic/quancheng-ouleb.png', platformList: platforms('泉城欧乐堡') },
  { id: 'quanzhou-ouleb', name: '泉州欧乐堡', imagePath: '/scenic/quanzhou-ouleb.jpg', platformList: platforms('泉州欧乐堡') },
  { id: 'fuzhou-ouleb', name: '福州欧乐堡', imagePath: '/scenic/fuzhou-ouleb.jpg', platformList: platforms('福州欧乐堡') },
  { id: 'zunyi-zoo', name: '遵义动物园', imagePath: '/scenic/zunyi-zoo.jpg', platformList: platforms('遵义动物园') },
  { id: 'nanyang-wildlife', name: '南阳森林野生动物世界', imagePath: '/scenic/nanyang-wildlife.jpg', platformList: platforms('南阳森林野生动物世界') }
]

/** 按 id 取景区配置；未知 id 返回 null。 */
export function getScenicById(id) {
  return scenicSpots.find((s) => s.id === id) || null
}

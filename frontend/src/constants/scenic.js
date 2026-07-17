// 文旅业务·景区配置（前端常量）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// imagePath 指向 public/cultural-tourism/{id}.jpg；缺图时 UI 自动降级为渐变占位卡。
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

export const scenicSpots = [
  {
    id: 'qihe',
    name: '齐河欧乐堡梦幻世界',
    imagePath: '/cultural-tourism/qihe.jpg',
    platformList: [
      P('douyin', 'https://www.douyin.com/search/齐河欧乐堡梦幻世界'),
      P('ctrip', 'https://you.ctrip.com/sight/qihe/'),
      P('meituan', 'https://www.meituan.com/search/齐河欧乐堡'),
      P('dianping', 'https://www.dianping.com/search/keyword/齐河欧乐堡')
    ]
  },
  {
    id: 'quanzhou',
    name: '泉州欧乐堡海洋世界',
    imagePath: '/cultural-tourism/quanzhou.jpg',
    platformList: [
      P('douyin', 'https://www.douyin.com/search/泉州欧乐堡海洋世界'),
      P('ctrip', 'https://you.ctrip.com/sight/quanzhou/'),
      P('meituan', 'https://www.meituan.com/search/泉州欧乐堡海洋世界'),
      P('dianping', 'https://www.dianping.com/search/keyword/泉州欧乐堡海洋世界')
    ]
  },
  {
    id: 'penglai',
    name: '蓬莱阁景区',
    imagePath: '/cultural-tourism/penglai.jpg',
    platformList: [
      P('douyin', 'https://www.douyin.com/search/蓬莱阁'),
      P('ctrip', 'https://you.ctrip.com/sight/penglai/'),
      P('meituan', 'https://www.meituan.com/search/蓬莱阁'),
      P('dianping', 'https://www.dianping.com/search/keyword/蓬莱阁')
    ]
  },
  {
    id: 'taishan',
    name: '泰山风景区',
    imagePath: '/cultural-tourism/taishan.jpg',
    platformList: [
      P('douyin', 'https://www.douyin.com/search/泰山'),
      P('ctrip', 'https://you.ctrip.com/sight/taian/'),
      P('meituan', 'https://www.meituan.com/search/泰山风景区'),
      P('dianping', 'https://www.dianping.com/search/keyword/泰山风景区')
    ]
  },
  {
    id: 'mengshan',
    name: '蒙山旅游区',
    imagePath: '/cultural-tourism/mengshan.jpg',
    platformList: [
      P('douyin', 'https://www.douyin.com/search/蒙山旅游区'),
      P('ctrip', 'https://you.ctrip.com/sight/linyi/'),
      P('meituan', 'https://www.meituan.com/search/蒙山旅游区'),
      P('dianping', 'https://www.dianping.com/search/keyword/蒙山旅游区')
    ]
  }
]

/** 按 id 取景区配置；未知 id 返回 null。 */
export function getScenicById(id) {
  return scenicSpots.find((s) => s.id === id) || null
}

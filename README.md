# 中国官方黄金储备追踪

追踪并可视化中国国家外汇管理局（SAFE）发布的官方储备资产数据，重点关注黄金储备变化趋势。

## 数据范围

- **时间跨度**：2018年1月 — 至今（月度数据）
- **数据来源**：[国家外汇管理局 - 官方储备资产](https://www.safe.gov.cn/safe/whcb/index.html)

### 字段说明

| 字段 | 单位 | 说明 |
|------|------|------|
| `foreign_exchange_sdr` | 亿SDR | 外汇储备 |
| `imf_reserve_position_sdr` | 亿SDR | 基金组织储备头寸 |
| `sdr_sdr` | 亿SDR | 特别提款权 |
| `gold_usd` | 亿美元 | 黄金储备（美元计价） |
| `gold_oz` | 万盎司 | 黄金储备（盎司计量） |
| `other_reserves_sdr` | 亿SDR | 其他储备资产 |

## 项目结构

```
├── data/
│   ├── reserves.json       # 主数据文件（JSON）
│   └── reserves.csv        # 数据文件（CSV）
├── .github/
│   └── workflows/
│       └── update-data.yml # 每月自动更新工作流
├── index.html              # GitHub Pages 可视化页面
├── scraper.py              # 数据爬虫脚本
├── requirements.txt        # Python 依赖
└── README.md
```

## 本地运行

```bash
pip install -r requirements.txt
python scraper.py
```

运行后 `data/` 目录下的 JSON 和 CSV 文件会自动更新。

## GitHub Pages

`index.html` 提供交互式可视化页面，包含：

- 黄金储备价值趋势（亿美元）
- 黄金储备数量趋势（万盎司）
- 黄金隐含单价（美元/盎司）
- 全部储备资产对比趋势图
- 按年份筛选的详细数据表

## 自动更新

GitHub Actions 工作流在 **每月15日 22:00（北京时间）** 自动运行：

1. 抓取 SAFE 官网最新数据
2. 与已有数据对比，检测是否有新增记录
3. 如有更新则自动提交并推送
4. 部署到 GitHub Pages

也支持通过 `workflow_dispatch` 手动触发。

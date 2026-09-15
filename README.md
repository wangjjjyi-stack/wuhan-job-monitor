# 武汉央国企 + 世界500强求职监控 V2.1

这是一个给个人秋招使用的静态网站 + GitHub Actions 自动监控项目。

## 它会做什么

- 保存武汉/湖北央国企招聘入口及你的简历匹配分。
- 新增独立的 **2026 Fortune Global 500 在汉机会池**，含 Fortune 排名、武汉地点核验、匹配度和具体岗位。
- 当前人工核验岗位单独展示，避免把“公司有武汉办公室”误当成“现在就有适合你的岗位”.
- 每天北京时间 **08:00 / 13:00 / 20:00** 自动检查招聘官网。
- 页面变动时记录“官网有变化”。
- 从官网页面中自动寻找与校招、财务、经营、数字化、产业研究等有关的链接。
- 对发现的岗位/招聘详情做规则化“简历匹配度”评分。
- 自动标记：
  - 武汉相关岗位加分；
  - “长期驻外 / 海外常驻 / 全国调配 / 项目一线”等地点风险；
  - “计算机 / 软件 / 通信 / 电气 / 土木”等可能的专业硬门槛。
- GitHub Pages 自动展示最新数据。
- 网页中的个人投递进度保存在浏览器 localStorage，不会上传到仓库。

## 3 分钟部署

### 1. 新建 GitHub 仓库
例如：`wuhan-soe-job-monitor`。

### 2. 把本压缩包内的全部文件上传到仓库根目录
必须保留：
- `.github/workflows/`
- `config/`
- `data/`
- `index.html`
- `monitor.py`
- `requirements.txt`

### 3. 开启 GitHub Pages
进入仓库：
`Settings → Pages → Build and deployment → Source → GitHub Actions`

### 4. 第一次手动运行监控
`Actions → Recruitment Monitor → Run workflow`

首次运行会安装 Chromium，大约需要几分钟。完成后 `data/` 会自动产生监控结果并提交回仓库。

### 5. 打开网站
`Actions → Deploy GitHub Pages` 成功后，
在 `Settings → Pages` 会看到你的公开网址。

## 修改监控频率

文件：`.github/workflows/monitor.yml`

当前：
- 00:00 UTC = 北京时间 08:00
- 05:00 UTC = 北京时间 13:00
- 12:00 UTC = 北京时间 20:00

GitHub Actions 的定时任务可能有几分钟到几十分钟延迟，不适合用于“秒级抢投递”。

## 调整你的简历匹配规则

文件：`config/resume_profile.json`

你可以增删：
- `strong_keywords`
- `avoid_keywords`
- `technical_gate_keywords`
- `technical_major_requirements`

## 新增企业

在 `config/targets.json` 添加一项，并在 `data/jobs.json` / `data/jobs.js` 中增加企业卡片。

## 重要限制

1. 一些央企招聘网站是登录后可见、验证码或强反爬页面，自动检查可能失败。
2. “匹配度”是筛选工具，不代表能通过专业、院校、政治面貌、资格证等硬门槛。
3. 自动发现采用关键词与页面解析，不是招聘官网官方 API，可能有漏报或误报。
4. 最终投递前必须点进官网核对岗位名称、地点、专业、截止时间。


## V2.1 新增：世界500强武汉池

首批纳入的500强企业包括：
华为、联想、小米、京东、美的、海尔智家、施耐德电气、西门子、Honda/东风本田、沃尔玛/山姆、顺丰、富士康、FedEx。

筛选原则不是“500强都加”，而是：
1. 2026 Fortune Global 500 成员；
2. 有可验证的武汉实体、招聘地点或武汉职位；
3. 至少存在财务、经营、运营、项目、供应链、数字化等与你简历有交集的职能。

监控程序对该池启用 `require_wuhan=true`，自动发现的岗位详情若没有“武汉/Wuhan/湖北/Hubei”地点信号，不会推到网页的候选岗位区。

## 自动更新说明（重要）

V2.1 已把“监控”和“部署 Pages”放在同一个 GitHub Actions 工作流中。
因此每天自动监控结束后，会直接重新部署网站，不依赖机器人提交再次触发另一个工作流。

# RoboMaster公告跟踪工具使用教程

## 1. 安装和准备

### 1.1 安装依赖

首先确保您已安装所需的python3库：

```bash
pip install requests beautifulsoup4 tqdm
```

### 1.2 Git配置（可选）

如果您想使用Git功能，请确保：
- 已安装Git
- 已初始化Git仓库
- 设置Git用户信息

```bash
# 初始化Git仓库
git init

# 设置Git用户信息
export GIT_USER="您的用户名"
export GIT_EMAIL="您的邮箱"
```

## 2. 基本用法

### 2.1 跟踪单个公告

```bash
python3 main.py -id 1768
```

这将获取ID为1768的公告并保存。如果之前有保存过该公告的历史版本，会自动生成差异报告。

### 2.2 跟踪多个公告

```bash
python3 main.py -ids 1768,1769,1770
```

### 2.3 跟踪一个ID范围的公告

```bash
python3 main.py -begin 1760 -end 1780
```

## 3. 高级用法

### 3.1 限制请求频率

```bash
python3 main.py -begin 1760 -end 1780 -qps 2
```

这将限制每秒最多发送2个请求，避免被服务器限流。

### 3.2 指定存储路径

```bash
python3 main.py -id 1768 -storage ./my_announcements
```

### 3.3 使用自定义User-Agent

```bash
python3 main.py -id 1768 -ua "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

### 3.4 详细日志模式

```bash
python3 main.py -id 1768 -v
```

## 4. Git集成

### 4.1 启用Git自动提交

```bash
python3 main.py -id 1768 -git
```

当检测到公告有变化时，会自动提交到Git仓库。

### 4.2 Git测试模式

```bash
export DRY_RUN=true
python3 main.py -id 1768 -git
```

这会模拟Git操作但不真正执行。

## 5. 环境变量和自动化

### 5.1 使用环境变量配置

```bash
export BEGIN_ID=1760
export END_ID=1780
python3 main.py -env -git
```

### 5.2 设置定时任务

在Linux系统上，可以设置cron任务：

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天上午10点运行）
0 10 * * * cd /path/to/robomaster-tracker && export BEGIN_ID=1760 && export END_ID=1780 && python3 main.py -env -git
```

## 6. 文件和输出说明

程序运行后会创建以下目录和文件：

- `announcements/` - 保存原始公告内容
  - `{公告ID}_{日期}.html` - 公告内容文件
- `diffs/` - 保存差异报告
  - `diff_{公告ID}_{旧日期}_vs_{新日期}.html` - 差异对比文件
- `diff_records_{日期时间}.json` - 本次运行检测到的所有变更记录

差异对比文件可以用浏览器打开，将以高亮形式显示添加和删除的内容。

## 7. 常见问题解答

### 问题1：首次运行没有生成差异报告

首次运行时只会保存当前版本的公告内容，需要等待公告有更新后再次运行才能生成差异报告。

### 问题2：如何验证Git配置是否生效？

运行时添加`-v`参数，查看日志输出中是否有"已设置Git邮箱"和"已设置Git用户名"的提示。

### 问题3：如何查看历史变更？

如果您启用了Git功能，可以使用Git命令查看历史变更：

```bash
git log --pretty=full
```

---

希望这个教程能帮助您使用这个工具！如有其他问题，请随时提问。
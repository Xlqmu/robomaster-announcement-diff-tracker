import requests
from bs4 import BeautifulSoup
import os
import argparse
import time
from datetime import datetime
import difflib
import glob
import re
import concurrent.futures
from tqdm import tqdm
import logging
import json
import subprocess
import tempfile

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class QpsLimiter:
    """限制请求频率的类"""

    def __init__(self, qps):
        self.qps = qps
        self.min_interval = 1.0 / qps
        self.last_request_time = 0

    def wait(self):
        """等待合适的时间再发送下一个请求"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()


class DiffRecord:
    """差异记录类"""

    def __init__(self, announcement_id, previous_date, latest_date, diff_file):
        self.announcement_id = announcement_id
        self.previous_date = previous_date
        self.latest_date = latest_date
        self.diff_file = diff_file

    def to_dict(self):
        return {
            "announcement_id": self.announcement_id,
            "previous_date": self.previous_date,
            "latest_date": self.latest_date,
            "diff_file": self.diff_file,
        }


def init_git():
    """初始化Git配置"""
    try:
        # 检查git是否可用
        result = subprocess.run(
            ["git", "--version"], check=True, capture_output=True, text=True
        )
        logger.debug(f"Git版本: {result.stdout.strip()}")

        # 设置Git配置
        if "GIT_EMAIL" in os.environ:
            email = os.environ["GIT_EMAIL"]
            subprocess.run(
                ["git", "config", "--global", "user.email", email], check=True
            )
            logger.debug(f"已设置Git邮箱: {email}")

        if "GIT_USER" in os.environ:
            name = os.environ["GIT_USER"]
            subprocess.run(["git", "config", "--global", "user.name", name], check=True)
            logger.debug(f"已设置Git用户名: {name}")

        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git初始化失败: {e}")
        return False
    except Exception as e:
        logger.error(f"Git初始化出错: {str(e)}")
        return False


def commit_changes(diff_records, storage_path):
    """将变更提交到Git仓库"""
    if not diff_records:
        logger.debug("没有检测到变更，跳过Git提交")
        return True

    try:
        dry_run = os.environ.get("DRY_RUN") == "true"

        # git add
        logger.info("执行 git add")
        cmd = ["git", "add", storage_path]
        logger.debug(f"命令: {' '.join(cmd)}")
        if not dry_run:
            subprocess.run(cmd, check=True)

        # 准备提交消息
        commit_title = f"diff {len(diff_records)} records"
        commit_message = json.dumps(
            [r.to_dict() for r in diff_records], ensure_ascii=False, indent=2
        )

        # 创建临时文件存储提交信息
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as temp_file:
            temp_file.write(f"{commit_title}\n\n")
            temp_file.write(commit_message)
            temp_file_path = temp_file.name

        # git commit
        logger.info("执行 git commit")
        cmd = ["git", "commit", "-F", temp_file_path]
        logger.debug(f"命令: {' '.join(cmd)}")
        if not dry_run:
            subprocess.run(cmd, check=True)

        # 删除临时文件
        os.unlink(temp_file_path)

        logger.info("Git提交成功")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git操作失败: {e}")
        return False
    except Exception as e:
        logger.error(f"执行Git操作时出错: {str(e)}")
        return False


def get_env_int(key, fallback=0):
    """获取环境变量中的整数值"""
    if key in os.environ:
        try:
            return int(os.environ[key])
        except ValueError:
            return fallback
    return fallback


def fetch_and_save_announcement(announcement_id, qps_limiter, user_agent, storage_path):
    """获取并保存特定公告页面内容"""
    url = f"https://www.robomaster.com/zh-CN/resource/pages/announcement/{announcement_id}"

    # 应用QPS限制
    qps_limiter.wait()

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        response = requests.get(url, headers=headers)
        response.encoding = "utf-8"
        html_content = response.text

        soup = BeautifulSoup(html_content, "html.parser")

        # 提取公告内容区域
        detail_section = soup.find("div", {"class": "content-container"})
        if detail_section:
            content = detail_section.prettify()
        else:
            # 检查是否是404页面
            if "404" in soup.text or "未找到" in soup.text:
                logger.debug(f"公告 {announcement_id} 不存在")
                return None
            content = soup.prettify()

        # 创建存储目录
        announcement_dir = os.path.join(storage_path, "announcements")
        if not os.path.exists(announcement_dir):
            os.makedirs(announcement_dir)

        # 保存当前版本
        today = datetime.now().strftime("%Y%m%d")
        file_name = os.path.join(announcement_dir, f"{announcement_id}_{today}.html")
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(content)

        logger.debug(f"公告 {announcement_id} 已保存到 {file_name}")
        return file_name
    except Exception as e:
        logger.error(f"获取公告 {announcement_id} 时发生错误: {str(e)}")
        return None


def compare_versions(announcement_id, storage_path):
    """比较最新和上一个版本的公告内容"""
    # 查找所有该公告的历史版本
    announcement_dir = os.path.join(storage_path, "announcements")
    files = glob.glob(os.path.join(announcement_dir, f"{announcement_id}_*.html"))

    if len(files) < 2:
        logger.debug(f"公告 {announcement_id} 目前只有一个版本，无法比较")
        return None

    # 按文件名（日期）排序
    files.sort()
    latest_file = files[-1]
    previous_file = files[-2]

    # 提取日期信息
    latest_date = re.search(r"_(\d+)\.html$", latest_file).group(1)
    previous_date = re.search(r"_(\d+)\.html$", previous_file).group(1)

    # 如果是同一天的文件，不需要比较
    if latest_date == previous_date:
        logger.debug(f"公告 {announcement_id} 今天已经比较过，跳过")
        return None

    logger.debug(f"正在比较版本: {previous_date} vs {latest_date}")

    # 读取文件内容
    with open(latest_file, "r", encoding="utf-8") as file:
        latest_content = file.read()

    with open(previous_file, "r", encoding="utf-8") as file:
        previous_content = file.read()

    # 如果内容完全相同，跳过
    if latest_content == previous_content:
        logger.debug(f"公告 {announcement_id} 内容没有变化，跳过")
        return None

    # 生成差异报告
    diff = difflib.HtmlDiff()
    diff_html = diff.make_file(
        previous_content.splitlines(),
        latest_content.splitlines(),
        f"公告版本 ({previous_date})",
        f"公告版本 ({latest_date})",
        context=True,
    )

    # 创建差异目录
    diff_dir = os.path.join(storage_path, "diffs")
    if not os.path.exists(diff_dir):
        os.makedirs(diff_dir)

    # 保存差异报告
    diff_file = os.path.join(
        diff_dir, f"diff_{announcement_id}_{previous_date}_vs_{latest_date}.html"
    )
    with open(diff_file, "w", encoding="utf-8") as file:
        file.write(diff_html)

    logger.debug(f"公告 {announcement_id} 的差异已保存到 {diff_file}")

    # 返回差异记录
    return DiffRecord(announcement_id, previous_date, latest_date, diff_file)


def process_announcement(announcement_id, qps_limiter, user_agent, storage_path):
    """处理单个公告，获取内容并比较差异"""
    try:
        file_path = fetch_and_save_announcement(
            announcement_id, qps_limiter, user_agent, storage_path
        )
        if file_path:
            diff_record = compare_versions(announcement_id, storage_path)
            return diff_record
    except Exception as e:
        logger.error(f"处理公告 {announcement_id} 时出错: {str(e)}")
    return None


def main():
    parser = argparse.ArgumentParser(description="RoboMaster公告跟踪和比较工具")
    parser.add_argument("-id", type=int, help="要获取的单个公告ID")
    parser.add_argument("-ids", type=str, help="要获取的公告ID列表，使用逗号分隔")
    parser.add_argument("-begin", type=int, help="起始公告ID")
    parser.add_argument("-end", type=int, help="结束公告ID")
    parser.add_argument("-qps", type=int, default=5, help="每秒请求数限制")
    parser.add_argument("-ua", type=str, help="自定义User-Agent")
    parser.add_argument("-storage", type=str, default="./", help="存储路径")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    parser.add_argument("-git", action="store_true", help="启用Git自动提交")
    parser.add_argument("-env", action="store_true", help="从环境变量获取配置")
    parser.add_argument(
        "-monitor", action="store_true", help="监控模式，只在检测到更新时生成差异"
    )

    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # 初始化Git（如果启用）
    if args.git:
        if not init_git():
            logger.error("Git初始化失败，禁用Git功能")
            args.git = False

    # 收集所有需要处理的ID
    ids = set()

    # 从环境变量获取配置
    if args.env:
        begin_id = get_env_int("BEGIN_ID")
        end_id = get_env_int("END_ID")

        if begin_id >= end_id:
            logger.error("无效的ID范围，请正确设置BEGIN_ID和END_ID环境变量")
            return

        # 使用环境变量设置的ID范围
        ids = set(range(begin_id, end_id + 1))
        logger.info(f"从环境变量获取ID范围: {begin_id} - {end_id}")
    else:
        # 从命令行参数获取ID
        if args.id:
            ids.add(args.id)

        if args.ids:
            for id_str in args.ids.split(","):
                try:
                    ids.add(int(id_str))
                except ValueError:
                    logger.error(f"无效的ID: {id_str}")

        if args.begin and args.end and args.begin < args.end:
            for i in range(args.begin, args.end + 1):
                ids.add(i)

    if not ids:
        parser.print_help()
        return

    # 创建QPS限制器
    qps_limiter = QpsLimiter(args.qps)

    # 存储路径
    storage_path = args.storage

    # 使用线程池并发处理
    diff_records = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(args.qps * 2, 20)
    ) as executor:
        futures = {
            executor.submit(
                process_announcement, id, qps_limiter, args.ua, storage_path
            ): id
            for id in ids
        }

        # 显示进度条
        with tqdm(total=len(ids), desc="处理公告") as progress_bar:
            for future in concurrent.futures.as_completed(futures):
                announcement_id = futures[future]
                try:
                    result = future.result()
                    if result:
                        diff_records.append(result)
                except Exception as e:
                    logger.error(f"处理公告 {announcement_id} 时出错: {str(e)}")
                progress_bar.update(1)

    # 输出结果统计
    logger.info(f"总共处理: {len(ids)} 个公告，其中有 {len(diff_records)} 个有变化")

    # 保存差异记录
    if diff_records:
        record_file = os.path.join(
            storage_path,
            f"diff_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        with open(record_file, "w", encoding="utf-8") as f:
            json.dump(
                [r.to_dict() for r in diff_records], f, ensure_ascii=False, indent=2
            )
        logger.info(f"差异记录已保存到 {record_file}")

        # 打印有变化的公告ID
        logger.info(
            "有变化的公告ID: " + ", ".join(str(r.announcement_id) for r in diff_records)
        )

        # Git提交变更（如果启用）
        if args.git:
            commit_changes(diff_records, storage_path)


if __name__ == "__main__":
    main()

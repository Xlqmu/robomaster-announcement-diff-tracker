import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

# RoboMaster 公告页面 URL
url = "https://www.robomaster.com/zh-CN/announcement"

response = requests.get(url)
response.encoding = 'utf-8'
html_content = response.text

# 用 BeautifulSoup 提取公告内容
soup = BeautifulSoup(html_content, 'html.parser')

# 提取公告部分，根据实际页面结构可能需要调整
announcement_section = soup.find("div", {"class": "announcement-list"})
if announcement_section:
    announcement_content = announcement_section.prettify()
else:
    announcement_content = soup.prettify()

# 创建保存目录
if not os.path.exists("announcements"):
    os.makedirs("announcements")

# 保存为 HTML 文件，文件名带上日期
file_name = f"announcements/announcement_{datetime.now().strftime('%Y%m%d')}.html"
with open(file_name, 'w', encoding='utf-8') as file:
    file.write(announcement_content)

print(f"公告已保存到 {file_name}")


import requests
import telegram
from bs4 import BeautifulSoup
import time

TOKEN = '7471049461:AAGz4viJgjq89qd7CMFkvOLe-A1vO8ZDS_o'
CHANNEL_ID = '@K_AirDrop_Alert_bot'

bot = telegram.Bot(token=TOKEN)

last_upbit_title = ''
last_bithumb_title = ''

def check_upbit_event():
    global last_upbit_title
    url = 'https://upbit.com/service_center/notice'
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    first_post = soup.select_one('.notice-list li a')
    title = first_post.text.strip()
    link = 'https://upbit.com' + first_post['href']
    if title != last_upbit_title:
        last_upbit_title = title
        bot.send_message(chat_id=CHANNEL_ID, text=f'📢 [업비트 이벤트] {title}\n{link}')

def check_bithumb_event():
    global last_bithumb_title
    url = 'https://www.bithumb.com/customer_support/info_guide'
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    first_post = soup.select_one('table tbody tr td.subject a')
    title = first_post.text.strip()
    link = 'https://www.bithumb.com' + first_post['href']
    if title != last_bithumb_title:
        last_bithumb_title = title
        bot.send_message(chat_id=CHANNEL_ID, text=f'📢 [빗썸 이벤트] {title}\n{link}')

while True:
    try:
        check_upbit_event()
        check_bithumb_event()
    except Exception as e:
        print(f'에러 발생: {e}')
    time.sleep(300)  # 5분 간격

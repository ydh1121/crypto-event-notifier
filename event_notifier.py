import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime
import os

# 환경변수에서 정보 불러오기
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')

# 텔레그램 메시지 전송 함수
def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {
        'chat_id': TELEGRAM_CHANNEL_ID,
        'text': message
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("텔레그램 전송 오류:", e)

# 업비트 크롤링 함수 (셀레니움)
def check_upbit_event(latest_title):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://upbit.com/service_center/notice?id=112")
        time.sleep(3)

        notice = driver.find_element(By.CSS_SELECTOR, ".css-6f91y1 > li:nth-child(1)")
        title = notice.find_element(By.CSS_SELECTOR, ".css-4rbku5").text
        date = notice.find_element(By.CSS_SELECTOR, ".css-1jgnnso").text
        link = notice.find_element(By.TAG_NAME, "a").get_attribute("href")

        if "이벤트" in title and title != latest_title:
            return {'title': title, 'date': date, 'link': link}
    except Exception as e:
        print("업비트 크롤링 오류:", e)
    finally:
        driver.quit()
    return None

# 빗썸 크롤링 함수
def check_bithumb_new_event(latest_bithumb_id):
    url = 'https://feed.bithumb.com/notice?category=8&page=1'
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    notice_list = soup.select('li > a.NoticeContentList_notice-list__link__LAkAV')
    new_items = []

    for item in notice_list:
        title = item.select_one('.NoticeContentList_notice-list__link-title__nlmSC')
        if title and '에어드랍' in title.text:
            link = 'https://feed.bithumb.com' + item['href']
            article_id = item['href'].split('/')[-1]
            date_span = item.select_one('.NoticeContentList_notice-list__link-date__gDc6U')
            date = date_span.text if date_span else '날짜 없음'

            if article_id != latest_bithumb_id:
                new_items.append({
                    'id': article_id,
                    'title': title.text.strip(),
                    'link': link,
                    'date': date
                })
                break
    return new_items

# 메인 루프
if __name__ == '__main__':
    latest_upbit_title = None
    latest_bithumb_id = None

    send_telegram_message("✅ 텔레그램 연동 테스트 메시지입니다.")

    while True:
        try:
            # 업비트 확인
            new_upbit = check_upbit_event(latest_upbit_title)
            if new_upbit:
                message = f"[업비트 이벤트]\n{new_upbit['date']}\n{new_upbit['title']}\n{new_upbit['link']}"
                send_telegram_message(message)
                latest_upbit_title = new_upbit['title']

            # 빗썸 확인
            new_bithumb = check_bithumb_new_event(latest_bithumb_id)
            if new_bithumb:
                for event in new_bithumb:
                    message = f"[빗썸 이벤트]\n{event['date']}\n{event['title']}\n{event['link']}"
                    send_telegram_message(message)
                    latest_bithumb_id = event['id']

        except Exception as e:
            print("오류 발생:", e)

        time.sleep(60)

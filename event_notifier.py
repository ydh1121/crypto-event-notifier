import requests
import telegram
from bs4 import BeautifulSoup
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# === 텔레그램 설정 ===
import os
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

# === 마지막 제목 저장 ===
last_upbit_title = ''
last_bithumb_title = ''

def check_upbit_event():
    global last_upbit_title

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    service = Service(executable_path='./chromedriver.exe')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get("https://upbit.com/service_center/notice")
        time.sleep(3)

        event_tab = driver.find_element(By.XPATH, "//span[text()='이벤트']")
        driver.execute_script("arguments[0].click();", event_tab)
        time.sleep(3)

        rows = driver.find_elements(By.CSS_SELECTOR, "tr.css-nxo5rk")
        for row in rows:
            title_elem = row.find_element(By.CSS_SELECTOR, "td.css-c8ywoi a")
            date_elem = row.find_element(By.CSS_SELECTOR, "td.css-a7n042 span")
            title = title_elem.text.strip()
            link = title_elem.get_attribute("href")
            date = date_elem.text.strip()

            if ("에어드랍" in title or "공부" in title) and title != last_upbit_title and date == time.strftime('%Y.%m.%d'):
                last_upbit_title = title
                bot.send_message(chat_id=CHANNEL_ID, text=f"{date} 업비트 이벤트\n{title}\n{link}")
                break
    except Exception as e:
        print(f"업비트 크롤링 오류: {e}")
    finally:
        driver.quit()

def check_bithumb_event():
    global last_bithumb_title
    try:
        url = 'https://www.bithumb.com/customer_support/info_guide'
        res = requests.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        first_post = soup.select_one('table tbody tr td.subject a')
        date_elem = soup.select_one('table tbody tr td.date')

        if first_post is None or date_elem is None:
            print("빗썸 첫 게시글을 찾을 수 없습니다.")
            return

        title = first_post.text.strip()
        link = 'https://www.bithumb.com' + first_post['href']
        date = date_elem.text.strip()

        if ("에어드랍" in title or "공부" in title) and title != last_bithumb_title and date == time.strftime('%Y.%m.%d'):
            last_bithumb_title = title
            bot.send_message(chat_id=CHANNEL_ID, text=f"{date} 빗썸 이벤트\n{title}\n{link}")
    except Exception as e:
        print(f"빗썸 크롤링 오류: {e}")

# === 테스트 메시지 ===
bot.send_message(chat_id=CHANNEL_ID, text="✅ 텔레그램 연동 테스트 메시지입니다.")

# === 1분마다 반복 실행 ===
while True:
    try:
        check_upbit_event()
        check_bithumb_event()
    except Exception as e:
        print(f'에러 발생: {e}')
    time.sleep(60)

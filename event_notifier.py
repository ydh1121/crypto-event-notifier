import requests
import telegram
from bs4 import BeautifulSoup
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# === 텔레그램 설정 ===
TOKEN = '7471049461:AAGz4viJgjq89qd7CMFkvOLe-A1vO8ZDS_o'
CHANNEL_ID = '@K_AirDrop_Alert_bot'
bot = telegram.Bot(token=TOKEN)

# === 마지막 업비트 게시글 ID 저장 ===
sent_upbit_ids = set()

# === 키워드 필터 ===
KEYWORDS = ['에어드랍', '공부']

# === 업비트 이벤트 크롤링 (Selenium 사용) ===
def check_upbit_event():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    service = Service(executable_path='./chromedriver.exe')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get("https://upbit.com/service_center/notice")
        time.sleep(3)

        # '이벤트' 탭 클릭
        event_tab = driver.find_element(By.XPATH, "//span[text()='이벤트']")
        driver.execute_script("arguments[0].click();", event_tab)
        time.sleep(3)

        # 게시글 목록 수집
        posts = driver.find_elements(By.CSS_SELECTOR, 'tr.css-nxo5rk.css-knz4ib')
        today_str = datetime.now().strftime('%Y.%m.%d')

        for post in posts:
            try:
                date_elem = post.find_element(By.CSS_SELECTOR, 'span.css-13q9n9q')
                post_date = date_elem.text.strip()

                if post_date != today_str:
                    continue

                link_elem = post.find_element(By.CSS_SELECTOR, 'a.css-12ct4qh')
                link = 'https://upbit.com' + link_elem.get_attribute('href')
                title = link_elem.text.strip()

                post_id = link.split('id=')[-1]
                if post_id in sent_upbit_ids:
                    continue

                if any(keyword in title for keyword in KEYWORDS):
                    message = f"{post_date} 업비트 이벤트\n{title}\n{link}"
                    bot.send_message(chat_id=CHANNEL_ID, text=message)
                    sent_upbit_ids.add(post_id)

            except Exception as e:
                print(f"게시글 처리 오류: {e}")

    except Exception as e:
        print(f"업비트 크롤링 오류: {e}")

    finally:
        driver.quit()

# === 반복 실행 (1분 간격) ===
while True:
    try:
        check_upbit_event()
    except Exception as e:
        print(f'에러 발생: {e}')
    time.sleep(60)  # 1분 대기

import requests
import telegram
from bs4 import BeautifulSoup
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from datetime import datetime

# === 텔레그램 설정 ===
TOKEN = '7471049461:AAGz4viJgjq89qd7CMFkvOLe-A1vO8ZDS_o'
CHANNEL_ID = '@K_AirDrop_Alert_bot'
bot = telegram.Bot(token=TOKEN)

# ✅ 연동 테스트 메시지
bot.send_message(chat_id=CHANNEL_ID, text="✅ 텔레그램 연동 테스트 메시지입니다.")

# === 마지막 게시글 제목 저장용 변수 ===
last_upbit_title = ''
last_bithumb_title = ''

KEYWORDS = ['에어드랍', '공부']

# === 업비트 이벤트 확인 (Selenium 사용) ===
def check_upbit_event():
    global last_upbit_title

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    service = Service(executable_path='./chromedriver.exe')
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://upbit.com/service_center/notice")
        time.sleep(3)

        # '이벤트' 탭 클릭
        event_tab = driver.find_element(By.XPATH, "//span[text()='이벤트']")
        driver.execute_script("arguments[0].click();", event_tab)
        time.sleep(3)

        # 게시글 목록 추출
        rows = driver.find_elements(By.CSS_SELECTOR, "tr.css-nxo5rk")

        for row in rows:
            title_elem = row.find_element(By.CSS_SELECTOR, "a")
            date_elem = row.find_element(By.CSS_SELECTOR, "span.css-13q9n9q")

            title = title_elem.text.strip()
            link = title_elem.get_attribute("href")
            date = date_elem.text.strip()

            today = datetime.now().strftime("%Y.%m.%d")

            if today in date and title != last_upbit_title:
                if any(keyword in title for keyword in KEYWORDS):
                    last_upbit_title = title
                    bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=f"{date} 업비트 이벤트\n{title}\n{link}"
                    )
                break  # 첫 글만 확인

    except Exception as e:
        print(f"업비트 크롤링 오류: {e}")
    finally:
        driver.quit()

# === 빗썸 이벤트 확인 ===
def check_bithumb_event():
    global last_bithumb_title
    url = 'https://www.bithumb.com/customer_support/info_guide'
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')

    rows = soup.select('table tbody tr')

    today = datetime.now().strftime("%Y.%m.%d")

    for row in rows:
        title_elem = row.select_one('td.subject a')
        date_elem = row.select_one('td.date')

        if not title_elem or not date_elem:
            continue

        title = title_elem.text.strip()
        date = date_elem.text.strip()
        link = 'https://www.bithumb.com' + title_elem['href']

        if today == date and title != last_bithumb_title:
            if any(keyword in title for keyword in KEYWORDS):
                last_bithumb_title = title
                bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=f"{date} 빗썸 이벤트\n{title}\n{link}"
                )
            break  # 첫 글만 확인

# === 루프 실행 ===
while True:
    try:
        check_upbit_event()
        check_bithumb_event()
    except Exception as e:
        print(f'에러 발생: {e}')
    time.sleep(60)  # 1분 간격

import os
import requests
import openai
from datetime import datetime

# ========== CONFIGURATION ==========
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

openai.api_key = OPENAI_API_KEY
NEWS_ENDPOINT = 'https://newsapi.org/v2/top-headlines'

# ========== DUPLICATE TRACKING ==========
def load_sent_headlines():
    try:
        with open("sent_headlines.txt", "r") as f:
            return set(line.strip() for line in f.readlines())
    except FileNotFoundError:
        return set()

def save_sent_headline(title):
    with open("sent_headlines.txt", "a") as f:
        f.write(title + "\n")

SENT_HEADLINES = load_sent_headlines()
EVALUATED_HEADLINES = set()

# ========== TELEGRAM ==========
def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    response = requests.post(url, data=data)
    return response.status_code == 200

# ========== AI ANALYSIS ==========
def analyze_event_ai(event_text):
    prompt = f"""
    You are a senior crypto analyst and market trader. Your job is to analyze how global news affects the price of cryptocurrencies.

    Headline: "{event_text}"

    Respond in this format:
    Direction: up/down/neutral
    Confidence: <number>%
    Explanation: <short but clear market-based reasoning>
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response['choices'][0]['message']['content']
        lines = content.split("\n")
        direction = "neutral"
        confidence = 50
        explanation = "No explanation."

        for line in lines:
            if line.lower().startswith("direction"):
                direction = line.split(":")[-1].strip().lower()
            elif line.lower().startswith("confidence"):
                confidence = int(line.split(":")[-1].strip().replace("%", ""))
            elif line.lower().startswith("explanation"):
                explanation = line.split(":", 1)[-1].strip()

        return direction, confidence, explanation

    except Exception as e:
        return "neutral", 50, f"AI analysis failed: {str(e)}"

# ========== FORMAT MESSAGE ==========
def format_result(event_text, direction, confidence, explanation, published_at):
    arrow = "📉" if direction == "down" else "📈" if direction == "up" else "➖"
    return f"""\n📰 {event_text}\n🕒 Published: {published_at}\n🤖 AI-based analysis\nDirection: {direction.upper()} {arrow}\nConfidence: {confidence}%\nExplanation: {explanation}\n"""

# ========== FETCH & ANALYZE ==========
def fetch_news():
    print("✅ Script started: fetching news...")  # Debug line

    KEYWORDS = ['bitcoin', 'crypto', 'ethereum', 'SEC', 'inflation', 'interest rate', 'Trump', 'ETF', 'Binance', 'lawsuit', 'regulation', 'hacked', 'halving', 'adoption', 'crackdown', 'tariff', 'federal reserve', 'usd', 'recession']
    FORCE_REVIEW = ['trump', 'protest', 'unrest', 'clash', 'musk', 'riot', 'chaos', 'emergency', 'conflict']

    params = {
        'apiKey': NEWS_API_KEY,
        'language': 'en',
        'pageSize': 10,
    }

    response = requests.get(NEWS_ENDPOINT, params=params)
    data = response.json()

    if data.get('status') != 'ok':
        print("❌ Failed to fetch news:", data)
        return

    articles = data.get('articles', [])
    print(f"\n🔍 Found {len(articles)} headlines. Analyzing...\n")

    for article in articles:
        title = article['title']
        published_at_raw = article.get('publishedAt', '')
        published_at = ''

        try:
            dt = datetime.strptime(published_at_raw, "%Y-%m-%dT%H:%M:%SZ")
            published_at = dt.strftime("%Y-%m-%d %H:%M UTC")
        except:
            published_at = "Unknown time"

        if title in EVALUATED_HEADLINES:
            print("🔁 Skipped already evaluated headline (this run):", title)
            continue

        if title in SENT_HEADLINES:
            print("🔁 Skipped duplicate headline (already sent):", title)
            continue

        EVALUATED_HEADLINES.add(title)

        if any(keyword.lower() in title.lower() for keyword in KEYWORDS):
            direction, confidence, explanation = analyze_event_ai(title)
            message = format_result(title, direction, confidence, explanation, published_at)

            if direction in ["up", "down"] and confidence >= 65:
                send_telegram_message(message)
                save_sent_headline(title)
                SENT_HEADLINES.add(title)
                print("✅ Alert sent to Telegram:", title)
            elif any(word in title.lower() for word in FORCE_REVIEW) and confidence >= 60 and direction != "neutral":
                send_telegram_message(message)
                save_sent_headline(title)
                SENT_HEADLINES.add(title)
                print("⚠️ Forced alert (special topic):", title)
            else:
                print("ℹ️ Skipped (low confidence or neutral):", title)

# ========== ENTRY POINT ==========
if __name__ == '__main__':
    fetch_news()

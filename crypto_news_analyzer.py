import os
import requests
import openai
from datetime import datetime

# ========== CONFIGURATION ==========
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Replace with your Gist RAW URL
GIST_RAW_URL = "https://gist.githubusercontent.com/bobenok228/22642d47313245c8e005a9d77d14801d/raw/a319a8d2a7114a5be244cf4bce9340e7b9d5b7d4/sent_headlines.txt"

openai.api_key = OPENAI_API_KEY
NEWS_ENDPOINT = 'https://newsapi.org/v2/top-headlines'
EVALUATED_HEADLINES = set()

# ========== GIST TRACKING ==========
def load_sent_headlines():
    try:
        response = requests.get(GIST_RAW_URL, timeout=10)
        if response.status_code == 200:
            return set(line.strip().lower() for line in response.text.splitlines())
        else:
            print("⚠️ Failed to fetch Gist:", response.status_code)
            return set()
    except Exception as e:
        print("⚠️ Error fetching Gist:", str(e))
        return set()

def save_sent_headline(title):
    try:
        response = requests.get(GIST_RAW_URL, timeout=10)
        if response.status_code != 200:
            print("⚠️ Cannot update Gist: fetch failed.")
            return
        current = response.text.strip() + f"\n{title}"

        # Convert RAW to PATCH endpoint
        patch_url = GIST_RAW_URL.replace("/raw/", "/").split("/gist.githubusercontent.com/")[1]
        patch_url = f"https://api.github.com/gists/{patch_url.split('/')[1]}"

        update = {
            "files": {
                "sent_headlines.txt": {
                    "content": current
                }
            }
        }

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}"
        }

        patch = requests.patch(patch_url, headers=headers, json=update)
        if patch.status_code != 200:
            print("⚠️ Failed to update Gist:", patch.status_code)
    except Exception as e:
        print("⚠️ Error updating Gist:", str(e))

# ========== TELEGRAM ==========
def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': message}
    response = requests.post(url, data=data)
    return response.status_code == 200

# ========== GPT ANALYSIS ==========
def analyze_event_ai(event_text):
    prompt = f"""
    You are a senior crypto analyst. Analyze how this headline might affect the crypto market.

    Headline: "{event_text}"

    Format:
    Direction: up/down/neutral
    Confidence: <number>%
    Explanation: <short market impact reasoning>
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
    print("✅ Script started: fetching news...")

    KEYWORDS = ['bitcoin', 'crypto', 'ethereum', 'SEC', 'inflation', 'interest rate', 'Trump', 'ETF', 'Binance', 'lawsuit', 'regulation', 'hacked', 'halving', 'adoption', 'crackdown', 'tariff', 'federal reserve', 'usd', 'recession']
    FORCE_REVIEW = ['trump', 'protest', 'unrest', 'clash', 'musk', 'riot', 'chaos', 'emergency', 'conflict']

    SENT_HEADLINES = load_sent_headlines()

    params = {
        'apiKey': NEWS_API_KEY,
        'language': 'en',
        'pageSize': 10,
    }

    try:
        response = requests.get(NEWS_ENDPOINT, params=params, timeout=10)
        data = response.json()
    except Exception as e:
        print("❌ Failed to fetch news:", str(e))
        return

    if data.get('status') != 'ok':
        print("❌ NewsAPI error:", data)
        return

    articles = data.get('articles', [])
    print(f"\n🔍 Found {len(articles)} headlines. Analyzing...\n")

    for article in articles:
        title = article['title']
        clean_title = title.strip().lower()

        if clean_title in EVALUATED_HEADLINES or clean_title in SENT_HEADLINES:
            print("🔁 Skipped duplicate headline:", title)
            continue

        EVALUATED_HEADLINES.add(clean_title)

        published_at_raw = article.get('publishedAt', '')
        published_at = "Unknown time"
        try:
            dt = datetime.strptime(published_at_raw, "%Y-%m-%dT%H:%M:%SZ")
            published_at = dt.strftime("%Y-%m-%d %H:%M UTC")
        except:
            pass

        if any(keyword.lower() in clean_title for keyword in KEYWORDS):
            direction, confidence, explanation = analyze_event_ai(title)
            message = format_result(title, direction, confidence, explanation, published_at)

            if direction in ["up", "down"] and confidence >= 65:
                send_telegram_message(message)
                save_sent_headline(clean_title)
                print("✅ Alert sent to Telegram:", title)
            elif any(word in clean_title for word in FORCE_REVIEW) and confidence >= 60 and direction != "neutral":
                send_telegram_message(message)
                save_sent_headline(clean_title)
                print("⚠️ Forced alert (special topic):", title)
            else:
                print("ℹ️ Skipped (low confidence or neutral):", title)

# ========== RUN ==========
if __name__ == '__main__':
    fetch_news()
    
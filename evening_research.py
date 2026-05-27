"""
Evening Research Job — รัน Agents 1-5 ค้นข้อมูล แล้ว exit
Railway Cron: 0 10 * * *  (17:00 Bangkok = 10:00 UTC)
"""
import anthropic
import json
import datetime
import os
import sys
import time
import pickle
import io
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# ─── CONFIG ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")   # base64-encoded token

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── AGENTS ──────────────────────────────────────────────────────────────────
AGENTS = {
    "journalist": {
        "id": 1, "emoji": "📰",
        "name": "Agent 1 — นักข่าวนักค้นคว้า",
        "system": """คุณคือนักข่าวมืออาชีพที่เชี่ยวชาญด้านข่าวสารที่มีผลต่อการลงทุน
ติดตามข่าวการเมืองโลก เศรษฐกิจ สงคราม และ Corporate events
รายงานแบบ bullet points กระชับ ชัดเจน ระบุความสำคัญต่อตลาด""",
        "prompt": """ค้นหาและรวบรวมข่าวสำคัญวันนี้ที่มีผลต่อการลงทุน:
1. ข่าวการเมืองโลก 3 เรื่องสำคัญ (ระบุผลกระทบต่อตลาด)
2. ข่าวเศรษฐกิจ/นโยบายการเงิน 3 เรื่อง (Fed, GDP, Inflation)
3. ความขัดแย้ง/ความเสี่ยงภูมิรัฐศาสตร์
4. ข่าว Corporate สำคัญ (Earnings, M&A)
5. สรุป Market Sentiment: 🟢 Bullish / 🔴 Bearish / 🟡 Mixed
รายงานภาษาไทย"""
    },
    "broker": {
        "id": 2, "emoji": "📊",
        "name": "Agent 2 — Broker มืออาชีพ",
        "system": """คุณคือ Broker มืออาชีพที่วิเคราะห์ตลาดหุ้นทั่วโลก
เชี่ยวชาญ: US (S&P500, NASDAQ), China, India, Vietnam, Thailand SET Index
รวมถึง Crypto และ Commodity""",
        "prompt": """วิเคราะห์ภาพรวมตลาดหุ้นทั่วโลกวันนี้:
1. US Markets: S&P500, NASDAQ — แนวโน้มและ key levels
2. Asia: China SSE, India SENSEX, Vietnam VN-Index, Japan Nikkei
3. ไทย: SET Index — Foreign Flow และแนวโน้ม
4. Crypto: Bitcoin, Ethereum
5. Commodity: Gold, Oil
6. Sector ที่ Outperform / Underperform
รายงานภาษาไทย พร้อม Sentiment แต่ละตลาด"""
    },
    "technical": {
        "id": 3, "emoji": "📈",
        "name": "Agent 3 — Technical Analyst",
        "system": """คุณคือ Technical Analyst ผู้เชี่ยวชาญการวิเคราะห์กราฟ
ใช้: MACD, RSI, EMA (20/50/200), Bollinger Bands, Elliott Wave, Fibonacci
วิเคราะห์ Trend, Momentum, Pattern และ Entry/Exit points""",
        "prompt": """วิเคราะห์ Technical ของสินทรัพย์สำคัญวันนี้:
1. S&P500 — Trend, Support/Resistance, Indicator signals
2. SET Index — EMA crossover, Volume, แนวโน้มกราฟ
3. Gold — Technical setup
4. Bitcoin — Technical setup
5. Market Structure สรุป: Uptrend / Downtrend / Sideways
6. Key Levels ที่ต้องจับตา
7. Signal Summary: BUY 🟢 / SELL 🔴 / NEUTRAL 🟡
รายงานภาษาไทย"""
    },
    "economist": {
        "id": 4, "emoji": "🌐",
        "name": "Agent 4 — ที่ปรึกษาเศรษฐกิจโลก",
        "system": """คุณคือนักเศรษฐศาสตร์ระดับโลก วิเคราะห์ Macro Economics
เชี่ยวชาญ Monetary Policy, Business Cycle, Global Trade, Recession indicators
ประเมินระยะสั้น (1-3 เดือน), กลาง (3-12 เดือน), ยาว (1-3 ปี)""",
        "prompt": """ประเมินสถานการณ์เศรษฐกิจโลกปัจจุบัน:
1. ภาพรวมเศรษฐกิจโลก: Expansion / Slowdown / Recession?
2. สหรัฐฯ: GDP, Job market, Inflation outlook
3. China: Economic health, Property, Export
4. ยุโรป: ECB policy, Energy, Political risk
5. ไทย: GDP, Export, Tourism, THB outlook
6. ปัจจัยเสี่ยง Top 3
7. Outlook ระยะสั้น/กลาง/ยาว — Risk: Low/Medium/High
รายงานภาษาไทย"""
    },
    "financial_advisor": {
        "id": 5, "emoji": "💰",
        "name": "Agent 5 — ที่ปรึกษาการเงิน",
        "system": """คุณคือที่ปรึกษาการเงินและการลงทุนมืออาชีพ
เชี่ยวชาญ Asset Allocation, Risk Management, Portfolio Management
DCA Strategy, Hedging, Position Sizing, Drawdown Management""",
        "prompt": """ประเมินและแนะนำการจัดการพอร์ตวันนี้:
1. Market Risk Level วันนี้: 1-10
2. Asset Allocation แนะนำ: Equity/Bond/Cash/Alt สัดส่วนที่เหมาะสม
3. Sector/Asset ที่ควร Overweight / Underweight
4. กลยุทธ์ Hedge ที่เหมาะสม
5. Portfolio Action: Buy/Hold/Sell อะไรวันนี้?
6. ระดับ Cash ที่ควรถือ
7. คำแนะนำแยกตาม Risk: Conservative / Moderate / Aggressive
รายงานภาษาไทย"""
    },
}

# ─── GOOGLE DRIVE ────────────────────────────────────────────────────────────
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_gdrive_service():
    """Get Drive service using token stored as env var (JSON string)."""
    if not GDRIVE_TOKEN_JSON:
        print("[Drive] GDRIVE_TOKEN_JSON not set — skipping Drive save")
        return None
    try:
        import base64
        token_data = json.loads(base64.b64decode(GDRIVE_TOKEN_JSON).decode())
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=GDRIVE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"[Drive] Auth error: {e}")
        return None

def save_to_gdrive(content: str, filename: str) -> str:
    service = get_gdrive_service()
    if not service:
        return ""
    try:
        meta = {"name": filename, "mimeType": "text/plain"}
        if GDRIVE_FOLDER_ID:
            meta["parents"] = [GDRIVE_FOLDER_ID]
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
        f = service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        url = f.get("webViewLink", "")
        print(f"[Drive] Saved {filename} → {url}")
        return url
    except Exception as e:
        print(f"[Drive] Save error: {e}")
        return ""

# ─── RUN AGENT ───────────────────────────────────────────────────────────────
def run_agent(key: str) -> str:
    a = AGENTS[key]
    print(f"[{a['emoji']}] Running {a['name']}...")
    try:
        res = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=a["system"],
            messages=[{
                "role": "user",
                "content": a["prompt"] + f"\n\nวันที่: {datetime.datetime.utcnow().strftime('%d/%m/%Y')} UTC"
            }]
        )
        text = res.content[0].text
        print(f"[{a['emoji']}] Done ✓ ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[{a['emoji']}] ERROR: {e}")
        return f"[Error: {e}]"

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"🌙 Evening Research — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}")

    reports = {}
    for key in AGENTS:
        reports[key] = run_agent(key)
        time.sleep(3)

    # Build cache JSON content
    payload = {
        "research_date": datetime.datetime.utcnow().isoformat(),
        "reports": reports
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)

    # Save to Google Drive as cache file
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    url = save_to_gdrive(content, f"agent_cache_{date_str}.json")

    print(f"\n✅ Evening research complete")
    print(f"   Agents done: {len(reports)}/5")
    if url:
        print(f"   Drive: {url}")

    # Also save file ID for morning job via env (not possible in cron)
    # Instead save locally — morning cron will re-fetch from Drive by date
    Path("cache_latest.json").write_text(content, encoding="utf-8")
    print("   Local cache saved ✓")

if __name__ == "__main__":
    main()
    sys.exit(0)   # must exit for Railway cron

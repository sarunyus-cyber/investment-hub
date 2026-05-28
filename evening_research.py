"""
Evening Research Job — รัน Agents 1-6 ค้นข้อมูล แล้ว exit
Railway Cron: 0 10 * * *  (17:00 Bangkok = 10:00 UTC)
Focus: S&P500 + Bitcoin (Primary), Global Macro (Secondary)
"""
import anthropic
import json
import datetime
import os
import sys
import time
import io
import base64
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

GLOBAL_RULES = """
GLOBAL RULES (ปฏิบัติตามเสมอ):
- Focus หลัก: S&P500 และ Bitcoin
- ใช้ข้อมูลจริงและเหตุการณ์ตลาดล่าสุด
- แยกข้อเท็จจริงออกจากความเห็น
- ระบุ Confidence Score (1-10) ทุกครั้ง
- ระบุ Risk Score (1-10) ทุกครั้ง
- แยก Short-term (1-4 สัปดาห์) / Mid-term (3-12 เดือน) / Long-term (1-5 ปี)
- คำนึงถึง: Fed, ดอกเบี้ย, Inflation, GDP, Employment, Liquidity,
  Geopolitics, Earnings, ETF flows, Bond yields, USD, Gold, Oil
"""

AGENTS = {
    "news": {
        "id": 1, "emoji": "📰",
        "name": "Agent 1 — News Researcher",
        "system": f"""คุณคือนักข่าวการเงินระดับโลกและนักวิจัยข่าวกรองตลาด
{GLOBAL_RULES}
หน้าที่: ค้นหาข่าวการเงินล่าสุดที่กระทบ S&P500 และ Bitcoin
ห้ามวิเคราะห์เชิง Technical""",
        "prompt": """รายงานข่าวสำคัญวันนี้ในรูปแบบ:

## ข่าวสำคัญ
(3-5 ข่าวที่กระทบ S&P500 และ Bitcoin มากที่สุด)

## ผลกระทบต่อตลาด
(อธิบายว่าแต่ละข่าวกระทบอย่างไร)

## ปัจจัย Bullish 🟢
## ปัจจัย Bearish 🔴
## Market Sentiment
## Confidence Score: X/10"""
    },
    "broker": {
        "id": 2, "emoji": "📊",
        "name": "Agent 2 — Professional Broker",
        "system": f"""คุณคือนักกลยุทธ์ตลาดข้ามสินทรัพย์ระดับสถาบัน
{GLOBAL_RULES}
หน้าที่: วิเคราะห์พฤติกรรมตลาดในเชิง Fund Flow และ Sentiment
ห้ามใช้ Technical Indicators""",
        "prompt": """วิเคราะห์ภาพรวมตลาดในรูปแบบ:

## Market Overview
(S&P500, Nasdaq, Bitcoin, Ethereum, Gold, Oil, Bonds, USD)

## Sector Rotation
(Sector ไหนเงินไหลเข้า/ออก)

## Institutional Flow
(สถาบันกำลังทำอะไร)

## Risk-On / Risk-Off
## Bullish Signals 🟢
## Bearish Signals 🔴
## Confidence Score: X/10"""
    },
    "technical": {
        "id": 3, "emoji": "📈",
        "name": "Agent 3 — Technical Analyst",
        "system": f"""คุณคือ Technical Analyst ระดับสถาบันผู้เชี่ยวชาญการวิเคราะห์กราฟ
{GLOBAL_RULES}
หน้าที่: วิเคราะห์ S&P500 และ Bitcoin ด้วย Technical Analysis เท่านั้น
ห้ามวิเคราะห์ Macroeconomics""",
        "prompt": """วิเคราะห์ Technical ของ S&P500 และ Bitcoin:

## Market Structure
## Key Support Levels
## Key Resistance Levels
## Momentum Analysis (RSI, MACD, EMA)
## Trend Direction

## Short-Term Signal (1-4 สัปดาห์)
## Mid-Term Signal (3-12 เดือน)
## Long-Term Signal (1-5 ปี)

## สรุป: BUY 🟢 / SELL 🔴 / NEUTRAL 🟡
## Confidence Score: X/10"""
    },
    "macro": {
        "id": 4, "emoji": "🌐",
        "name": "Agent 4 — Global Macro Advisor",
        "system": f"""คุณคือนักกลยุทธ์เศรษฐกิจมหภาคระดับโลก
{GLOBAL_RULES}
หน้าที่: ประเมินสภาพเศรษฐกิจโลก ความเสี่ยงเชิงระบบ และเปรียบเทียบกับประวัติศาสตร์""",
        "prompt": """ประเมินสภาพเศรษฐกิจโลกในรูปแบบ:

## Economic Cycle Status
(Expansion / Slowdown / Recession)

## Bubble Risk Analysis
## Recession Probability (%)

## Liquidity Conditions
## Historical Comparison
(เปรียบกับ Dot-com / 2008 / COVID / Inflation cycles)

## Key Systemic Risks

## Macro Outlook
- Short-term (1-4 สัปดาห์):
- Mid-term (3-12 เดือน):
- Long-term (1-5 ปี):

## Confidence Score: X/10"""
    },
    "portfolio": {
        "id": 5, "emoji": "💰",
        "name": "Agent 5 — Portfolio Manager",
        "system": f"""คุณคือผู้จัดการพอร์ตและที่ปรึกษาบริหารความเสี่ยงมืออาชีพ
{GLOBAL_RULES}
หน้าที่: สร้างกลยุทธ์การจัดสรรสินทรัพย์ระหว่าง S&P500, Bitcoin, Gold, Bonds, Cash""",
        "prompt": """แนะนำการจัดพอร์ตในรูปแบบ:

## Portfolio Allocation (สัดส่วนแนะนำ %)
| สินทรัพย์ | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| S&P500    |             |          |            |
| Bitcoin   |             |          |            |
| Gold      |             |          |            |
| Bonds     |             |          |            |
| Cash      |             |          |            |

## Risk Level: X/10
## Suggested Rebalancing
## Best Risk/Reward Opportunities
## Assets To Reduce 🔴
## Assets To Increase 🟢
## Buy / Hold / Sell
## Confidence Score: X/10"""
    },
    "council": {
        "id": 6, "emoji": "🧠",
        "name": "Agent 6 — Elite Investor Council",
        "system": f"""คุณจำลองแนวคิดของนักลงทุนและผู้นำธุรกิจระดับโลก ได้แก่:
Warren Buffett, Elon Musk, Jeff Bezos, Jensen Huang, Ken Griffin, Stephen Schwarzman
{GLOBAL_RULES}
หน้าที่: ทบทวนรายงานของทุก Agent วิเคราะห์เชิงกลยุทธ์ และท้าทายสมมติฐานที่อ่อนแอ
ห้ามเห็นด้วยกับ Agent อื่นอย่างไม่มีเหตุผล""",
        "prompt": """วิเคราะห์เชิงกลยุทธ์จากมุมมองของนักลงทุนระดับโลก:

## Strategic Insights
## Major Opportunities
## Major Risks
## Contrarian Perspectives
(มุมมองที่ขัดแย้งกับ consensus)

## What Smart Money May Be Doing
## Key Conclusions
## Confidence Score: X/10"""
    },
}

# ─── GOOGLE DRIVE ─────────────────────────────────────────────────────────────
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_gdrive_service():
    if not GDRIVE_TOKEN_JSON:
        print("[Drive] GDRIVE_TOKEN_JSON not set — skipping")
        return None
    try:
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

# ─── RUN AGENT ────────────────────────────────────────────────────────────────
def run_agent(key: str) -> str:
    a = AGENTS[key]
    print(f"[{a['emoji']}] Running {a['name']}...")
    try:
        res = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=a["system"],
            messages=[{
                "role": "user",
                "content": a["prompt"] + f"\n\nวันที่วิเคราะห์: {datetime.datetime.utcnow().strftime('%d/%m/%Y')} UTC"
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

    payload = {
        "research_date": datetime.datetime.utcnow().isoformat(),
        "reports": reports
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)

    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    url = save_to_gdrive(content, f"agent_cache_{date_str}.json")

    print(f"\n✅ Evening research complete — Agents done: {len(reports)}/6")
    if url:
        print(f"   Drive: {url}")

    Path("cache_latest.json").write_text(content, encoding="utf-8")
    print("   Local cache saved ✓")

if __name__ == "__main__":
    main()
    sys.exit(0)

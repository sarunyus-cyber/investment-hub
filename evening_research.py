"""
Investment Intelligence Hub — All-in-One
รัน Agents 1-6 ค้นข้อมูล → CEO สรุป → ส่ง Email via Gmail API → บันทึก Drive
Railway Cron: 0 14 * * *  (21:00 Bangkok = 14:00 UTC)
"""
import anthropic
import json
import datetime
import os
import sys
import re
import time
import base64
import io
import email.mime.text
import email.mime.multipart
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_RECIPIENT   = os.environ.get("EMAIL_RECIPIENT", "")
EMAIL_SENDER      = os.environ.get("EMAIL_SENDER", "")
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

GLOBAL_RULES = """
GLOBAL RULES:
- Focus: S&P500 and Bitcoin
- Confidence Score (1-10) and Risk Score (1-10)
- Short-term / Mid-term / Long-term
- Consider: Fed, Interest rates, Inflation, GDP, Geopolitics, Earnings, ETF flows
"""

AGENTS = {
    "news": {
        "emoji": "\U0001f4f0", "name": "Agent 1 \u2014 News Researcher",
        "system": "You are a world-class financial journalist focused on S&P500 and Bitcoin.\n" + GLOBAL_RULES,
        "searches": [
            "S&P500 stock market news today",
            "Bitcoin crypto news today",
            "Federal Reserve interest rate news today",
            "US economy inflation employment news today",
            "geopolitical risk market impact today",
        ],
        "prompt": """Search the web first using the search queries provided, then report:
## ข่าวสำคัญวันนี้ที่กระทบ S&P500 และ Bitcoin
- รายงาน 3-5 ข่าวใหญ่ที่สุดของวันนี้ พร้อมวันที่และแหล่งข่าว
- อธิบายผลกระทบต่อ S&P500 และ Bitcoin แยกกัน
- ปัจจัยบวก (Bullish) และปัจจัยลบ (Bearish)
- Market Sentiment วันนี้: Bullish/Bearish/Mixed
- Confidence Score: X/10"""
    },
    "broker": {
        "emoji": "\U0001f4ca", "name": "Agent 2 \u2014 Broker",
        "system": "You are an institutional cross-market strategist analyzing Fund Flow and Sentiment.\n" + GLOBAL_RULES,
        "searches": [
            "S&P500 SPX price today closing",
            "Bitcoin BTC price today USD",
            "Gold price today XAU",
            "US Treasury bond yield today",
            "US Dollar DXY index today",
            "Nasdaq 100 QQQ price today",
        ],
        "prompt": """Search the web for today\'s actual prices first, then analyze:
## ราคาตลาดวันนี้ (ใช้ราคาจริงที่ค้นมาได้)
| สินทรัพย์ | ราคา | เปลี่ยนแปลง % |
|-----------|------|--------------|
| S&P500    | (ราคาจริง) | |
| Bitcoin   | (ราคาจริง) | |
| Gold      | (ราคาจริง) | |
| Bond 10Y  | (yield จริง) | |
| USD (DXY) | (ค่าจริง) | |

## Sector Rotation วันนี้
## Institutional Flow: Risk-On หรือ Risk-Off?
## Bullish/Bearish Signals
- Confidence Score: X/10"""
    },
    "technical": {
        "emoji": "\U0001f4c8", "name": "Agent 3 \u2014 Technical",
        "system": "You are an elite technical analyst for S&P500 and Bitcoin.\n" + GLOBAL_RULES,
        "searches": [
            "S&P500 SPX technical analysis support resistance today",
            "S&P500 SPX RSI MACD signal today",
            "Bitcoin BTC technical analysis support resistance today",
            "Bitcoin BTC RSI MACD signal today",
        ],
        "prompt": """Search for today\'s technical data first, then analyze using ACTUAL current prices:
## S&P500 Technical Analysis
- ราคาปัจจุบัน: (ราคาจริงวันนี้)
- แนวรับ: / แนวต้าน: (ระดับจริง)
- RSI: / MACD: / EMA:
- Trend: / Signal: BUY/HOLD/SELL

## Bitcoin Technical Analysis  
- ราคาปัจจุบัน: (ราคาจริงวันนี้)
- แนวรับ: / แนวต้าน: (ระดับจริง)
- RSI: / MACD: / EMA:
- Trend: / Signal: BUY/HOLD/SELL

- Confidence Score: X/10"""
    },
    "macro": {
        "emoji": "\U0001f310", "name": "Agent 4 \u2014 Macro",
        "system": "You are a world-class macroeconomic strategist.\n" + GLOBAL_RULES,
        "searches": [
            "Federal Reserve Fed meeting decision interest rate 2025",
            "US inflation CPI data latest 2025",
            "US GDP growth rate latest 2025",
            "US unemployment jobs report latest 2025",
            "global recession risk economic outlook 2025",
        ],
        "prompt": """Search for latest economic data first, then evaluate:
## สถานการณ์เศรษฐกิจโลกล่าสุด
- Fed Policy ล่าสุด: อัตราดอกเบี้ยปัจจุบัน + แนวโน้ม
- Inflation (CPI) ล่าสุด: X%
- GDP Growth ล่าสุด: X%
- Unemployment ล่าสุด: X%
## Economic Cycle: Expansion/Slowdown/Recession
## Recession Probability: X%
## ผลกระทบต่อ S&P500 และ Bitcoin
- Confidence Score: X/10"""
    },
    "portfolio": {
        "emoji": "\U0001f4b0", "name": "Agent 5 \u2014 Portfolio",
        "system": "You are a professional portfolio manager for S&P500/Bitcoin/Gold/Bonds/Cash.\n" + GLOBAL_RULES,
        "searches": [
            "S&P500 ETF SPY VOO fund flow today",
            "Bitcoin ETF BTC fund flow inflow outflow today",
            "Gold ETF GLD fund flow today",
            "market volatility VIX index today",
        ],
        "prompt": """Search for fund flow and volatility data first, then recommend:
## สถานะตลาดวันนี้
- VIX (Fear Index): (ค่าจริง) — ตลาด Fear/Greed?
- Bitcoin ETF Flow: เงินไหลเข้า/ออก
- S&P500 ETF Flow: เงินไหลเข้า/ออก

## แนะนำพอร์ต (อิงจากข้อมูลจริงวันนี้)
| สินทรัพย์ | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| S&P500    | X%          | X%       | X%         |
| Bitcoin   | X%          | X%       | X%         |
| Gold      | X%          | X%       | X%         |
| Bond      | X%          | X%       | X%         |
| Cash      | X%          | X%       | X%         |

## Risk Level: X/10
## Action: Buy/Hold/Sell อะไร และเท่าไหร่
- Confidence Score: X/10"""
    },
    "council": {
        "emoji": "\U0001f9e0", "name": "Agent 6 \u2014 Elite Council",
        "system": "You simulate Buffett, Musk, Bezos, Jensen Huang. Challenge weak assumptions.\n" + GLOBAL_RULES,
        "searches": [
            "Warren Buffett Berkshire investment portfolio 2025",
            "institutional investor hedge fund positioning S&P500 Bitcoin 2025",
            "smart money flow stock market today",
            "contrarian investment view S&P500 Bitcoin today",
        ],
        "prompt": """Search for what smart money and elite investors are doing now, then analyze:
## มุมมองนักลงทุนระดับโลก
- Buffett/Berkshire: กำลังทำอะไรอยู่?
- Hedge Funds: Positioning อย่างไร?
- Smart Money: เงินไหลไปทางไหน?

## Contrarian View (มุมมองที่ขัดแย้งกับ consensus)
## Hidden Risks ที่คนส่วนใหญ่มองข้าม
## Asymmetric Opportunities วันนี้
## Key Conclusion สำหรับ CEO
- Confidence Score: X/10"""
    },
}

AGENT_META = {k: {"emoji": v["emoji"], "name": v["name"]} for k, v in AGENTS.items()}

# ─── GOOGLE SERVICES ──────────────────────────────────────────────────────────
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/documents",
]

def get_google_creds():
    if not GDRIVE_TOKEN_JSON:
        return None
    try:
        token_data = json.loads(base64.b64decode(GDRIVE_TOKEN_JSON).decode())
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=GOOGLE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as e:
        print(f"[Google] Auth error: {e}")
        return None

def get_gdrive_service():
    creds = get_google_creds()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)

def get_gmail_service():
    creds = get_google_creds()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)

def save_to_gdrive(content, filename):
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
        print(f"[Drive] Saved {filename}")
        return url
    except Exception as e:
        print(f"[Drive] Save error: {e}")
        return ""

# ─── GOOGLE DOCS ──────────────────────────────────────────────────────────────
def save_to_gdocs(ceo_report, agent_reports, date_str):
    """Create a Google Doc with the full briefing report."""
    creds = get_google_creds()
    if not creds:
        return ""
    try:
        docs_service  = build("docs",  "v1", credentials=creds)
        drive_service = get_gdrive_service()

        # Build full text content first
        bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
        timestamp = bkk.strftime("%d %B %Y %H:%M Bangkok")

        lines = []
        lines.append(f"INVESTMENT BRIEFING {date_str}")
        lines.append(f"{timestamp}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("CEO SUMMARY (Agent 7)")
        lines.append("=" * 60)
        lines.append("")
        lines.append(ceo_report)
        lines.append("")
        lines.append("=" * 60)
        lines.append("AGENT REPORTS")
        lines.append("=" * 60)
        lines.append("")

        for key, report in agent_reports.items():
            m = AGENT_META.get(key, {"emoji": "-", "name": key})
            lines.append(f"--- {m['name']} ---")
            lines.append("")
            lines.append(report)
            lines.append("")

        full_text = "\n".join(lines)

        # Create Google Doc with title only
        doc_title = f"Investment Briefing {date_str}"
        doc = docs_service.documents().create(body={"title": doc_title}).execute()
        doc_id  = doc["documentId"]
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        # Move to Investment Reports folder
        if GDRIVE_FOLDER_ID and drive_service:
            try:
                drive_service.files().update(
                    fileId=doc_id,
                    addParents=GDRIVE_FOLDER_ID,
                    removeParents="root",
                    fields="id,parents"
                ).execute()
            except Exception as e:
                print(f"[Docs] Move error (non-fatal): {e}")

        # Insert all text at index 1 in ONE request — avoids Thai char index issues
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [
                {"insertText": {"location": {"index": 1}, "text": full_text}}
            ]}
        ).execute()

        print(f"[Docs] Created: {doc_title} -> {doc_url}")
        return doc_url

    except Exception as e:
        print(f"[Docs] ERROR: {e}")
        return ""

# ─── RUN AGENT WITH WEB SEARCH ───────────────────────────────────────────────
def run_agent(key):
    a = AGENTS[key]
    print(f"[{a['emoji']}] Running {a['name']} (with web search)...")
    today = datetime.datetime.utcnow().strftime("%d/%m/%Y")

    # Build search instruction from agent-specific queries
    searches = a.get("searches", [])
    search_instruction = ""
    if searches:
        search_list = "\n".join(f"  - {q}" for q in searches)
        search_instruction = (
            f"STEP 1: Use web_search for EACH of these queries (search all of them):\n"
            f"{search_list}\n\n"
            f"STEP 2: Analyze using the ACTUAL real-time data you found.\n"
            f"Always cite actual prices/data from search results.\n\n"
        )

    user_message = (
        f"Today is {today} Bangkok time.\n\n"
        f"{search_instruction}"
        f"{a['prompt']}"
    )

    messages = [{"role": "user", "content": user_message}]

    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2000,
            system=a["system"],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages
        )

        final_text = ""
        loop_count = 0

        while True:
            # Extract text from current response
            for block in res.content:
                if hasattr(block, "type") and block.type == "text":
                    final_text += block.text

            if res.stop_reason != "tool_use" or loop_count >= 8:
                break

            loop_count += 1
            messages.append({"role": "assistant", "content": res.content})

            # Pass tool results back
            tool_results = []
            for block in res.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed — use results to analyze."
                    })
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            res = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=a["system"],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

        print(f"[{a['emoji']}] Done ({len(final_text)} chars, {loop_count} searches)")
        return final_text if final_text else "[No response]"

    except Exception as e:
        print(f"[{a['emoji']}] Web search ERROR: {e} — retrying without search...")
        try:
            res2 = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                system=a["system"],
                messages=[{"role": "user", "content": a["prompt"] + f"\nDate: {today}"}]
            )
            return res2.content[0].text
        except Exception as e2:
            return f"[Error: {e2}]"

# ─── CEO ──────────────────────────────────────────────────────────────────────
def call_ceo(agent_reports):
    print("[CEO] Synthesizing...")
    sections = ""
    for key, report in agent_reports.items():
        m = AGENT_META.get(key, {"emoji": "-", "name": key})
        short = report[:600] if len(report) > 600 else report
        sections += f"\n{m['emoji']} {m['name']}: {short}\n"

    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    bkk_date = bkk.strftime("%d %B %Y")

    prompt = f"""สร้าง Morning Briefing ภาษาไทย จากรายงานต่อไปนี้:{sections}

สำคัญมาก: แยกการวิเคราะห์ S&P500 กับ Bitcoin ออกจากกันให้ชัดเจน ห้ามปนกัน
ใช้รูปแบบต่อไปนี้อย่างเคร่งครัด:

## Morning Briefing {bkk_date}

### สรุปภาพรวม
(3-4 ประโยค อธิบายสถานการณ์ตลาดโดยรวมวันนี้)

### S&P500 Analysis
**แนวโน้ม:** (Bullish/Bearish/Sideways พร้อมเหตุผล)
**ปัจจัยบวก:** (2-3 ข้อ เฉพาะ S&P500)
**ปัจจัยลบ:** (2-3 ข้อ เฉพาะ S&P500)
**แนวรับ-แนวต้าน:** (ระบุระดับราคา)
**Signal:** BUY/HOLD/SELL

### Bitcoin Analysis
**แนวโน้ม:** (Bullish/Bearish/Sideways พร้อมเหตุผล)
**ปัจจัยบวก:** (2-3 ข้อ เฉพาะ Bitcoin)
**ปัจจัยลบ:** (2-3 ข้อ เฉพาะ Bitcoin)
**แนวรับ-แนวต้าน:** (ระบุระดับราคา)
**Signal:** BUY/HOLD/SELL

### จุดสังเกต (Watch)
(2-3 เหตุการณ์ที่ต้องจับตาในสัปดาห์นี้)

### แนะนำพอร์ต
| สินทรัพย์ | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| S&P500    | X%          | X%       | X%         |
| Bitcoin   | X%          | X%       | X%         |
| Gold      | X%          | X%       | X%         |
| Bond      | X%          | X%       | X%         |
| Cash      | X%          | X%       | X%         |

### แผนปฏิบัติการ
1. **S&P500:** (ระบุชัดเจนว่า เพิ่ม/ลด/ถือ กี่% และเหตุผล)
2. **Bitcoin:** (ระบุชัดเจนว่า เพิ่ม/ลด/ถือ กี่% และเหตุผล)
3. **Gold/Bond/Cash:** (ระบุชัดเจนว่า ปรับสัดส่วนอย่างไร)

### Final Decision
**S&P500:** BUY/HOLD/SELL (เหตุผล 1 ประโยค)
**Bitcoin:** BUY/HOLD/SELL (เหตุผล 1 ประโยค)
**Risk Score:** X/10 | **Confidence:** X/10

---
*คำเตือน: ข้อมูลนี้เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนตัดสินใจ*"""

    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            system="คุณคือ CEO สรุปรายงานการลงทุนเป็นภาษาไทย กระชับมาก ห้ามเกิน 800 คำ แยก S&P500 กับ Bitcoin ชัดเจน ระบุสินทรัพย์และ action ชัดเจนทุกข้อ",
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.content[0].text
        print(f"[CEO] Done ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[CEO] ERROR: {e}")
        return f"[CEO Error: {e}]"

# ─── EMAIL via Gmail API ──────────────────────────────────────────────────────
def md_to_html(text):
    # Remove non-Thai/non-ASCII garbled characters
    import unicodedata
    cleaned = []
    for ch in text:
        name = unicodedata.name(ch, "")
        cat = unicodedata.category(ch)
        # Keep: ASCII, Thai, common punctuation, spaces, newlines
        if (ord(ch) < 128 or
            0x0E00 <= ord(ch) <= 0x0E7F or  # Thai
            cat in ("Po","Ps","Pe","Pi","Pf","Pd","Pc") or
            ch in ("\n","\t","\r"," ")):
            cleaned.append(ch)
        elif cat.startswith("L") or cat.startswith("N"):
            # Keep letters and numbers from any script except Cyrillic
            if not (0x0400 <= ord(ch) <= 0x04FF):
                cleaned.append(ch)
    text = "".join(cleaned)

    # Convert markdown table rows
    lines = text.split("\n")
    result = []
    in_table = False
    table_rows = []
    for line in lines:
        if line.strip().startswith("|") and "|" in line[1:]:
            if not in_table:
                in_table = True
                table_rows = []
            if not all(c in "|-: " for c in line.replace("|","")):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                table_rows.append(cells)
        else:
            if in_table:
                html_table = '<table style="border-collapse:collapse;width:100%;margin:10px 0">'
                for i, row in enumerate(table_rows):
                    html_table += "<tr>"
                    tag = "th" if i == 0 else "td"
                    style = "background:#1e3a5f;color:white;padding:8px 10px;font-size:15px;font-weight:bold" if i == 0 else "padding:8px 10px;border:1px solid #e5e7eb;font-size:15px"
                    for cell in row:
                        html_table += f'<{tag} style="{style}">{cell}</{tag}>'
                    html_table += "</tr>"
                html_table += "</table>"
                result.append(html_table)
                in_table = False
                table_rows = []
            result.append(line)
    if in_table and table_rows:
        html_table = '<table style="border-collapse:collapse;width:100%;margin:10px 0">'
        for i, row in enumerate(table_rows):
            html_table += "<tr>"
            tag = "th" if i == 0 else "td"
            style = "background:#1e3a5f;color:white;padding:8px 10px;font-size:15px;font-weight:bold" if i == 0 else "padding:8px 10px;border:1px solid #e5e7eb;font-size:15px"
            for cell in row:
                html_table += f'<{tag} style="{style}">{cell}</{tag}>'
            html_table += "</tr>"
        html_table += "</table>"
        result.append(html_table)
    text = "\n".join(result)

    text = re.sub(r"^### (.+)$", r"<h3 style='color:#1e3a5f;margin:16px 0 8px;font-size:18px'>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$",  r"<h2 style='color:#1e3a5f;margin:18px 0 10px;font-size:22px'>\1</h2>", text, flags=re.M)
    text = re.sub(r"^# (.+)$",   r"<h1 style='color:#1e3a5f;margin:20px 0 12px;font-size:26px'>\1</h1>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"^---$", r"<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0'>", text, flags=re.M)
    text = re.sub(r"^\*(.+)\*$", r"<em style='color:#6b7280;font-size:13px'>\1</em>", text, flags=re.M)
    text = text.replace("\n", "<br>")
    return text

def send_notification_email(subject, doc_url, date_str, ceo_summary):
    """Send a short notification email with link to Google Doc."""
    if not EMAIL_RECIPIENT:
        print("[Email] Skipped - no EMAIL_RECIPIENT")
        return
    gmail = get_gmail_service()
    if not gmail:
        print("[Email] Skipped - Gmail auth failed")
        return

    # Short summary = first 500 chars of CEO report
    short = ceo_summary[:500] + "..." if len(ceo_summary) > 500 else ceo_summary

    html_body = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;font-size:15px;color:#111;line-height:1.7">
<div style="background:#1e3a5f;color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px">
  <div style="font-size:20px;font-weight:bold">Investment Intelligence Hub</div>
  <div style="font-size:13px;opacity:0.85;margin-top:4px">{date_str} | S&P500 + Bitcoin</div>
</div>

<p style="font-size:16px;font-weight:bold;color:#1e3a5f">รายงานการลงทุนประจำสัปดาห์พร้อมแล้ว</p>

<div style="background:#f8fafc;border-left:4px solid #1e3a5f;padding:12px 16px;margin:12px 0;border-radius:0 6px 6px 0;font-size:14px;color:#374151">
{short.replace(chr(10), "<br>")}
</div>

<div style="text-align:center;margin:20px 0">
  <a href="{doc_url}" style="background:#1e3a5f;color:white;padding:12px 32px;border-radius:6px;text-decoration:none;font-size:16px;font-weight:bold;display:inline-block">
    เปิดรายงานฉบับเต็ม
  </a>
</div>

<p style="font-size:13px;color:#6b7280">วิเคราะห์โดย AI 7 Agents: News, Broker, Technical, Macro, Portfolio, Elite Council, CEO</p>
<div style="font-size:11px;color:#9ca3af;margin-top:12px;border-top:1px solid #e5e7eb;padding-top:10px">
เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน</div>
</div>"""

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER or "me"
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(email.mime.text.MIMEText(short, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))
    raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        gmail.users().messages().send(userId="me", body={"raw": raw_msg}).execute()
        size_kb = len(html_body.encode()) / 1024
        print(f"[Email] Notification sent -> {EMAIL_RECIPIENT} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"[Email] Gmail ERROR: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    print(f"\n{'='*55}")
    print(f"Investment Hub - {bkk.strftime('%Y-%m-%d %H:%M')} Bangkok")
    print(f"{'='*55}")

    # Phase 1: Agents
    print("\nPhase 1: Agent Research...")
    reports = {}
    for key in AGENTS:
        reports[key] = run_agent(key)
        time.sleep(15)  # avoid rate limit

    date_str = bkk.strftime("%Y-%m-%d")
    date_str_th = bkk.strftime("%d/%m/%Y")

    # Phase 2: CEO
    print("\nPhase 2: CEO Briefing...")
    ceo_report = call_ceo(reports)

    # Phase 3: Save as Google Docs
    print("\nPhase 3: Saving to Google Docs...")
    doc_url = save_to_gdocs(ceo_report, reports, date_str)

    # Phase 4: Send short notification email
    print("\nPhase 4: Sending notification email...")
    send_notification_email(
        subject=f"Investment Briefing {date_str_th} | S&P500 + Bitcoin พร้อมแล้ว",
        doc_url=doc_url,
        date_str=date_str_th,
        ceo_summary=ceo_report
    )

    print(f"\nAll done!")
    if doc_url:
        print(f"Google Doc: {doc_url}")

if __name__ == "__main__":
    main()
    sys.exit(0)

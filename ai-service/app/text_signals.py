"""
สัญญาณเตือนในข้อความ (SMS / LINE / ข้อความที่ถอดจากสาย) ที่มักพบในการหลอกลวง

ใช้ 2 อย่าง:
  1. normalize_text  -> preprocessing ของโมเดลข้อความ (ถูกอ้างอิงใน pipeline ที่ train แล้ว ห้ามเปลี่ยนชื่อ)
  2. find_signals    -> อธิบายให้ผู้ใช้เห็นว่า "ทำไม" ข้อความนี้น่าสงสัย (แสดงผลคู่กับคะแนนจากโมเดล)
"""
from __future__ import annotations

import re
import unicodedata

_URL = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|net|org|co|xyz|top|cc|vip|online|site|link|me|info|shop|club|app)\b\S*)", re.I)
_PHONE = re.compile(r"(?<!\d)0[689]\d[-\s]?\d{3}[-\s]?\d{4}(?!\d)|(?<!\d)0[2-7][-\s]?\d{3}[-\s]?\d{4}(?!\d)")
_MONEY = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:บาท|฿|thb)", re.I)
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """ทำข้อความให้อยู่ในรูปเดียวกัน: ตัวพิมพ์เล็ก, แทน URL/เบอร์/จำนวนเงินด้วย token เดียวกัน"""
    text = unicodedata.normalize("NFC", text or "").lower()
    text = _URL.sub(" <url> ", text)
    text = _PHONE.sub(" <phone> ", text)
    text = _MONEY.sub(" <money> ", text)
    text = re.sub(r"\d+", "0", text)
    return _SPACES.sub(" ", text).strip()


# (รหัส, คำอธิบายภาษาไทยที่แสดงให้ผู้ใช้, regex)
SIGNALS: list[tuple[str, str, re.Pattern]] = [
    ("money_request", "ขอให้โอนเงิน ชำระค่าธรรมเนียม หรือวางมัดจำ",
     re.compile(r"โอน(เงิน)?|ชำระ|มัดจำ|ค่าธรรมเนียม|ค่าดำเนินการ|ค่ามัดจำ|ค่าปรับ|ตรวจสอบเงิน|ยืนยันยอด", re.I)),
    ("authority", "อ้างว่าเป็นเจ้าหน้าที่รัฐหรือหน่วยงานทางการ",
     re.compile(r"ตำรวจ|สภ\.|สน\.|dsi|ดีเอสไอ|ปปง|ป\.ป\.ง|ศาล|อัยการ|สรรพากร|การไฟฟ้า|กฟภ|กฟน|ศุลกากร|กรมที่ดิน|ประกันสังคม|กสทช|ธปท|แบงก์ชาติ|เจ้าหน้าที่", re.I)),
    ("threat", "ข่มขู่ เร่งให้ตัดสินใจเร็ว หรืออ้างว่าคุณทำผิดกฎหมาย",
     re.compile(r"ด่วน|ภายใน\s*0\s*(ชั่วโมง|ชม|นาที|วัน)|ระงับ|อายัด|ดำเนินคดี|หมายจับ|หมายศาล|ผิดกฎหมาย|ฟอกเงิน|บัญชีม้า|ยาเสพติด|ถูกฟ้อง|มีความผิด|ปิดบัญชี|ตัดไฟ", re.I)),
    ("credentials", "ขอ OTP รหัสผ่าน เลขบัตร หรือข้อมูลบัญชี",
     re.compile(r"otp|รหัส\s*(ผ่าน|ยืนยัน|atm|pin)|pin|เลขบัตร(ประชาชน)?|เลขหลังบัตร|เลขบัญชี|cvv|ข้อมูลบัตร|ยืนยันตัวตน", re.I)),
    ("link", "มีลิงก์ให้กด ซึ่งอาจเป็นเว็บปลอม",
     re.compile(r"<url>|กดลิงก์|คลิกลิงก์|คลิก|กดที่นี่|ลิ้งค์|ลิงค์", re.I)),
    ("move_chat", "ชวนให้แอด LINE หรือย้ายไปคุยช่องทางอื่น",
     re.compile(r"แอด\s*ไลน์|add\s*line|ไลน์\s*id|line\s*id|แอดไลน์|ทักไลน์|@\w{3,}|แอดมิน", re.I)),
    ("too_good", "เสนอผลตอบแทน รายได้ หรือเงินคืนที่สูงเกินจริง",
     re.compile(r"กำไร|ผลตอบแทน|ปันผล|รายได้\s*(วันละ|ต่อวัน|เสริม)|ได้เงินจริง|ไม่ต้องลงทุน|ลงทุนน้อย|รับเงินคืน|เงินคืน|ถอนได้จริง|การันตี", re.I)),
    ("prize", "แจ้งว่าได้รับรางวัลหรือสิทธิพิเศษโดยไม่ได้ร่วมกิจกรรม",
     re.compile(r"ยินดีด้วย|ได้รับรางวัล|ถูกรางวัล|ผู้โชคดี|สิทธิ์พิเศษ|สิทธิพิเศษ|รับฟรี|แจกฟรี", re.I)),
    ("loan", "เสนอสินเชื่อง่ายเกินจริง",
     re.compile(r"สินเชื่อ|เงินกู้|กู้เงิน|ไม่เช็ค\s*บูโร|ไม่เช็คบูโร|อนุมัติไว|อนุมัติทันที|ไม่ต้องค้ำ", re.I)),
    ("remote_app", "ให้ติดตั้งแอปหรือแชร์หน้าจอ",
     re.compile(r"ดาวน์โหลด\s*แอป|ติดตั้ง\s*แอป|โหลดแอป|\.apk|anydesk|teamviewer|แชร์หน้าจอ|รีโมท", re.I)),
    ("parcel", "อ้างเรื่องพัสดุตกค้างหรือของผิดกฎหมาย",
     re.compile(r"พัสดุ|ศุลกากร|ไปรษณีย์|ตกค้าง|ส่งของ|kerry|flash|dhl|ems", re.I)),
]


def find_signals(text: str) -> list[dict]:
    norm = normalize_text(text)
    found = []
    for code, label, pattern in SIGNALS:
        m = pattern.search(norm) or pattern.search(text or "")
        if m:
            match = m.group(0).strip()
            if match == "<url>":  # แสดงลิงก์จริงจากข้อความเดิม ไม่ใช่ token ที่ normalize แล้ว
                url = _URL.search(text or "")
                match = url.group(0) if url else "ลิงก์"
            found.append({"code": code, "label": label, "match": match[:60]})
    return found

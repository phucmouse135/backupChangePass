import imaplib
import email
from email.header import decode_header
import re
import html

# --- CẤU HÌNH ---
IMAP_SERVER = "imap.gmx.net"
IMAP_PORT = 993

# Các từ khóa xác nhận đổi pass thành công (Final Success)
CONFIRM_KEYWORDS = [
    "password has been changed",
    "password changed",
    "mật khẩu đã được thay đổi",
    "bạn vừa thay đổi mật khẩu",
    "reset your password", # Đôi khi tiêu đề này cũng tính là thành công tùy ngữ cảnh
]

# Các từ khóa của mail yêu cầu reset (Dùng để moi UID)
RESET_KEYWORDS = [
    "reset your password",
    "get back on instagram",
    "recover your password",
    "đặt lại mật khẩu",
    "truy cập lại vào instagram"
]

SENDER_FILTER = "Instagram"

def _decode_mime_str(s):
    if not s: return ""
    decoded_list = decode_header(s)
    result = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            if encoding:
                try: result += content.decode(encoding)
                except: result += content.decode("utf-8", errors="ignore")
            else: result += content.decode("utf-8", errors="ignore")
        else: result += str(content)
    return result

def _get_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get("Content-Disposition"))
            if "attachment" not in cdispo:
                try:
                    payload = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    if ctype == "text/html":
                        # Ưu tiên lấy HTML để extract UID từ link ẩn
                        return payload.lower() 
                    body += payload
                except: pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except: pass
    return body.lower()

def _extract_uid(text):
    """
    Trích xuất UID Instagram từ nội dung mail.
    Pattern thường thấy:
    - Link: instagram.com/_n/some_action?uid=12345678
    - Footer: 'This message was sent to ... (uid: 12345678)'
    """
    # Regex 1: Tìm uid=123... trong link
    m1 = re.search(r'uid=([0-9]{6,20})', text)
    if m1: return m1.group(1)
    
    # Regex 2: Tìm pattern /_n/ ... &uid=...
    # (Instagram mail link format)
    
    # Regex 3: Tìm số thuần túy nằm cạnh từ khóa 'user' hoặc trong ngoặc
    # (Cách này rủi ro hơn, nên ưu tiên link trước)
    
    return None

def execute_step4(driver=None, email_addr="", password="", ig_user=None):
    host = IMAP_SERVER
    if email_addr.endswith("@gmx.com"): host = "imap.gmx.com"
    elif email_addr.endswith("@mail.com"): host = "imap.mail.com"

    print(f"-> [IMAP] Checking: {email_addr}...")
    
    try:
        mail = imaplib.IMAP4_SSL(host, IMAP_PORT)
        mail.login(email_addr, password)
        mail.select("INBOX")
        
        # --- GIAI ĐOẠN 1: TÌM MAIL RESET ĐỂ LẤY UID ---
        # Tìm TẤT CẢ mail từ Instagram (kể cả đã đọc)
        status, messages = mail.search(None, f'(FROM "{SENDER_FILTER}")')
        
        if status != "OK" or not messages[0]:
             # Thử tìm rộng hơn
            status, messages = mail.search(None, 'ALL')
            
        all_ids = messages[0].split()
        # Lấy 10 mail gần nhất để quét
        recent_ids = all_ids[-10:] if len(all_ids) > 10 else all_ids
        
        target_uid = None
        
        # Quét ngược từ mới nhất về cũ
        print(f"   Scanning {len(recent_ids)} mails for UID...")
        for mid in reversed(recent_ids):
            try:
                # Fetch full body để regex
                res, data = mail.fetch(mid, "(BODY.PEEK[])")
                msg = email.message_from_bytes(data[0][1])
                subject = _decode_mime_str(msg["Subject"]).lower()
                body = _get_email_body(msg)
                
                # Check xem có phải mail Reset/GetBack không
                is_reset_mail = any(kw in subject for kw in RESET_KEYWORDS)
                
                if is_reset_mail:
                    # Trích xuất UID
                    extracted = _extract_uid(body)
                    if extracted:
                        target_uid = extracted
                        print(f"   [INFO] Found Reset Mail -> Extracted UID: {target_uid}")
                        break # Đã tìm thấy mail reset mới nhất, dừng tìm UID
            except Exception as e:
                continue

        # Nếu không tìm thấy UID trong mail, dùng ig_user từ input làm fallback
        if not target_uid and ig_user:
            print(f"   [WARN] No UID found in mails. Using input User: {ig_user}")
            target_uid = ig_user
            
        if not target_uid:
            print("   [FAIL] Could not extract UID and no User provided.")
            mail.close(); mail.logout()
            return "Fail: No UID found"

        # --- GIAI ĐOẠN 2: TÌM MAIL CONFIRM KHỚP UID ---
        print(f"   Verifying success for UID/User: {target_uid}...")
        found_success = False
        
        # Quét lại list mail (ưu tiên mail chưa đọc nếu có, hoặc quét lại list cũ)
        # Vì mail Confirm thường đến SAU mail Reset, nên nó nằm ở top
        for mid in reversed(recent_ids):
            try:
                res, data = mail.fetch(mid, "(BODY.PEEK[])")
                msg = email.message_from_bytes(data[0][1])
                subject = _decode_mime_str(msg["Subject"]).lower()
                body = _get_email_body(msg)
                
                # 1. Phải là mail báo thành công
                is_success_mail = any(kw in subject for kw in CONFIRM_KEYWORDS) or \
                                  any(kw in body for kw in CONFIRM_KEYWORDS)
                                  
                if not is_success_mail:
                    continue

                # 2. Phải chứa UID hoặc User mục tiêu
                # (Instagram mail thường chứa username trong body: "Hi user123, ...")
                if target_uid.lower() in body or target_uid.lower() in subject:
                    print(f"   [SUCCESS] Verified Mail Found for {target_uid}")
                    found_success = True
                    break
                else:
                    # Debug nhẹ: Thấy mail success nhưng ko khớp uid
                    # print(f"   [SKIP] Found success mail but UID mismatch.")
                    pass
                    
            except: continue
            
        mail.close()
        mail.logout()
        
        return True if found_success else "Fail: No Confirm Mail for UID"

    except Exception as e:
        print(f"   [ERROR] {e}")
        return str(e)
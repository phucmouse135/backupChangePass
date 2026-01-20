import imaplib
import email
from email.header import decode_header
import re
import time

# --- CẤU HÌNH SERVER ---
IMAP_PORT = 993
GMX_HOST = "imap.gmx.net"
MAIL_COM_HOST = "imap.mail.com"

# Từ khóa tìm mail Reset (để lấy User/UID)
RESET_KEYWORDS = [
    "reset your password",
    "get back on instagram",
    "recover your password",
    "đặt lại mật khẩu",
    "truy cập lại vào instagram",
    "log in as" # Đôi khi mail "We've made it easy to log in as..."
]

# Từ khóa xác nhận thành công (để báo Live)
CONFIRM_KEYWORDS = [
    "password has been changed",
    "password changed",
    "your instagram password has been changed",
    "mật khẩu đã được thay đổi",
    "bạn vừa thay đổi mật khẩu"
]

SENDER_FILTER = "Instagram"

def _decode_mime_str(s):
    """Giải mã tiêu đề email"""
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
    """Lấy nội dung HTML/Text của email"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get("Content-Disposition"))
            if "attachment" not in cdispo:
                try:
                    payload = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    if ctype == "text/html":
                        return payload # Trả về raw HTML/Text để regex
                    body += payload
                except: pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except: pass
    return body

def _extract_candidates_from_body(text):
    """
    Trích xuất Username hoặc UID từ nội dung mail.
    Trả về set các giá trị tìm được.
    """
    candidates = set()
    
    # 1. Regex Username: "Hi zjsigjywkg,"
    # Bắt chữ "Hi ", sau đó là cụm ký tự không chứa dấu phẩy/khoảng trắng
    m_user = re.search(r'Hi\s+([a-zA-Z0-9_.]+),', text, re.IGNORECASE)
    if m_user:
        candidates.add(m_user.group(1).lower())

    # 2. Regex UID từ link: uid=123456...
    m_uid = re.search(r'uid=([0-9]{6,25})', text)
    if m_uid:
        candidates.add(m_uid.group(1))

    # 3. Regex UID từ footer: (uid: 123456)
    m_footer = re.search(r'\(uid:\s*(\d{6,25})\)', text)
    if m_footer:
        candidates.add(m_footer.group(1))
        
    return candidates

def verify_account_live(email_login, password, ig_user_fallback=None):
    """
    Quy trình check mới:
    1. Login IMAP.
    2. Quét mail Reset -> Lưu danh sách User/UID (candidates).
    3. Tìm mail Success MỚI NHẤT.
    4. Nếu mail Success đó chứa 1 trong các candidates -> SUCCESS.
    """
    host = GMX_HOST
    if "@mail.com" in email_login:
        host = MAIL_COM_HOST
    
    try:
        # 1. KẾT NỐI
        mail = imaplib.IMAP4_SSL(host, IMAP_PORT)
        try:
            mail.login(email_login, password)
        except imaplib.IMAP4.error:
            return "Login Mail Failed"
            
        mail.select("INBOX")
        
        # 2. LẤY MAIL
        status, messages = mail.search(None, f'(FROM "{SENDER_FILTER}")')
        if status != "OK" or not messages[0]:
            status, messages = mail.search(None, 'ALL')
            
        if not messages[0]:
            mail.logout()
            return "Mail Empty (No Insta mail)"

        mail_ids = messages[0].split()
        # Quét sâu hơn (20 mail) để chắc chắn bắt được mail Reset cũ
        recent_ids = mail_ids[-20:] if len(mail_ids) > 20 else mail_ids
        
        candidate_users = set()
        if ig_user_fallback:
            candidate_users.add(ig_user_fallback.lower())
        
        # --- GIAI ĐOẠN 1: THU THẬP USER TỪ CÁC MAIL RESET ---
        # Quét tất cả mail trong danh sách recent
        for mid in reversed(recent_ids):
            try:
                res, data = mail.fetch(mid, "(BODY.PEEK[])") # PEEK để không đánh dấu đã đọc
                msg = email.message_from_bytes(data[0][1])
                subject = _decode_mime_str(msg["Subject"]).lower()
                
                # Nếu là mail Reset/Recover
                if any(kw in subject for kw in RESET_KEYWORDS):
                    body = _get_email_body(msg)
                    # Trích xuất user/uid
                    found = _extract_candidates_from_body(body)
                    if found:
                        candidate_users.update(found)
            except Exception:
                continue
        
        if not candidate_users:
            mail.logout()
            return "Fail: No User/UID found in Reset mails"

        # print(f"   [INFO] Candidates found: {candidate_users}")

        # --- GIAI ĐOẠN 2: CHECK MAIL SUCCESS MỚI NHẤT ---
        # Tìm mail Confirm mới nhất trùng khớp với bất kỳ candidate nào
        is_live = False
        final_user = ""
        
        for mid in reversed(recent_ids):
            try:
                res, data = mail.fetch(mid, "(BODY.PEEK[])")
                msg = email.message_from_bytes(data[0][1])
                subject = _decode_mime_str(msg["Subject"]).lower()
                
                # Kiểm tra xem có phải mail Success không
                if any(kw in subject for kw in CONFIRM_KEYWORDS):
                    body = _get_email_body(msg).lower()
                    
                    # Kiểm tra xem mail này có chứa bất kỳ candidate nào không
                    for user in candidate_users:
                        if user in body or user in subject:
                            is_live = True
                            final_user = user
                            break
                    
                    if is_live:
                        # Tìm thấy mail confirm mới nhất khớp logic -> Chốt đơn
                        break
            except Exception:
                continue

        mail.close()
        mail.logout()
        
        if is_live:
            # Trả về success kèm tên user tìm được để update UI (nếu cần)
            return f"success|USER={final_user}" 
        else:
            return "Fail: Latest Confirm Mail mismatch"

    except Exception as e:
        return f"Error: {str(e)}"
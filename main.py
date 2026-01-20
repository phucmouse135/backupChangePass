import os
from dataclasses import dataclass
from mail_handler import verify_account_live

INPUT_FILE = "input.txt"

@dataclass
class Account:
    uid: str
    mail_login: str
    ig_user: str
    mail_pass: str

def process_account(account, headless=True, status_cb=None):
    try:
        if status_cb:
            status_cb("Checking Live (IMAP)...")

        # Gọi hàm check
        result = verify_account_live(
            email_login=account.mail_login,
            password=account.mail_pass,
            ig_user_fallback=account.ig_user
        )

        # Xử lý kết quả trả về
        if result.startswith("success"):
            # Nếu kết quả có dạng "success|USER=abc", ta có thể lấy abc ra
            # Nhưng ở đây ta chỉ cần trả về "success" để GUI tô xanh
            # Hoặc trả nguyên chuỗi để GUI tự update cột User (xem phần GUI bên dưới)
            return result 
            
        return result
    
    except Exception as e:
        return f"System Error: {str(e)}"

def main():
    # Test CLI
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:
        p = line.strip().split("\t")
        if len(p) < 7: continue
        acc = Account(uid=p[0], mail_login=p[5], ig_user=p[2], mail_pass=p[6])
        print(f"Checking {acc.mail_login} -> {process_account(acc)}")

if __name__ == "__main__":
    main()
import os
from dotenv import load_dotenv

# ✅ تحميل المتغيرات من ملف .env إن وجد
load_dotenv()

# 🧩 إعدادات أساسية
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "changeme")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "443"))

# 🖥️ إعدادات القالب الافتراضي للأنظمة
TEMPLATE_NAME = os.getenv("TEMPLATE_NAME", "BaseWin2022")
TEMPLATE_ADMIN_PASSWORD = os.getenv("TEMPLATE_ADMIN_PASSWORD", "")

# 🌐 إعدادات الـ DDNS
DDNS_HOST = os.getenv("DDNS_HOST", "dzhosing.serveftp.com")

# ⚙️ مسار VBoxManage
VBOXMANAGE = os.getenv("VBOXMANAGE", r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe")

# 💾 إعدادات الموارد الافتراضية
DEFAULT_MEMORY_MB = int(os.getenv("DEFAULT_MEMORY_MB", "4096"))
DEFAULT_CPUS = int(os.getenv("DEFAULT_CPUS", "2"))
DEFAULT_DISK_MB = int(os.getenv("DEFAULT_DISK_MB", "25600"))

# ✅ (اختياري) طباعة للتأكد أن القيم تُقرأ بشكل صحيح عند التشغيل
if __name__ == "__main__":
    print("=== Config Debug ===")
    print("ADMIN_USER:", ADMIN_USER)
    print("HOST:", HOST)
    print("PORT:", PORT)
    print("TEMPLATE_NAME:", TEMPLATE_NAME)
    print("DDNS_HOST:", DDNS_HOST)

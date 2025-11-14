import sqlite3, os, datetime

DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "vms.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ✅ جدول الآلات الافتراضية (vms)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vms (
        name TEXT PRIMARY KEY,
        serial TEXT,
        owner TEXT,
        user TEXT,
        password TEXT,
        ip TEXT,
        status TEXT,
        memory INT,
        cpus INT,
        disk INT,
        connect TEXT,
        port INT,
        service_ports TEXT,
        activated INT DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT
    )
    """)

    # ✅ جدول المستخدمين (الزبائن)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        serial TEXT,  -- ✅ لحفظ السيريال المرتبط بالمستخدم بعد التفعيل
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# 🔹 أداة اتصال أساسية
def _conn():
    return sqlite3.connect(DB_PATH)


# ✅ إدخال آلة جديدة
def insert_vm(name, serial, owner, user, password, ip, status,
              memory, cpus, disk, connect=None, port=None, service_ports=None,
              created_at=None, expires_at=None):
    conn = _conn()
    c = conn.cursor()
    c.execute("""
        REPLACE INTO vms
        (name, serial, owner, user, password, ip, status, memory, cpus, disk,
         connect, port, service_ports, created_at, expires_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (name, serial, owner, user, password, ip, status, memory, cpus, disk,
          connect, port, service_ports, created_at, expires_at))
    conn.commit()
    conn.close()


# ✅ عرض جميع الآلات
def list_vms():
    conn = _conn()
    c = conn.cursor()
    c.execute("""
        SELECT name, serial, owner, user, password, ip, status, memory, cpus, disk,
               connect, port, service_ports, activated, created_at, expires_at
        FROM vms
    """)
    rows = c.fetchall()
    conn.close()

    vms = []
    for r in rows:
        vms.append({
            'name': r[0],
            'serial': r[1],
            'owner': r[2],
            'user': r[3],
            'password': r[4],
            'ip': r[5],
            'status': r[6],
            'memory': r[7],
            'cpus': r[8],
            'disk': r[9],
            'connect': r[10],
            'port': r[11],
            'service_ports': r[12].split(',') if r[12] else [],
            'activated': r[13],
            'created_at': r[14],
            'expires_at': r[15]
        })
    return vms


# ✅ البحث بالـ serial
def vm_by_serial(serial):
    conn = _conn()
    c = conn.cursor()
    c.execute("""
        SELECT name, serial, owner, user, password, ip, status, memory, cpus, disk,
               connect, port, service_ports, activated, created_at, expires_at
        FROM vms WHERE serial=?
    """, (serial,))
    r = c.fetchone()
    conn.close()

    if not r:
        return None

    return {
        'name': r[0],
        'serial': r[1],
        'owner': r[2],
        'user': r[3],
        'password': r[4],
        'ip': r[5],
        'status': r[6],
        'memory': r[7],
        'cpus': r[8],
        'disk': r[9],
        'connect': r[10],
        'port': r[11],
        'service_ports': r[12].split(',') if r[12] else [],
        'activated': r[13],
        'created_at': r[14],
        'expires_at': r[15]
    }


# ✅ البحث بالاسم
def vm_by_name(name):
    conn = _conn()
    c = conn.cursor()
    c.execute("""
        SELECT name, serial, owner, user, password, ip, status, memory, cpus, disk,
               connect, port, service_ports, activated, created_at, expires_at
        FROM vms WHERE name=?
    """, (name,))
    r = c.fetchone()
    conn.close()

    if not r:
        return None

    return {
        'name': r[0],
        'serial': r[1],
        'owner': r[2],
        'user': r[3],
        'password': r[4],
        'ip': r[5],
        'status': r[6],
        'memory': r[7],
        'cpus': r[8],
        'disk': r[9],
        'connect': r[10],
        'port': r[11],
        'service_ports': r[12].split(',') if r[12] else [],
        'activated': r[13],
        'created_at': r[14],
        'expires_at': r[15]
    }


# ✅ تحديث الحقول
def update_vm_fields(name, **kwargs):
    keys = []
    vals = []
    for k, v in kwargs.items():
        keys.append(f"{k}=?")
        vals.append(v)
    vals.append(name)
    conn = _conn()
    c = conn.cursor()
    c.execute(f"UPDATE vms SET {','.join(keys)} WHERE name=?", vals)
    conn.commit()
    conn.close()


# ✅ حذف آلة
def delete_vm(name):
    conn = _conn()
    c = conn.cursor()
    c.execute('DELETE FROM vms WHERE name=?', (name,))
    conn.commit()
    conn.close()


# ✅ تفعيل آلة عبر السيريال
def activate_vm_by_serial(serial):
    conn = _conn()
    c = conn.cursor()
    c.execute('UPDATE vms SET activated=1 WHERE serial=?', (serial,))
    conn.commit()
    conn.close()


# ✅ إنشاء مستخدم جديد
def create_user(email, password):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
    conn.commit()
    conn.close()


# ✅ جلب مستخدم عبر البريد الإلكتروني
def get_user(email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row


# ✅ تحديث السيريال للمستخدم بعد أول تفعيل
def update_user_serial(email, serial):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET serial=? WHERE email=?", (serial, email))
    conn.commit()
    conn.close()


# ✅ تجديد اشتراك العميل (تحديث تاريخ الانتهاء)
def renew_vm(serial, extra_days=30):
    """
    تمديد صلاحية السيريال بعدد الأيام المحددة (افتراضياً 30 يومًا)
    """
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT expires_at FROM vms WHERE serial = ?", (serial,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    try:
        now = datetime.datetime.utcnow()
        if row[0]:
            current_exp = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            new_exp = current_exp + datetime.timedelta(days=extra_days)
        else:
            new_exp = now + datetime.timedelta(days=extra_days)

        new_exp_str = new_exp.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE vms SET expires_at = ? WHERE serial = ?", (new_exp_str, serial))
        conn.commit()
        conn.close()
        print(f"[OK] ✅ تم تمديد صلاحية الآلة {serial} حتى {new_exp_str}")
        return True

    except Exception as e:
        print(f"[ERR] أثناء تجديد الاشتراك: {e}")
        conn.close()
        return False

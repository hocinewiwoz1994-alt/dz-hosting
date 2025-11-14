from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from db import create_user, get_user
import secrets, time, os
import config

# 🧩 إصلاح مهم جدًا لمسار قاعدة البيانات عند تشغيل SSL
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from db import init_db, list_vms, insert_vm, update_vm_fields, vm_by_serial, vm_by_name, delete_vm, activate_vm_by_serial

import os
VBOX_API = os.getenv("VBOX_API")

import threading
from db import list_vms, update_vm_fields
import datetime

app = Flask(__name__)

from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

AUTO_POWER_OFF = True

# ⬇️⬇️ رابر (طبقة) تتعامل مع VBOX_API بدل vbox_helper_full ⬇️⬇️
import logging, sys

class VBoxRemote:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token  # ← إضافة التوكن

    def _headers(self):
        """هيدر التوكن إذا موجود"""
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _post(self, path, payload=None, timeout=30):
        url = f"{self.base_url}{path}"
        try:
            r = requests.post(
                url,
                json=payload or {},
                headers=self._headers(),  # ← إضافة الهيدر
                timeout=timeout
            )
            r.raise_for_status()
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": "bad_json", "raw": r.text}
        except Exception as e:
            print(f"[VBOX_API POST ERROR] {url} -> {e}")
            return {"ok": False, "error": str(e)}

    def _get(self, path, params=None, timeout=30):
        url = f"{self.base_url}{path}"
        try:
            r = requests.get(
                url,
                params=params or {},
                headers=self._headers(),  # ← إضافة الهيدر
                timeout=timeout
            )
            r.raise_for_status()
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": "bad_json", "raw": r.text}
        except Exception as e:
            print(f"[VBOX_API GET ERROR] {url} -> {e}")
            return {"ok": False, "error": str(e)}

    # === إنشاء VM عبر الـ API ===
    def create_vm_async(self, name, owner_email=None, memory_mb=None, cpus=None, disk_mb=None):
        payload = {
            "name": name,
            "owner_email": owner_email,
            "memory_mb": memory_mb,
            "cpus": cpus,
            "disk_mb": disk_mb,
        }
        resp = self._post("/api/vm/create", payload)
        return resp

    def start_vm(self, name):
        return self._post("/api/vm/action", {"name": name, "action": "start"})

    def poweroff_vm(self, name):
        return self._post("/api/vm/action", {"name": name, "action": "stop"})

    def reset_vm(self, name):
        return self._post("/api/vm/action", {"name": name, "action": "reset"})

    def delete_vm_full(self, name):
        return self._post("/api/vm/action", {"name": name, "action": "delete"})

    def get_vm_status(self, name):
        resp = self._get("/api/vm/status", {"name": name})
        return resp.get("status", "unknown")

    def get_ip(self, name):
        resp = self._get("/api/vm/status", {"name": name})
        return resp.get("ip") or resp.get("ip_internal") or "-"

    def change_vm_password(self, name, current_pw, new_pw):
        resp = self._post("/api/vm/change_password", {
            "name": name,
            "current_password": current_pw,
            "new_password": new_pw
        })
        return bool(resp.get("ok"))

    def renew_vm_expiry(self, name, days=35):
        resp = self._post("/api/vm/renew", {
            "name": name,
            "days": days
        })
        return bool(resp.get("ok"))

    def update_resources(self, name, memory_mb, cpus):
        resp = self._post("/api/vm/update_resources", {
            "name": name,
            "memory_mb": int(memory_mb),
            "cpus": int(cpus)
        })
        return bool(resp.get("ok"))

# هذا هو "vbox" الجديد لكن يكلّم API
vbox = VBoxRemote(VBOX_API, token=os.getenv("API_TOKEN"))

# فعّل اللوقينغ للكونسول
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# خَلّي فلاسـك يطبع أخطاء الجنچا بدل ما يسكت
app.config["PROPAGATE_EXCEPTIONS"] = True
app.config["TEMPLATES_AUTO_RELOAD"] = True

# هاندلر عام يطبع أي استثناء مع الـ Traceback
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    print("\n⚠️⚠️⚠️ حدث خطأ داخلي ⚠️⚠️⚠️")
    traceback.print_exc()
    return f"❌ خطأ داخلي في السيرفر: {e}", 500

# (اختياري) اطبع كل طلب يدخل مع معلومات الجلسة
@app.before_request
def _dbg_req():
    try:
        print(f"[REQ] {request.method} {request.path}  session.is_admin={session.get('is_admin')}")
    except Exception:
        pass

import datetime

# ✅ فلتر مخصص لتحويل النص إلى datetime (مع جعلها UTC aware)
@app.template_filter("todatetime")
def todatetime(value):
    """يحاول تحويل نص إلى كائن datetime مع منطقة زمنية UTC"""
    if not value:
        return None
    try:
        dt = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=datetime.timezone.utc)  # ← تصحيح أساسي هنا
    except Exception:
        return None

# ✅ دالة inject_now() لإتاحة استخدام now() داخل Jinja (بمنطقة زمنية UTC)
@app.context_processor
def inject_now():
    return {"now": lambda: datetime.datetime.now(datetime.timezone.utc)}

app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(16))
init_db()

def require_admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

@app.get("/admin/login")
def admin_login():
    return render_template("admin.html", login=True, vms=[])

@app.post("/admin/login")
def admin_login_post():
    u = request.form.get("user")
    p = request.form.get("pass")
    if u == config.ADMIN_USER and p == config.ADMIN_PASS:
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))
    return render_template("admin.html", login=True, error="Bad credentials")

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.get("/admin")
def admin_dashboard():
    if require_admin():
        return require_admin()
    try:
        vms = list_vms()
        print(f"[DEBUG] ✅ عدد الأجهزة المسترجعة من قاعدة البيانات: {len(vms)}")
    except Exception as e:
        import traceback
        print("[ERROR] فشل أثناء جلب البيانات من قاعدة البيانات:")
        traceback.print_exc()
        return "❌ خطأ أثناء قراءة البيانات من قاعدة البيانات. تحقق من الكونسول.", 500

    try:
        print(f"[DEBUG] 🧩 عرض القالب admin.html باستخدام TEMPLATE_NAME={config.TEMPLATE_NAME}")
        return render_template("admin.html", login=False, vms=vms, template_name=config.TEMPLATE_NAME, config=config)
    except Exception as e:
        import traceback
        print("[ERROR] ⚠️ فشل أثناء عرض القالب admin.html:")
        traceback.print_exc()
        return "❌ خطأ أثناء عرض القالب admin.html. تحقق من الكونسول.", 500

@app.post("/admin/create")
def admin_create_vm():
    if require_admin(): return require_admin()

    unique_id = int(time.time())
    name = f"Dz_Hosting-{unique_id}"

    owner = request.form.get("owner_email", "").strip()

    try:
        mem = int(request.form.get("memory_mb", config.DEFAULT_MEMORY_MB))
    except Exception:
        mem = config.DEFAULT_MEMORY_MB

    try:
        cpus = int(request.form.get("cpus", config.DEFAULT_CPUS))
    except Exception:
        cpus = config.DEFAULT_CPUS

    try:
        disk = int(request.form.get("disk_mb", config.DEFAULT_DISK_MB))
    except Exception:
        disk = config.DEFAULT_DISK_MB

    serial = secrets.token_hex(8).upper()
    user = "Administrator"
    temp_pw = secrets.token_urlsafe(10)[:12]

    # ✅ إنشاء VM عبر API واسترجاع معلوماتها بما فيها created_at و expires_at
    vinfo = vbox.create_vm_async(
        name,
        owner_email=owner,
        memory_mb=mem,
        cpus=cpus,
        disk_mb=disk
    )

    try:
        # ✅ تخزين البيانات مع الحقول الجديدة
        insert_vm(
            name, serial, owner, user, temp_pw, "-", "creating",
            mem, cpus, disk,
            connect=vinfo.get('connect'),
            port=vinfo.get('port'),
            service_ports=','.join(map(str, vinfo.get('service_ports', []))) if vinfo.get('service_ports') else None,
            created_at=vinfo.get('created_at'),
            expires_at=vinfo.get('expires_at')
        )
    except TypeError:
        # fallback للنسخ القديمة
        insert_vm(name, serial, owner, user, temp_pw, "-", "creating", mem, cpus, disk)
        update_vm_fields(
            name,
            connect=vinfo.get('connect'),
            port=vinfo.get('port'),
            created_at=vinfo.get('created_at'),
            expires_at=vinfo.get('expires_at')
        )

    return jsonify({"ok": True, "name": name}), 202

@app.post("/admin/activate")
def admin_activate():
    if require_admin(): return require_admin()
    serial = request.form.get("serial")
    activate_vm_by_serial(serial)
    return redirect(url_for("admin_dashboard"))

@app.get("/")
def home():
    # ✅ تحقق من أن المستخدم مسجل الدخول
    if not session.get("user_email"):
        return redirect(url_for("login_page"))

    # 🔹 استخدم السيريال من الرابط أو من الجلسة (session)
    serial = request.args.get("serial", "").strip() or session.get("serial")

    # 🔸 إذا لم يكن موجود → عرض صفحة الإدخال
    if not serial:
        return render_template("customer.html", vm=None, error=None)

    vm = vm_by_serial(serial)
    if not vm:
        session.pop("serial", None)  # إزالة السيريال غير الصحيح من الجلسة
        return render_template("customer.html", vm=None, error="❌ الرقم التسلسلي غير موجود.")

    # ✅ حفظ السيريال في الجلسة بعد التحقق
    session["serial"] = serial
    from db import update_user_serial
    update_user_serial(session["user_email"], serial)

    # ✅ تحقق من حالة التفعيل
    if not vm["activated"]:
        return render_template("customer.html", vm=None, error="⚠️ هذه الآلة لم تُفعّل بعد. تواصل مع الأدمن.")

    # ✅ تحقق من صلاحية السيريال (انتهاء الاشتراك والتحذيرات)
    now = datetime.datetime.now(datetime.timezone.utc)

    if vm.get("expires_at"):
        try:
            exp_date = datetime.datetime.strptime(vm["expires_at"], "%Y-%m-%d %H:%M:%S")
            days_left = (exp_date - now).days

            # 🟢 الحالة الطبيعية
            if days_left > 5:
                return render_template("customer.html", vm=vm, error=None)

            # 🟡 تحذير أول (باقي 5 إلى 3 أيام)
            elif 3 < days_left <= 5:
                warning = f"⚠️ تبقّى {days_left} أيام على انتهاء اشتراكك. يُرجى التجديد قريبًا لتجنّب الإيقاف."
                return render_template("customer.html", vm=vm, error=warning)

            # 🟠 تحذير قوي (باقي 3 أيام أو أقل)
            elif 0 <= days_left <= 3:
                warning = f"⏳ اشتراكك سينتهي خلال {days_left} أيام! سيتم إيقاف الآلة تلقائيًا بعد ذلك."
                return render_template("customer.html", vm=vm, error=warning)

            # 🔴 الاشتراك منتهي منذ أقل من 3 أيام
            elif -3 <= days_left < 0:
                session.pop("serial", None)  # إزالة السيريال لانتهائه
                return render_template("customer.html", vm=None, error="❌ انتهت صلاحية اشتراكك. يرجى التجديد لاستعادة الوصول.")

            # 🚫 منتهي منذ أكثر من 3 أيام → إيقاف فعلي للآلة
            elif days_left < -3:
                vbox.poweroff_vm(vm["name"])
                update_vm_fields(vm["name"], status="expired")
                session.pop("serial", None)
                return render_template("customer.html", vm=None, error="⏰ انتهت صلاحية هذه الآلة وتم إيقافها تلقائيًا.")

        except Exception as e:
            print(f"[WARN] خطأ في قراءة expires_at للآلة {vm['name']}: {e}")

    # ✅ عرض تفاصيل الآلة (دون طلب السيريال مجددًا)
    return render_template("customer.html", vm=vm, error=None)

@app.get("/register")
def register_page():
    return render_template("register.html", error=None)

@app.post("/register")
def register_post():
    email = request.form.get("email").strip().lower()
    password = request.form.get("password")
    confirm = request.form.get("confirm")
    if password != confirm:
        return render_template("register.html", error="كلمتا المرور غير متطابقتين.")
    if get_user(email):
        return render_template("register.html", error="هذا البريد مسجّل مسبقًا.")
    hashed = generate_password_hash(password)
    create_user(email, hashed)
    session["user_email"] = email
    return redirect(url_for("home"))

@app.get("/login")
def login_page():
    return render_template("login.html", error=None)

@app.post("/login")
def login_post():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user(email)
    if not user or not check_password_hash(user[2], password):
        return render_template("login.html", error="بيانات الدخول غير صحيحة.")

    # ✅ حفظ البريد في الجلسة
    session["user_email"] = email

    # ✅ إذا كان المستخدم لديه سيريال محفوظ في قاعدة البيانات، أضفه تلقائيًا للجلسة
    # (نفترض ترتيب الأعمدة: id, email, password, serial)
    if len(user) > 3 and user[3]:
        session["serial"] = user[3]

    # ✅ التوجيه إلى الصفحة الرئيسية مباشرة
    return redirect(url_for("home"))

@app.get("/logout")
def logout_user():
    session.clear()
    return redirect(url_for("login_page"))

@app.post("/customer/action")
def customer_action():
    serial = request.form.get("serial")
    action = request.form.get("action")
    vm = vm_by_serial(serial)
    if not vm:
        return render_template("customer.html", vm=None, error="Serial not found.")
    name = vm["name"]
    if action == "start":
        vbox.start_vm(name)
    elif action == "stop":
        vbox.poweroff_vm(name)
    elif action == "reset":
        vbox.reset_vm(name)
    elif action == "refresh":
        ip = vbox.get_ip(name)
        update_vm_fields(name, ip=ip)
    return render_template("customer.html", vm=vm_by_serial(serial), error=None)

@app.get("/customer/action")
def customer_action_get():
    # إذا المستخدم دخل الرابط مباشرة، نعيده للصفحة الرئيسية بدل 405
    return redirect(url_for("home"))

@app.get("/api/vm_status")
def api_vm_status():
    """
    🔍 Endpoint موحد لجلب حالة الآلة
    يقبل:
      - ?serial=XXXXX  أو
      - ?name=Dz_Hosting-123456
    """
    serial = request.args.get("serial")
    name = request.args.get("name")

    vm = None
    if serial:
        vm = vm_by_serial(serial)
    elif name:
        vm = vm_by_name(name)

    if not vm:
        return jsonify({"ok": False, "status": "not_found"}), 404

    status = vm.get("status", "unknown")
    if status == "running":
        status_text = "🟢 يعمل"
    elif status == "stopped":
        status_text = "🟠 متوقف"
    elif status == "expired":
        status_text = "🔴 منتهي"
    elif status == "creating":
        status_text = "⚪ قيد الإنشاء..."
    else:
        status_text = "⚪ غير معروف"

    # 🔹 أعد كل الحقول المفيدة أيضًا، لتحديث الواجهة عند الجاهزية
    return jsonify({
        "ok": True,
        "status": status,
        "status_text": status_text,
        "name": vm.get("name"),
        "serial": vm.get("serial"),
        "ip": vm.get("ip"),
        "password": vm.get("password"),
        "connect": vm.get("connect"),
        "service_ports": vm.get("service_ports"),
        "owner": vm.get("owner")
    })

@app.post("/change_password")
def change_password():
    serial = request.form.get("serial")
    new_pw = request.form.get("new_password")
    vm = vm_by_serial(serial)
    if not vm:
        return render_template("customer.html", vm=None, error="❌ الرقم التسلسلي غير موجود.")

    # الآن نستخدم كلمة المرور الحقيقية من قاعدة البيانات
    current_pw = vm["password"]

    success = vbox.change_vm_password(vm["name"], current_pw, new_pw)
    if success:
        update_vm_fields(vm["name"], password=new_pw)
        msg = "✅ تم تغيير كلمة المرور داخل النظام بنجاح."
    else:
        msg = "❌ لم يتمكن النظام من تغيير كلمة المرور داخل الآلة."
    return render_template("customer.html", vm=vm_by_serial(serial), error=msg)

@app.post("/api/vm_update")
def api_vm_update():
    data = request.get_json(silent=True)
    if not data or 'name' not in data:
        return jsonify({'ok': False, 'error': 'invalid payload'}), 400
    name = data.get('name')
    ip = data.get('ip_internal') or data.get('ip') or data.get('ip_internal','-')
    status = data.get('status')
    password = data.get('password')
    connect = data.get('connect')
    port = data.get('port')
    service_ports = data.get('service_ports')
    try:
        update_vm_fields(
            name,
            ip=ip,
            status=status,
            password=password,
            connect=connect,
            port=port,
            service_ports=','.join(map(str, service_ports)) if isinstance(service_ports, (list,tuple)) else service_ports
        )
    except Exception as e:
        print('webhook db update failed', e)
    return jsonify({'ok': True})

@app.post("/admin/renew")
def admin_renew_vm():
    # ✅ تحقق من أن الأدمن مسجل الدخول
    if require_admin():
        return require_admin()

    name = request.form.get("name")
    days = request.form.get("days")

    if not name:
        return redirect(url_for("admin_dashboard"))

    try:
        # ✅ تحويل قيمة الأيام (افتراضي 35)
        extra_days = int(days) if days else 35

        # ✅ استدعاء دالة التجديد عبر API
        vbox.renew_vm_expiry(name, days=extra_days)

        msg = f"✅ تم تجديد صلاحية الآلة {name} لمدة {extra_days} يومًا إضافية."
        print(msg)

    except Exception as e:
        msg = f"❌ حدث خطأ أثناء التجديد: {e}"
        print(msg)

    return redirect(url_for("admin_dashboard"))

@app.post("/admin/action")
def admin_action():
    if require_admin():
        return require_admin()

    from db import update_vm_fields, delete_vm

    name = request.form.get("name")
    action = request.form.get("action")

    if not name or not action:
        return redirect(url_for("admin_dashboard"))

    try:
        if action == "start":
            vbox.start_vm(name)
            update_vm_fields(name, status="running")

        elif action == "stop":
            vbox.poweroff_vm(name)
            update_vm_fields(name, status="stopped")

        elif action == "reset":
            vbox.reset_vm(name)
            update_vm_fields(name, status="restarting")

        elif action == "delete":
            vbox.delete_vm_full(name)
            delete_vm(name)
            print(f"[OK] ✅ تم حذف الآلة {name}")

    except Exception as e:
        print(f"[ERR] أثناء تنفيذ الإجراء {action} للآلة {name}: {e}")

    return redirect(url_for("admin_dashboard"))

@app.post("/admin/update_resources")
def admin_update_resources():
    if require_admin():
        return require_admin()

    name = request.form.get("name")
    ram = request.form.get("memory_mb")
    cpus = request.form.get("cpus")

    if not name or not ram or not cpus:
        return redirect(url_for("admin_dashboard"))

    # 🛑 نطلب من الـ API يوقف الـ VM ويعدل الموارد داخله
    vbox.poweroff_vm(name)
    time.sleep(3)

    # 🔧 تعديل الرام والأنوية عبر الـ API
    vbox.update_resources(name, ram, cpus)

    # 📌 تحديث البيانات في قاعدة البيانات
    update_vm_fields(name, memory=ram, cpus=cpus)

    return redirect(url_for("admin_dashboard"))

def auto_power_off_loop():
    """
    🔁 تعمل في الخلفية للتحقق من:
      - تحديث الحالة الفعلية لكل VM (كل 30 ثانية)
      - إيقاف أي آلة انتهى اشتراكها منذ أكثر من 3 أيام (مرة كل 24 ساعة)
    """
    import datetime
    from threading import Lock

    # قفل يمنع تشغيل أكثر من حلقة واحدة بنفس الوقت
    global _auto_off_lock
    try:
        _auto_off_lock
    except NameError:
        _auto_off_lock = Lock()

    if _auto_off_lock.locked():
        print("[AUTO-OFF] ⚠️ العملية تعمل بالفعل، لن أبدأ حلقة جديدة.")
        return

    with _auto_off_lock:
        sync_interval = 30               # ⏱️ تحقق من الحالة كل 30 ثانية
        expire_check_interval = 86400    # ⏱️ فحص الاشتراكات المنتهية كل 24 ساعة
        last_expire_check = 0

        print("[AUTO-OFF] 🚀 تم بدء حلقة المراقبة الخلفية بنجاح.")

        while AUTO_POWER_OFF:
            try:
                vms = list_vms()
                now = datetime.datetime.now(datetime.timezone.utc)

                # 🟢 1️⃣ تحديث الحالة الفعلية لكل VM من خلال الـ API
                for vm in vms:
                    try:
                        real_status = vbox.get_vm_status(vm["name"])
                        if real_status and real_status != vm["status"]:
                            update_vm_fields(vm["name"], status=real_status)
                            print(f"[SYNC] 🔄 تحديث حالة {vm['name']} → {real_status}")
                    except Exception as e:
                        print(f"[WARN] ⚠️ فشل في جلب حالة {vm['name']}: {e}")

                # 🔴 2️⃣ فحص الاشتراكات المنتهية مرة كل 24 ساعة فقط
                if (time.time() - last_expire_check) > expire_check_interval:
                    print("[AUTO-OFF] 🔁 فحص الاشتراكات المنتهية...")
                    expired_count = 0

                    for vm in vms:
                        exp_at = vm.get("expires_at")
                        if not exp_at:
                            continue

                        try:
                            exp_date = datetime.datetime.strptime(
                                exp_at, "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=datetime.timezone.utc)
                        except Exception:
                            continue

                        if (now - exp_date).days > 3 and vm["status"] not in ("expired", "deleted"):
                            print(f"[AUTO-OFF] ⏰ إيقاف {vm['name']} لانتهاء الاشتراك.")
                            try:
                                vbox.poweroff_vm(vm["name"])
                                update_vm_fields(vm["name"], status="expired")
                                expired_count += 1
                            except Exception as e:
                                print(f"[AUTO-OFF] ⚠️ فشل إيقاف {vm['name']}: {e}")

                    print(f"[AUTO-OFF] ✅ تم فحص الاشتراكات المنتهية ({expired_count} متأثرة).")
                    last_expire_check = time.time()

            except Exception as e:
                print(f"[AUTO-OFF ERROR] ❌ خطأ في الحلقة الخلفية: {e}")

            # 💤 انتظر 30 ثانية قبل إعادة الفحص
            time.sleep(sync_interval)

@app.get('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.get("/security.txt")
def security_txt():
    return "Contact: admin@dzhosing.serveftp.com\nPolicy: none", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)



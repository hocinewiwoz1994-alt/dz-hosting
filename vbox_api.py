from flask import Flask, request, jsonify
import subprocess, threading, time, datetime, os, json
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# ================================
#    Load .env token
# ================================
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN") or "DEFAULT_TOKEN"

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


# ================================
#  Token Protection Middleware
# ================================
def require_token():
    token = request.headers.get("X-API-KEY")
    if not token or token != API_TOKEN:
        return False
    return True


# ================================
#     Helper functions
# ================================
def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        out = result.stdout.strip()
        err = result.stderr.strip()
        print("CMD:", " ".join(cmd))
        print("OUT:", out)
        print("ERR:", err)
        return out
    except Exception as e:
        print("CMD ERROR:", e)
        return ""


def vm_exists(name):
    out = run_cmd(["VBoxManage", "list", "vms"])
    return name in out


def get_vm_ip(name):
    out = run_cmd(["VBoxManage", "guestproperty", "get", name, "/VirtualBox/GuestInfo/Net/0/V4/IP"])
    if "Value:" in out:
        return out.split("Value:")[-1].strip()
    return "-"


def get_vm_status(name):
    out = run_cmd(["VBoxManage", "showvminfo", name, "--machinereadable"])
    if "VMState=" in out:
        state = out.split("VMState=")[-1].splitlines()[0].replace('"', "")
        return state
    return "unknown"


def create_vm_folder(name):
    folder = os.path.join("vms", name)
    os.makedirs(folder, exist_ok=True)
    return folder


# ================================
#     VM CREATE (ASYNC)
# ================================
@app.post("/api/vm/create")
def api_create_vm():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    data = request.get_json(force=True)
    name = data.get("name")
    owner_email = data.get("owner_email")
    mem = int(data.get("memory_mb", 2048))
    cpus = int(data.get("cpus", 2))
    disk = int(data.get("disk_mb", 20000))

    if not name:
        return jsonify({"ok": False, "error": "missing_name"}), 400

    threading.Thread(
        target=create_vm_async_worker,
        args=(name, mem, cpus, disk),
        daemon=True
    ).start()

    now = datetime.datetime.utcnow()
    expires = now + datetime.timedelta(days=35)

    return jsonify({
        "ok": True,
        "connect": f"rdp://{name}",
        "port": 3389,
        "service_ports": [22, 3389],
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S")
    })


def create_vm_async_worker(name, mem, cpus, disk):
    print(f"[ASYNC] Creating VM {name}")

    run_cmd(["VBoxManage", "createvm", "--name", name, "--register"])
    run_cmd(["VBoxManage", "modifyvm", name, "--memory", str(mem)])
    run_cmd(["VBoxManage", "modifyvm", name, "--cpus", str(cpus)])
    run_cmd(["VBoxManage", "modifyvm", name, "--nic1", "nat"])
    run_cmd(["VBoxManage", "modifyvm", name, "--vrde", "on"])
    run_cmd(["VBoxManage", "modifyvm", name, "--vrdeport", "3389"])

    disk_path = os.path.join("vms", f"{name}.vdi")
    run_cmd(["VBoxManage", "createmedium", "disk", "--filename", disk_path, "--size", str(disk)])

    run_cmd(["VBoxManage", "storagectl", name, "--name", "SATA", "--add", "sata"])
    run_cmd(["VBoxManage", "storageattach", name, "--storagectl", "SATA", "--port", "0", "--device", "0",
             "--type", "hdd", "--medium", disk_path])

    print(f"[ASYNC] VM Created: {name}")


# ================================
#     VM ACTIONS
# ================================
@app.post("/api/vm/action")
def api_vm_action():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    data = request.get_json(force=True)
    name = data.get("name")
    action = data.get("action")

    if not name or not action:
        return jsonify({"ok": False, "error": "missing_params"}), 400

    if action == "start":
        run_cmd(["VBoxManage", "startvm", name, "--type", "headless"])

    elif action == "stop":
        run_cmd(["VBoxManage", "controlvm", name, "poweroff"])

    elif action == "reset":
        run_cmd(["VBoxManage", "controlvm", name, "reset"])

    elif action == "delete":
        run_cmd(["VBoxManage", "controlvm", name, "poweroff"])
        time.sleep(3)
        run_cmd(["VBoxManage", "unregistervm", name, "--delete"])

    else:
        return jsonify({"ok": False, "error": "unknown_action"}), 400

    return jsonify({"ok": True})


# ================================
#     VM STATUS
# ================================
@app.get("/api/vm/status")
def api_vm_status():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    name = request.args.get("name")
    if not name:
        return jsonify({"ok": False, "status": "missing_name"}), 400

    status = get_vm_status(name)
    ip = get_vm_ip(name)

    return jsonify({
        "ok": True,
        "name": name,
        "status": status,
        "ip": ip,
    })


# ================================
#     CHANGE PASSWORD
# ================================
@app.post("/api/vm/change_password")
def api_change_password():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    data = request.get_json(force=True)
    name = data.get("name")
    new_pw = data.get("new_password")

    if not name or not new_pw:
        return jsonify({"ok": False, "error": "missing_params"}), 400

    run_cmd([
        "VBoxManage", "guestcontrol", name,
        "run", "--exe", "cmd.exe", "--username", "Administrator",
        "--password", data.get("current_password"),
        "--", "/C", f"net user Administrator {new_pw}"
    ])

    return jsonify({"ok": True})


# ================================
#     RENEW EXPIRY
# ================================
@app.post("/api/vm/renew")
def api_renew_vm():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    data = request.get_json(force=True)
    name = data.get("name")
    days = int(data.get("days", 35))

    if not name:
        return jsonify({"ok": False, "error": "missing_name"}), 400

    new_exp = datetime.datetime.utcnow() + datetime.timedelta(days=days)

    return jsonify({
        "ok": True,
        "expires_at": new_exp.strftime("%Y-%m-%d %H:%M:%S")
    })


# ================================
#     UPDATE RESOURCES
# ================================
@app.post("/api/vm/update_resources")
def api_update_resources():

    if not require_token():
        return jsonify({"ok": False, "error": "invalid_token"}), 401

    data = request.get_json(force=True)
    name = data.get("name")
    ram = data.get("memory_mb")
    cpus = data.get("cpus")

    if not name or not ram or not cpus:
        return jsonify({"ok": False, "error": "missing_params"}), 400

    run_cmd(["VBoxManage", "modifyvm", name, "--memory", str(ram)])
    run_cmd(["VBoxManage", "modifyvm", name, "--cpus", str(cpus)])

    return jsonify({"ok": True})


# ================================
#     RUN SERVER
# ================================
if __name__ == "__main__":
    print("📡 Running VirtualBox API on http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001)

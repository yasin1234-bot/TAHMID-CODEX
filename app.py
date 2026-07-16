import os
import json
import signal
import requests
import shutil
import zipfile
import hashlib
import subprocess
import psutil
import shutil
import threading
import io
import multiprocessing
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort
from flask_sqlalchemy import SQLAlchemy  # এটি যোগ করা হয়েছে
from werkzeug.utils import secure_filename
from pathlib import Path
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "yasin-vps-secret-2025" # আপনার সিক্রেট কী
# BotFather থেকে পাওয়া টোকেন এখানে বসান
BOT_TOKEN = '8457683795:AAE-O0a3Evi_2tK3KLRh89bzEnFFYfR2xAA'

# আপনার চ্যানেল এবং গ্রুপের ইউজারনেম (অবশ্যই @ সহ)
# আগের লিঙ্কগুলোর বদলে শুধু @ সহ ইউজারনেম দিন
CHANNEL_ID = '@freefireob51'
GROUP_ID = '@free_like_bot1'

def check_membership(user_id):
    links = [CHANNEL_ID, GROUP_ID]
    for chat_id in links:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={chat_id}&user_id={user_id}"
        try:
            response = requests.get(url).json()
            if response.get('ok'):
                status = response['result']['status']
                # যদি কোনো একটায় জয়েন না থাকে, তবে False পাঠাবে
                if status not in ['member', 'administrator', 'creator']:
                    return False
            else:
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    return True

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"success": False, "message": "User ID missing!"})

    # পরিবর্তন এখানে: শুধু একটা ভেরিয়েবল নিন
    is_member = check_membership(user_id)
    
    if is_member:
        return jsonify({"success": True, "message": "Verified!"})
    else:
        return jsonify({"success": False, "message": "চ্যানেলে জয়েন করা নেই!"})

# সেশনের মেয়াদ ২৪ ঘণ্টা সেট করা
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

def get_and_update_count():
    file_path = "counter.txt"
    
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("0")
    
    with open(file_path, "r") as f:
        data = f.read().strip()
        count = int(data) if data else 0

    # সেশনকে 'permanent' করা যাতে এটি ২৪ ঘণ্টা পর্যন্ত টিকে থাকে
    session.permanent = True

    if not session.get('has_visited'):
        count += 1
        with open(file_path, "w") as f:
            f.write(str(count))
        session['has_visited'] = True
    
    return count
    
# ডেটাবেস ফাইল কোথায় সেভ হবে তা বলে দিতে হবে
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# এখন db ডিফাইন করলে আর এরর আসবে না
db = SQLAlchemy(app) 

# Song মডেল
class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

app.secret_key = os.environ.get("SECRET_KEY", "yasin-vps-secret-2025")

# আপনার দেওয়া API এর তথ্য
API_BASE_URL = "https://yasinbhaifreelikeapi.vercel.app/like"
API_KEY = "YASIN"

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
SERVERS_DIR = BASE_DIR / "servers"
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
SERVERS_DIR.mkdir(exist_ok=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "TAHMID CODEX@@@1")

RUNNING_PROCESSES = {}
RESET_TIMERS = {}

THEME_PRESETS = {
    "purple": "#a855f7",
    "green":  "#00ff41",
    "blue":   "#38bdf8",
    "red":    "#ef4444",
    "amber":  "#fbbf24",
    "cyan":   "#06b6d4",
    "pink":   "#ec4899",
    "lime":   "#84cc16",
}


# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return {
        "servers": {},
        "users": {},
        "settings": {
            "maintenance": False,
            "maintenance_msg": "System under maintenance.",
            "theme_color": "#a855f7"
        }
    }

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str))

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_theme_color():
    data = load_data()
    return data.get("settings", {}).get("theme_color", "#a855f7")


# ─── Context processor: injects theme_color into every template ───────────────

@app.context_processor
def inject_theme():
    return {"theme_color": get_theme_color()}


# ─── Decorators ───────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        data = load_data()
        settings = data.get("settings", {})
        if settings.get("maintenance") and session.get("username") != "__admin__":
            return render_template("maintenance.html", message=settings.get("maintenance_msg", "Under maintenance"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ─── Process helpers ──────────────────────────────────────────────────────────

def is_process_alive(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def kill_process(pid):
    try:
        p = psutil.Process(pid)
        children = p.children(recursive=True)
        p.terminate()
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
        try:
            p.wait(timeout=5)
        except psutil.TimeoutExpired:
            p.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

def get_run_command(runtime, main_file):
    ext = Path(main_file).suffix.lower()
    if runtime == "node" or ext in (".js", ".ts", ".mjs"):
        return ["node", main_file]
    else:
        return ["python", "-u", main_file]

def _sync_process_status():
    data = load_data()
    changed = False
    for name, cfg in data["servers"].items():
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
            changed = True
    if changed:
        save_data(data)

_sync_process_status()


# ─── Auto-reset helpers ────────────────────────────────────────────────────────

def _auto_reset_seconds(cfg):
    ar = cfg.get("auto_reset", {})
    y = ar.get("years", 0) or 0
    d = ar.get("days", 0) or 0
    h = ar.get("hours", 0) or 0
    m = ar.get("minutes", 0) or 0
    s = ar.get("seconds", 0) or 0
    return int(y * 365 * 24 * 3600 + d * 24 * 3600 + h * 3600 + m * 60 + s)

def _do_auto_reset(name):
    try:
        data = load_data()
        cfg = data["servers"].get(name)
        if not cfg:
            return

        pid = cfg.get("pid")

        if name in RUNNING_PROCESSES:
            entry = RUNNING_PROCESSES[name]
            proc = entry["proc"]

            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            try:
                entry["log_file"].close()
            except Exception:
                pass

            del RUNNING_PROCESSES[name]

        elif pid:
            kill_process(pid)

        log_path = SERVERS_DIR / name / "logs.txt"

        try:
            with open(log_path, "a") as lf:
                lf.write(f"\n{'='*50}\n[{datetime.now().isoformat()}] AUTO RESET triggered\n{'='*50}\n")
        except Exception:
            pass

        main_file = cfg.get("main_file") or "main.py"
        extract_dir = SERVERS_DIR / name / "extracted"
        main_path = extract_dir / main_file

        if main_path.exists():
            cmd = get_run_command(cfg.get("runtime", "python"), main_file)

            env = os.environ.copy()
            env["PORT"] = str(cfg.get("port", 8080))

            log_file = open(log_path, "a")

            # ✅ FIXED LINE
            proc = subprocess.Popen(
                cmd,
                cwd=str(extract_dir),
                stdout=log_file,
                stderr=log_file,
                env=env,
                preexec_fn=os.setsid
            )

            RUNNING_PROCESSES[name] = {
                "proc": proc,
                "log_file": log_file
            }

            cfg["status"] = "running"
            cfg["pid"] = proc.pid

        else:
            cfg["status"] = "stopped"
            cfg["pid"] = None

        data["servers"][name] = cfg
        save_data(data)

        total = _auto_reset_seconds(cfg)

        # ❗ এখানে typo ছিল: auto_eset → auto_reset
        if cfg.get("auto_reset", {}).get("enabled") and total > 0:
            _schedule_reset(name, total)

    except Exception as e:
        print("Auto reset error:", e)


def _schedule_reset(name, total_seconds):
    if name in RESET_TIMERS:
        try:
            RESET_TIMERS[name]["timer"].cancel()
        except Exception:
            pass

    t = threading.Timer(total_seconds, _do_auto_reset, args=[name])
    t.daemon = True
    t.start()

    RESET_TIMERS[name] = {
        "timer": t,
        "started_at": datetime.now().isoformat(),
        "total_seconds": total_seconds
    }


def _init_reset_timers():
    data = load_data()

    for name, cfg in data["servers"].items():
        ar = cfg.get("auto_reset", {})

        if ar.get("enabled"):
            total = _auto_reset_seconds(cfg)

            if total > 0:
                _schedule_reset(name, total)


_init_reset_timers()


# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # প্রথমে ভিজিটর কাউন্ট আপডেট করে নেবে
    current_visit = get_and_update_count()
    
    # এরপর আপনার আগের লগইন চেক লজিক কাজ করবে
    if session.get("username"):
        # যদি ড্যাশবোর্ডে রিডাইরেক্ট হয়, সেখানে 'visit' ডাটা পাঠাতে চাইলে 
        # আপনাকে ড্যাশবোর্ড রুটেও এই লজিক রাখতে হবে। 
        return redirect(url_for("dashboard"))
        
    return redirect(url_for("login"))

# ─── Auth routes (Updated for Raw Password) ───────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    # ভিজিটর কাউন্টার কল করা
    current_visit = get_and_update_count() 
    
    data_settings = load_data() 
    logo_url = data_settings.get('settings', {}).get('logo_url', 'https://i.postimg.cc/default.png')
    theme_color = data_settings.get('settings', {}).get('theme_color', '#00ff41')

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not username:
            return render_template("login.html", error="Enter a username", logo_url=logo_url, theme_color=theme_color, visit=current_visit)
        
        data = load_data()
        user = data["users"].get(username)
        
        if user:
            stored_hash = user.get("password_hash", "")
            if stored_hash and stored_hash != hash_password(password):
                return render_template("login.html", error="Wrong password", logo_url=logo_url, theme_color=theme_color, visit=current_visit)
            
            if not stored_hash and password:
                data["users"][username]["password_hash"] = hash_password(password)
                data["users"][username]["raw_password"] = password 
                save_data(data)
        else:
            data["users"][username] = {
                "joined": datetime.now().isoformat(),
                "password_hash": hash_password(password) if password else "",
                "raw_password": password if password else "No Password" 
            }
            save_data(data)
            
        session["username"] = username
        return redirect(url_for("dashboard"))

    return render_template("login.html", error=None, logo_url=logo_url, theme_color=theme_color, visit=current_visit)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    try:
        username = session["username"]
        data = load_data()
        
        # settings.json ফাইল লোড করা
        settings_file = 'settings.json'
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    dashboard_settings = json.load(f)
            except:
                dashboard_settings = {"music_volume": 10, "music_url": ""}
        else:
            dashboard_settings = {"music_volume": 10, "music_url": ""}

        user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
        changed = False
        for name, cfg in user_servers.items():
            pid = cfg.get("pid")
            if pid and not is_process_alive(pid):
                cfg["status"] = "stopped"
                cfg["pid"] = None
                data["servers"][name] = cfg
                changed = True
        if changed:
            save_data(data)
            
        running = sum(1 for v in user_servers.values() if v.get("status") == "running")
        
        return render_template("dashboard.html", 
                               servers=user_servers, 
                               running=running, 
                               total=len(user_servers), 
                               username=username, 
                               settings=dashboard_settings)
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return f"System Error: {str(e)}", 500

@app.route("/admin/music/volume", methods=["POST"])
def update_settings():
    try:
        # ড্যাশবোর্ড থেকে ভলিউম ডাটা নেওয়া
        new_volume = request.form.get("volume")
        print(f"--- Received volume update: {new_volume} ---")
        
        settings_file = 'settings.json'
        
        # ডিফল্ট সেটিংস
        settings = {"music_volume": 10, "music_url": ""}
        
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                try:
                    settings = json.load(f)
                except:
                    pass

        # ভলিউম আপডেট
        if new_volume is not None:
            settings['music_volume'] = int(new_volume)
        
        # ফাইলে সেভ করা
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
            
        print(f"--- Success! Volume set to {new_volume} ---")
        return "Success"
        
    except Exception as e:
        print(f"Update Error: {e}")
        return f"Error: {str(e)}", 500




# ─── System stats API ─────────────────────────────────────────────────────────

@app.route("/api/stats")
@login_required
def system_stats():
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    return jsonify({"cpu": cpu, "ram": ram, "disk": disk})


# ─── Server management ────────────────────────────────────────────────────────

@app.route("/server/create", methods=["POST"])
@login_required
def create_server():
    name = request.form.get("name", "").strip().replace(" ", "-")
    runtime = request.form.get("runtime", "python")
    if not name:
        return redirect(url_for("dashboard"))
    data = load_data()
    if name in data["servers"]:
        return redirect(url_for("dashboard"))
    cfg = {
        "name": name,
        "owner": session["username"],
        "runtime": runtime,
        "status": "stopped",
        "main_file": "",
        "port": 8080,
        "packages": [],
        "pid": None,
        "created": datetime.now().isoformat(),
        "auto_reset": {"enabled": False, "years": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    }
    data["servers"][name] = cfg
    save_data(data)
    (SERVERS_DIR / name / "extracted").mkdir(parents=True, exist_ok=True)
    return redirect(url_for("server_detail", name=name))

@app.route("/server/delete/<name>", methods=["POST"])
@login_required
def delete_server(name):
    data = load_data()
    cfg = data.get("servers", {}).get(name) 
    
    if cfg and (cfg.get("owner") == session["username"] or session.get("admin")):
        pid = cfg.get("pid")
        if pid:
            kill_process(pid)
        
        if name in RUNNING_PROCESSES:
            try:
                RUNNING_PROCESSES[name]["proc"].terminate()
            except Exception:
                pass
            del RUNNING_PROCESSES[name]
            
        if name in RESET_TIMERS:
            try:
                RESET_TIMERS[name]["ter"].cancel()
            except Exception:
                pass
            del RESET_TIMERS[name]

        if "servers" in data and name in data["servers"]:
            del data["servers"][name]
        
        save_data(data)
        shutil.rmtree(SERVERS_DIR / name, ignore_errors=True)
        
    # নিচের লাইনটি নিশ্চিত হয়ে নিন (h সহ dashboard হবার কথা)
    return redirect(url_for("dashboard")) 

from flask import redirect, url_for, session

@app.route("/server/<name>")
# @login_required <-- এটা সরিয়ে দেওয়া হয়েছে যাতে অ্যাডমিন সরাসরি ঢুকতে পারে
def server_detail(name):
    try:
        data = load_data()
        cfg = data["servers"].get(name)
        
        if not cfg:
            return "Server not found", 404
        
        # অ্যাডমিন এবং ইউজার চেক
        current_user = session.get("username")
        is_admin = session.get("admin") == True 

        # যদি ইউজার অ্যাডমিন না হয়, তবে লগইন করা আছে কি না চেক করবে
        if not is_admin:
            if not current_user:
                # লগইন করা না থাকলে সরাসরি লগইন পেজে পাঠিয়ে দেবে
                return redirect(url_for('login')) 
            
            # যদি লগইন থাকে কিন্তু সে ওই সার্ভারের মালিক না হয়
            if cfg.get("owner") != current_user:
                return "Unauthorized", 403
        
        # --- এখান থেকে বাকি কোড আগের মতোই কাজ করবে ---

        # প্রসেস অ্যালাইভ আছে কি না চেক এবং স্ট্যাটাস আপডেট
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
            data["servers"][name] = cfg
            save_data(data)

        # Auto Reset ডাটা নিশ্চিত করা
        if "auto_reset" not in cfg:
            cfg["auto_reset"] = {"enabled": False, "years": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}

        # settings.json থেকে ডাটা লোড করা
        import json, os
        settings_file = 'settings.json'
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                server_settings = json.load(f)
        else:
            server_settings = {}

        # ফাইল লিস্ট সংগ্রহ করা
        from pathlib import Path
        SERVERS_DIR = Path("servers") 
        extract_dir = SERVERS_DIR / name / "extracted"
        
        files = list_files(extract_dir)
        
        return render_template("server.html", 
                               server_name=name, 
                               config=cfg, 
                               files=files, 
                               theme_color=cfg.get('theme_color', '#a855f7'),
                               settings=server_settings)
    except Exception as e:
        print(f"Error in server_detail: {e}")
        return str(e), 500

def list_files(directory, base=""):
    result = []
    if not directory.exists():
        return result
    try:
        for entry in sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name)):
            rel = f"{base}/{entry.name}" if base else entry.name
            if entry.is_dir():
                result.append({"name": entry.name, "path": rel, "type": "dir", "size": 0})
                result.extend(list_files(entry, rel))
            else:
                result.append({"name": entry.name, "path": rel, "type": "file", "size": entry.stat().st_size})
    except Exception:
        pass
    return result


# ─── Upload ───────────────────────────────────────────────────────────────────

@app.route("/server/<name>/upload", methods=["POST"])
@login_required
def upload_file(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file"})
    f = request.files["file"]
    extract_dir = SERVERS_DIR / name / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    upload_path = SERVERS_DIR / name / f"upload_{f.filename}"
    f.save(upload_path)
    extracted_files = []
    if f.filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(upload_path, "r") as z:
                z.extractall(extract_dir)
                extracted_files = [m.filename for m in z.infolist() if not m.is_dir()]
            upload_path.unlink(missing_ok=True)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    else:
        dest = extract_dir / f.filename
        shutil.copy(upload_path, dest)
        upload_path.unlink(missing_ok=True)
        extracted_files = [f.filename]
        if not cfg.get("main_file") and f.filename.endswith((".py", ".js", ".ts")):
            cfg["main_file"] = f.filename
            data["servers"][name] = cfg
            save_data(data)
    return jsonify({"success": True, "files": extracted_files})

@app.route('/server/<server_name>/files/delete_all', methods=['POST'])
@login_required # সিকিউরিটির জন্য এটি যোগ করা ভালো
def delete_all_files(server_name):
    # আপনার আসল ফাইল পাথ হচ্ছে SERVERS_DIR / server_name / "extracted"
    # SERVERS_DIR আপনার কোডের ওপরে ডিফাইন করা আছে (Path("servers"))
    folder_path = SERVERS_DIR / server_name / "extracted"
    
    try:
        if folder_path.exists():
            # ফোল্ডারের ভেতরের সব ফাইল ও ফোল্ডার ডিলিট করা
            for item in os.listdir(folder_path):
                item_path = folder_path / item
                if item_path.is_file() or item_path.is_symlink():
                    os.unlink(item_path)
                elif item_path.is_dir():
                    shutil.rmtree(item_path)
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Folder not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# ─── Packages ─────────────────────────────────────────────────────────────────

@app.route("/server/<name>/packages/install", methods=["POST"])
@login_required
def install_package(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    payload = request.get_json()
    pkg_name = payload.get("name", "").strip()
    pkg_ver = payload.get("version", "").strip()
    if not pkg_name:
        return jsonify({"success": False, "error": "Package name required"})
    install_str = f"{pkg_name}=={pkg_ver}" if pkg_ver else pkg_name
    try:
        result = subprocess.run(
            ["pip", "install", install_str],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            return jsonify({"success": False, "error": result.stderr[:400] or result.stdout[:400]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    pkgs = cfg.get("packages", [])
    pkgs = [p for p in pkgs if p["name"] != pkg_name]
    pkgs.append({"name": pkg_name, "version": pkg_ver or "", "installed_at": datetime.now().isoformat()})
    cfg["packages"] = pkgs
    data["servers"][name] = cfg
    save_data(data)
    req_path = SERVERS_DIR / name / "extracted" / "requirements.txt"
    try:
        lines = req_path.read_text().splitlines() if req_path.exists() else []
        lines = [l for l in lines if not l.lower().startswith(pkg_name.lower())]
        lines.append(install_str)
        req_path.write_text("\n".join(lines) + "\n")
    except Exception:
        pass
    return jsonify({"success": True, "package": pkg_name})

@app.route("/server/<name>/packages/remove", methods=["POST"])
@login_required
def remove_package(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False}), 404
    payload = request.get_json()
    pkg_name = payload.get("name", "")
    cfg["packages"] = [p for p in cfg.get("packages", []) if p["name"] != pkg_name]
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})


# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route("/server/<name>/settings", methods=["POST"])
@login_required
def save_settings(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    payload = request.get_json()
    cfg["main_file"] = payload.get("main_file", cfg.get("main_file", ""))
    cfg["port"] = payload.get("port", cfg.get("port", 8080))
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})


# ─── Auto Reset routes ────────────────────────────────────────────────────────

@app.route("/server/<name>/auto-reset/settings", methods=["POST"])
@login_required
def save_auto_reset_settings(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    payload = request.get_json()
    enabled = bool(payload.get("enabled", False))
    years = int(payload.get("years", 0) or 0)
    days = int(payload.get("days", 0) or 0)
    hours = int(payload.get("hours", 0) or 0)
    minutes = int(payload.get("minutes", 0) or 0)
    seconds = int(payload.get("seconds", 0) or 0)
    cfg["auto_reset"] = {"enabled": enabled, "years": years, "days": days, "hours": hours, "minutes": minutes, "seconds": seconds}
    data["servers"][name] = cfg
    save_data(data)
    if name in RESET_TIMERS:
        try:
            RESET_TIMERS[name]["timer"].cancel()
        except Exception:
            pass
        del RESET_TIMERS[name]
    if enabled:
        total = _auto_reset_seconds(cfg)
        if total > 0:
            _schedule_reset(name, total)
    return jsonify({"success": True})

@app.route("/server/<name>/auto-reset", methods=["POST"])
@login_required
def trigger_auto_reset(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    threading.Thread(target=_do_auto_reset, args=[name], daemon=True).start()
    return jsonify({"success": True})

@app.route("/server/<name>/auto-reset/status")
@login_required
def auto_reset_status(name):
    if name in RESET_TIMERS:
        entry = RESET_TIMERS[name]
        started = datetime.fromisoformat(entry["started_at"])
        elapsed = (datetime.now() - started).total_seconds()
        remaining = max(0, entry["total_seconds"] - int(elapsed))
        return jsonify({"remaining": remaining, "total": entry["total_seconds"]})
    data = load_data()
    cfg = data["servers"].get(name, {})
    total = _auto_reset_seconds(cfg)
    return jsonify({"remaining": total, "total": total})


# ─── Start / Stop ─────────────────────────────────────────────────────────────

@app.route("/server/<name>/start", methods=["POST"])
@login_required
def start_server(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Not found"}), 404
    pid = cfg.get("pid")
    if pid and is_process_alive(pid):
        return jsonify({"success": False, "error": "Already running"})
    main_file = cfg.get("main_file") or "main.py"
    extract_dir = SERVERS_DIR / name / "extracted"
    main_path = extract_dir / main_file
    if not main_path.exists():
        return jsonify({"success": False, "error": f"{main_file} not found. Upload your files first."})
    log_path = SERVERS_DIR / name / "logs.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = get_run_command(cfg.get("runtime", "python"), main_file)
    env = os.environ.copy()
    env["PORT"] = str(cfg.get("port", 8080))
    try:
        with open(log_path, "a") as lf:
            lf.write(f"\n{'='*50}\n[{datetime.now().isoformat()}] Starting: {' '.join(cmd)}\n{'='*50}\n")
        log_file = open(log_path, "a")
        proc = subprocess.Popen(
            cmd,
            cwd=str(extract_dir),
            stdout=log_file,
            stderr=log_file,
            env=env,
            preexec_fn=os.setsid
        )
        RUNNING_PROCESSES[name] = {"proc": proc, "log_file": log_file}
        cfg["status"] = "running"
        cfg["pid"] = proc.pid
        data["servers"][name] = cfg
        save_data(data)
        return jsonify({"success": True, "pid": proc.pid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/server/<name>/stop", methods=["POST"])
@login_required
def stop_server(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False}), 404
    pid = cfg.get("pid")
    stopped = False
    if name in RUNNING_PROCESSES:
        entry = RUNNING_PROCESSES[name]
        proc = entry["proc"]
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            entry["log_file"].close()
        except Exception:
            pass
        del RUNNING_PROCESSES[name]
        stopped = True
    if pid and not stopped:
        kill_process(pid)
    log_path = SERVERS_DIR / name / "logs.txt"
    try:
        with open(log_path, "a") as lf:
            lf.write(f"[{datetime.now().isoformat()}] Server stopped\n")
    except Exception:
        pass
    cfg["status"] = "stopped"
    cfg["pid"] = None
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})


# ─── Logs ─────────────────────────────────────────────────────────────────────

@app.route("/server/<name>/logs")
@login_required
def get_logs(name):
    log_path = SERVERS_DIR / name / "logs.txt"
    if not log_path.exists():
        return jsonify({"logs": "No logs yet. Start the server to see output."})
    try:
        content = log_path.read_text(errors="replace")
        lines = content.splitlines()
        if len(lines) > 200:
            lines = lines[-200:]
            content = "... (showing last 200 lines) ...\n" + "\n".join(lines)
        return jsonify({"logs": content or "No output yet."})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})

@app.route("/server/<name>/logs/clear", methods=["POST"])
@login_required
def clear_logs(name):
    log_path = SERVERS_DIR / name / "logs.txt"
    try:
        log_path.write_text("")
    except Exception:
        pass
    return jsonify({"success": True})


# ─── Admin ────────────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Wrong admin password")
    return render_template("admin_login.html", error=None)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

# ─── Admin Dashboard & Management ─────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_dashboard():
    data = load_data()
    servers = data["servers"]
    users_raw = data["users"]
    settings = data.get("settings", {})
    
    for name, cfg in servers.items():
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
            
    running = sum(1 for v in servers.values() if v.get("status") == "running")
    total_files = 0
    for sname in servers:
        ed = SERVERS_DIR / sname / "extracted"
        if ed.exists():
            total_files += sum(1 for f in ed.rglob("*") if f.is_file())
            
    user_stats = []
    for u in users_raw:
        u_servers = [v for v in servers.values() if v.get("owner") == u]
        u_files = 0
        for sv in u_servers:
            ed = SERVERS_DIR / sv["name"] / "extracted"
            if ed.exists():
                u_files += sum(1 for f in ed.rglob("*") if f.is_file())
        
        # এখানে আসল পাসওয়ার্ড (raw_password) দেখানোর জন্য কোড আপডেট করা হয়েছে
        user_stats.append({
            "username": u,
            "password": users_raw[u].get("raw_password", "Not Saved Yet"), # আসল পাসওয়ার্ড দেখাবে
            "projects": len(u_servers),
            "running": sum(1 for sv in u_servers if sv.get("status") == "running"),
            "files": u_files,
            "joined": users_raw[u].get("joined", "")
        })
        
    return render_template("admin.html", users=user_stats, servers=servers, settings=settings,
                           total_users=len(users_raw), total_projects=len(servers),
                           running=running, total_files=total_files,
                           theme_presets=THEME_PRESETS)


# ─── Admin User Management ────────────────────────────────────────────────────

@app.route("/admin/user/<username>/files")
@admin_required
def admin_user_files(username):
    data = load_data()
    user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
    file_data = {}
    for name, cfg in user_servers.items():
        ed = SERVERS_DIR / name / "extracted"
        file_data[name] = {"config": cfg, "files": list_files(ed)}
    return render_template("admin_files.html", username=username, file_data=file_data)

@app.route("/admin/user/<username>/delete", methods=["POST"])
@admin_required
def admin_delete_user(username):
    data = load_data()
    to_delete = [k for k, v in data["servers"].items() if v.get("owner") == username]
    for name in to_delete:
        pid = data["servers"][name].get("pid")
        if pid:
            kill_process(pid)
        if name in RUNNING_PROCESSES:
            try:
                RUNNING_PROCESSES[name]["proc"].terminate()
            except Exception:
                pass
            del RUNNING_PROCESSES[name]
        if name in RESET_TIMERS:
            try:
                RESET_TIMERS[name]["timer"].cancel()
            except Exception:
                pass
            del RESET_TIMERS[name]
        shutil.rmtree(SERVERS_DIR / name, ignore_errors=True)
        del data["servers"][name]
    data["users"].pop(username, None)
    save_data(data)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/maintenance", methods=["POST"])
@admin_required
def toggle_maintenance():
    data = load_data()
    payload = request.get_json()
    data["settings"]["maintenance"] = payload.get("enabled", False)
    data["settings"]["maintenance_msg"] = payload.get("message", "Under maintenance")
    save_data(data)
    return jsonify({"success": True})


# ─── Theme route ──────────────────────────────────────────────────────────────

@app.route("/admin/theme", methods=["POST"])
@admin_required
def set_theme():
    data = load_data()
    payload = request.get_json()
    color = payload.get("color", "#a855f7").strip()
    
    if not color.startswith("#"):
        return jsonify({"success": False, "error": "Invalid color"}), 400
        
    if "settings" not in data:
        data["settings"] = {}
    
    data["settings"]["theme_color"] = color
    save_data(data)
    return jsonify({"success": True, "color": color})

@app.route('/admin/logo', methods=['POST'])
def update_logo():
    data = request.get_json()
    new_url = data.get('logo_url')
    
    if new_url:
        # ডেটা লোড করুন
        full_data = load_data() 
        
        # নিশ্চিত করুন যে 'settings' ডিকশনারিটি আছে
        if 'settings' not in full_data:
            full_data['settings'] = {}
            
        # লোগো ইউআরএল আপডেট করুন
        full_data['settings']['logo_url'] = new_url
        
        # ডেটা সেভ করুন
        save_data(full_data)
        
        return jsonify({"success": True, "message": "Logo updated!"})
    
    return jsonify({"success": False, "message": "Invalid URL"}), 400

# মিউজিক ফাইল আপলোড রাউট
@app.route('/admin/music/upload', methods=['POST'])
def upload_music_file():
    try:
        if 'audio' not in request.files:
            return jsonify({"success": False, "error": "No file part"}), 400
        
        file = request.files['audio']
        if file.filename == '':
            return jsonify({"success": False, "error": "No selected file"}), 400

        if file:
            import json, os
            from werkzeug.utils import secure_filename
            
            # ফোল্ডার চেক করা
            upload_folder = 'static/uploads'
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
                
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)

            # ডেটাবেসে গান সেভ করার অংশ
            # 'Song' ক্লাসটি ওপরে ডিফাইন করা থাকতে হবে
            new_song = Song(name=filename)
            db.session.add(new_song)
            db.session.commit()
            
            music_url = f"/static/uploads/{filename}"
            
            # সেটিংস ফাইল লোড ও সেভ করা
            settings_file = 'settings.json'
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    current_settings = json.load(f)
            else:
                current_settings = {}

            current_settings['music_url'] = music_url
            with open(settings_file, 'w') as f:
                json.dump(current_settings, f, indent=4)
                
            return jsonify({"success": True, "url": music_url})
            
    except Exception as e:
        # টার্মিনালে এরর দেখার জন্য
        print(f"Error in upload: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/admin/music', methods=['POST'])
def save_music():
    try:
        data = request.get_json()
        music_url = data.get('music_url', '')
        
        import json, os
        settings_file = 'settings.json'
        
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                current_settings = json.load(f)
        else:
            current_settings = {}

        current_settings['music_url'] = music_url
        
        with open(settings_file, 'w') as f:
            json.dump(current_settings, f, indent=4)
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in save_music: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# গান দেখার জন্য Route
@app.route('/get_songs', methods=['GET'])
def get_songs():
    songs = Song.query.all()  # আপনার মডেলের নাম Song হলে
    song_list = []
    for song in songs:
        song_list.append({'id': song.id, 'name': song.name})
    return jsonify(song_list)

# গান ডিলিট করার জন্য Route
import os

@app.route('/delete_song/<int:id>', methods=['DELETE'])
def delete_song(id):
    song = Song.query.get(id)
    if song:
        # গানটির নাম ব্যবহার করে static/uploads ফোল্ডার থেকে ফাইলটি ডিলিট করার চেষ্টা
        # যদি ডাটাবেসে ফাইলের নাম song.name হিসেবে থাকে:
        file_path = os.path.join('static', 'uploads', song.name)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"File {song.name} deleted successfully from folder.")
            except Exception as e:
                print(f"Error deleting file from folder: {e}")
        else:
            print(f"File not found at: {file_path}")

        # ডাটাবেস থেকে ডিলিট
        db.session.delete(song)
        db.session.commit()
        return jsonify({'message': 'Song and file deleted successfully'})
    
    return jsonify({'message': 'Song not found'}), 404

@app.route('/admin/songs')
@login_required  # যদি লগইন করা বাধ্যতামূলক হয়
def list_songs():
    try:
        # ডেটাবেস থেকে সব গানের লিস্ট আনা
        songs = Song.query.all()
        return render_template('admin_songs.html', songs=songs)
    except Exception as e:
        print(f"Error fetching songs: {e}")
        return "Error loading songs", 500

@app.route('/api/all_songs') # এখানে লিঙ্কটি পরিবর্তন করা হয়েছে
def fetch_all_songs_api(): # এখানে ফাংশনের নাম পরিবর্তন করা হয়েছে
    try:
        songs = Song.query.all()
        return jsonify([{'name': s.name} for s in songs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Download routes ───────────────────────────────────────────────────────────

@app.route("/admin/file/<project_name>/download")
@admin_required
def admin_download_file(project_name):
    file_path = request.args.get("path", "")
    if not file_path:
        abort(400)
    safe_path = (SERVERS_DIR / project_name / "extracted" / file_path).resolve()
    base = (SERVERS_DIR / project_name / "extracted").resolve()
    if not str(safe_path).startswith(str(base)) or not safe_path.exists() or safe_path.is_dir():
        abort(404)
    return send_file(safe_path, as_attachment=True, download_name=safe_path.name)

@app.route("/admin/project/<project_name>/download")
@admin_required
def admin_download_project(project_name):
    type_filter = request.args.get("type", "all")
    extract_dir = SERVERS_DIR / project_name / "extracted"
    if not extract_dir.exists():
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in extract_dir.rglob("*"):
            if not f.is_file():
                continue
            if type_filter != "all" and not f.name.endswith(type_filter):
                continue
            zf.write(f, f.relative_to(extract_dir))
    buf.seek(0)
    ext_part = type_filter.replace(".", "") if type_filter != "all" else ""
    fname = f"{project_name}{'-' + ext_part if ext_part else ''}.zip"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/zip")

@app.route("/admin/user/<username>/download")
@admin_required
def admin_download_user(username):
    type_filter = request.args.get("type", "all")
    data = load_data()
    user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in user_servers:
            extract_dir = SERVERS_DIR / name / "extracted"
            if not extract_dir.exists():
                continue
            for f in extract_dir.rglob("*"):
                if not f.is_file():
                    continue
                if type_filter != "all" and not f.name.endswith(type_filter):
                    continue
                arcname = Path(name) / f.relative_to(extract_dir)
                zf.write(f, arcname)
    buf.seek(0)
    ext_part = type_filter.replace(".", "") if type_filter != "all" else ""
    fname = f"{username}-files{'-' + ext_part if ext_part else ''}.zip"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/zip")
       

# ─── New Dynamic API Runner (যেকোনো নামের জন্য কাজ করবে) ──────────────────────

@app.route('/<dynamic_name>')
def dynamic_api_runner(dynamic_name):
    try:
        # এখানে আমরা ধরে নিচ্ছি আপনার ফাইলগুলো কোনো নির্দিষ্ট প্রজেক্ট ফোল্ডারে আছে
        # অথবা আপনি চাইলে সরাসরি প্রজেক্টের নাম দিয়েই কল করতে পারেন।
        # উদাহরণ: domain.com/my-script -> এটি my-script.py বা .json খুঁজবে।
        
        data = load_data()
        # আমরা সব প্রজেক্টের ভেতর এই ফাইলটি খুঁজব
        for project_name in data["servers"]:
            project_dir = SERVERS_DIR / project_name / "extracted"
            
            # ফাইলের সম্ভাব্য নামগুলো চেক করা (যেমন: name.py, name.json, name.html)
            for ext in [".py", ".json", ".html", ".txt"]:
                file_path = (project_dir / f"{dynamic_name}{ext}").resolve()

                if file_path.exists():
                    # যদি পাইথন ফাইল হয় তবে রান করবে
                    if ext == ".py":
                        result = subprocess.run(
                            ["python", str(file_path)],
                            capture_output=True, text=True, timeout=30
                        )
                        if result.returncode == 0:
                            try:
                                return jsonify(json.loads(result.stdout))
                            except:
                                return f"<pre>{result.stdout}</pre>"
                        else:
                            return jsonify({"error": "Script Error", "details": result.stderr}), 500
                    
                    # অন্য ফাইল হলে সরাসরি দেখাবে
                    return send_file(file_path)

        # যদি কোথাও না পাওয়া যায়
        return jsonify({"error": f"Route or File '{dynamic_name}' not found in any project"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# ─── Project Management Routes (Admin Project List) ───────────────────────────

@app.route("/admin/project/control", methods=["POST"])
@admin_required
def admin_project_control():
    try:
        data = request.get_json()
        name = data.get("name")
        action = data.get("action") # 'start' or 'stop'
        
        if action == "start":
            return start_server(name) # আগের তৈরি করা স্টার্ট ফাংশন কল হবে
        elif action == "stop":
            return stop_server(name)  # আগের তৈরি করা স্টপ ফাংশন কল হবে
            
        return jsonify({"success": False, "error": "Invalid action"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/admin/project/update_reset", methods=["POST"])
@admin_required
def admin_update_reset():
    try:
        data = request.get_json()
        name = data.get("name")
        minutes = int(data.get("minutes", 0))
        
        all_data = load_data()
        cfg = all_data["servers"].get(name)
        
        if cfg:
            # অটো রিসেট ডাটা আপডেট
            cfg["auto_reset"] = {
                "enabled": True if minutes > 0 else False,
                "years": 0, "days": 0, "hours": 0,
                "minutes": minutes,
                "seconds": 0
            }
            cfg["reset_time"] = minutes # HTML এ সিলেক্টেড রাখার জন্য
            all_data["servers"][name] = cfg
            save_data(all_data)
            
            # আগের টাইমার ক্যানসেল করে নতুন করে শিডিউল করা
            if name in RESET_TIMERS:
                try: RESET_TIMERS[name]["timer"].cancel()
                except: pass
                del RESET_TIMERS[name]
                
            if minutes > 0:
                _schedule_reset(name, minutes * 60)
                
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Project not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
 
# --- LIKE BOT PAGE ROUTE ---
# ১. লাইক পেজ দেখানোর জন্য রাউট (এটি একবারই থাকবে)
@app.route("/like.html")
def index_likebot():
    return render_template("like.html")

                             
@app.route('/send_like', methods=['POST'])
def send_like():
    uid = request.form.get('uid')
    server_name = request.form.get('server', 'bd') 
    
    if not uid:
        return jsonify({'status': 'error', 'message': 'UID পাওয়া যায়নি!'})

    # API URL
    API_URL = f"https://yasinbhaifreelikeapi.vercel.app/like?uid={uid}&server_name={server_name}&key=YASIN"

    try:
        response = requests.get(API_URL, timeout=30)
        
        # এপিআই যদি ২০০ ওকে দেয়, কিন্তু ভেতরে এরর থাকে (যেমন ভুল ইউআইডি)
        if response.status_code == 200:
            data = response.json()
            
            # এপিআই যদি সাকসেসফুলি লাইক পাঠায়
            if "LikesGivenByAPI" in data:
                return jsonify({
                    'status': 'success',
                    'uid': uid,
                    'accName': data.get('PlayerNickname') or "N/A",
                    'oldLikes': data.get('LikesbeforeCommand') or "0",
                    'totalLikes': data.get('LikesafterCommand') or "0",
                    'added': data.get('LikesGivenByAPI') or "0",
                    'region': server_name.upper()
                })
            else:
                # এপিআই থেকে যদি এরর মেসেজ আসে (যেমন: "Input UID your server")
                # সেই মেসেজটি সরাসরি ফ্রন্টএন্ডে পাঠানো হচ্ছে পপআপে দেখানোর জন্য
                error_msg = data.get('message') or data.get('error') or "BOLD! UID NOT FOUND BD"
                return jsonify({'status': 'error', 'message': error_msg})
        
        else:
            return jsonify({'status': 'error', 'message': "BOLD! UID NOT FOUND BD"})

    except Exception as e:
        return jsonify({'status': 'error', 'message': "API connection failed!"})


with app.app_context():
    db.create_all() # এটি গান বা ইউজার টেবিল না থাকলে তৈরি করে দিবে

if __name__ == '__main__':
    # ১. ম্যানেজার স্টার্ট করা
    manager = multiprocessing.Manager()
        
    # ৩. অ্যাপ রান করা
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
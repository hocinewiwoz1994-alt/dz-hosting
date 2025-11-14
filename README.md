VM Panel - Ready project
-----------------------
Files included:
- app.py (Flask app)
- vbox_helper_full.py (VirtualBox controller)
- db.py (SQLite simple DB)
- templates/ (Jinja2 templates)
- static/ (CSS + JS)
- config.py and .env.example
- requirements.txt

Usage:
1. Copy .env.example -> .env and fill values (ADMIN_PASS, VBOXMANAGE path, etc)
2. pip install -r requirements.txt
3. python app.py
4. Open http://localhost:5000/admin and login with ADMIN_USER / ADMIN_PASS

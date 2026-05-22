
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from functools import wraps
import os
from stock_engine import *
from auth_db import init_db, create_user, verify_user, get_user, seed_default_user

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-this-secret")
init_db()
if os.environ.get("DISABLE_DEFAULT_USER") != "1":
    seed_default_user()

def current_user():
    uid = session.get("user_id")
    return get_user(uid) if uid else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({"ok": False, "error": "login_required"}), 401
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/me")
def api_me():
    u = current_user()
    return jsonify({"ok": True, "logged_in": bool(u), "user": u})

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    res = create_user(data.get("username"), data.get("password"))
    if res.get("ok"):
        session["user_id"] = res["user_id"]
    return jsonify(res)

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    u = verify_user(data.get("username"), data.get("password"))
    if not u:
        return jsonify({"ok": False, "error": "ユーザー名またはパスワードが違います"}), 401
    session["user_id"] = u["id"]
    return jsonify({"ok": True, "user": u})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/dashboard")
@login_required
def api_dashboard():
    return jsonify(get_dashboard_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/holdings")
@login_required
def api_holdings():
    return jsonify(get_holdings_analysis_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/watchlist")
@login_required
def api_watchlist():
    return jsonify(get_watchlist_analysis_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/candidates")
@login_required
def api_candidates():
    return jsonify(get_candidates_user(
        current_user()["id"],
        limit=int(request.args.get("limit", 20)),
        mode=request.args.get("mode", "total"),
        force=request.args.get("force")=="1"
    ))

@app.route("/api/ai-candidates")
@login_required
def api_ai_candidates():
    return api_candidates()

@app.route("/api/screener")
@login_required
def api_screener():
    return jsonify(get_screener_user(current_user()["id"], filters=dict(request.args), force=request.args.get("force")=="1"))

@app.route("/api/report")
@login_required
def api_report():
    return jsonify(get_ai_report_user(current_user()["id"], code=request.args.get("code"), force=request.args.get("force")=="1"))


@app.route("/api/market-terminal")
@login_required
def api_market_terminal():
    return jsonify(get_market_terminal_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/prices")
@login_required
def api_prices():
    codes = request.args.get("codes","").split(",")
    uid = current_user()["id"]
    return jsonify([get_price_user(c, uid, force=request.args.get("force")=="1") for c in codes if str(c).strip()])

@app.route("/api/chart/<code>")
@login_required
def api_chart(code):
    return jsonify(get_chart(code, range_=request.args.get("range","3mo"), interval=request.args.get("interval","1d"), force=request.args.get("force")=="1"))

@app.route("/api/strategy/<code>")
@login_required
def api_strategy(code):
    ch = get_chart(code, range_=request.args.get("range","3mo"), interval=request.args.get("interval","1d"), force=request.args.get("force")=="1")
    return jsonify(ch.get("strategy") if ch.get("ok") else ch)

@app.route("/api/detail/<code>")
@login_required
def api_detail(code):
    return jsonify(analyze_user(code, current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/holding/add", methods=["POST"])
@login_required
def api_add_holding():
    data = request.get_json(force=True)
    return jsonify(add_holding_user(current_user()["id"], data.get("query",""), data.get("shares"), data.get("avg_price"), data.get("manual_price")))

@app.route("/api/holding/delete", methods=["POST"])
@login_required
def api_delete_holding():
    data = request.get_json(force=True)
    return jsonify(delete_holding_user(current_user()["id"], data.get("code","")))

@app.route("/api/watchlist/add", methods=["POST"])
@login_required
def api_add_watchlist():
    data = request.get_json(force=True)
    return jsonify(add_watchlist_user(current_user()["id"], data.get("query","")))

@app.route("/api/watchlist/delete", methods=["POST"])
@login_required
def api_delete_watchlist():
    data = request.get_json(force=True)
    return jsonify(delete_watchlist_user(current_user()["id"], data.get("code","")))

@app.route("/api/refresh", methods=["GET","POST"])
@login_required
def api_refresh():
    clear_cache()
    return jsonify({"ok": True, "message": "cache cleared", "dashboard": get_dashboard_user(current_user()["id"], force=True)})

@app.route("/api/reset-cache", methods=["POST"])
@login_required
def api_reset_cache():
    return jsonify(clear_cache())

@app.route("/api/debug/price/<code>")
@login_required
def api_debug_price(code):
    return jsonify(get_price_user(code, current_user()["id"], force=True))

@app.route("/api/debug/chart/<code>")
@login_required
def api_debug_chart(code):
    return jsonify(get_chart(code, range_=request.args.get("range","3mo"), force=True))

@app.route("/api/scan/start", methods=["GET","POST"])
@login_required
def api_scan_start():
    return jsonify(start_background_scan(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/scan/status")
@login_required
def api_scan_status():
    return jsonify({"ok": True, "status": get_scan_status()})


@app.route("/api/alerts")
@login_required
def api_alerts():
    return jsonify(get_alerts_user(current_user()["id"]))

@app.route("/api/alerts/add", methods=["POST"])
@login_required
def api_alert_add():
    data = request.get_json(force=True)
    return jsonify(add_alert_user(current_user()["id"], data.get("query", ""), data.get("condition_type", "price_above"), data.get("threshold"), data.get("note", "")))

@app.route("/api/alerts/delete", methods=["POST"])
@login_required
def api_alert_delete():
    data = request.get_json(force=True)
    return jsonify(delete_alert_user(current_user()["id"], data.get("id")))

@app.route("/api/alerts/toggle", methods=["POST"])
@login_required
def api_alert_toggle():
    data = request.get_json(force=True)
    return jsonify(toggle_alert_user(current_user()["id"], data.get("id"), data.get("enabled")))

@app.route("/api/alerts/evaluate", methods=["GET", "POST"])
@login_required
def api_alert_evaluate():
    return jsonify(evaluate_alerts_user(current_user()["id"], force=request.args.get("force")=="1"))


@app.route("/api/trades")
@login_required
def api_trades():
    return jsonify(get_trades_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/trades/add", methods=["POST"])
@login_required
def api_trade_add():
    data = request.get_json(force=True)
    return jsonify(add_trade_user(
        current_user()["id"],
        data.get("code") or data.get("query") or "",
        data.get("buy_date"),
        data.get("buy_price"),
        data.get("sell_date"),
        data.get("sell_price"),
        data.get("shares")
    ))

@app.route("/api/trades/delete", methods=["POST"])
@login_required
def api_trade_delete():
    data = request.get_json(force=True)
    return jsonify(delete_trade_user(current_user()["id"], data.get("id")))

@app.route("/api/my-patterns")
@login_required
def api_my_patterns():
    return jsonify(get_my_patterns_user(current_user()["id"], mode=request.args.get("mode", "yuto_swing"), force=request.args.get("force")=="1"))


@app.route("/api/watch-performance")
@login_required
def api_watch_performance():
    return jsonify(get_watch_performance_user(current_user()["id"], force=request.args.get("force")=="1"))

@app.route("/api/entry-check")
@login_required
def api_entry_check():
    return jsonify(get_entry_check_user(
        current_user()["id"],
        request.args.get("code") or request.args.get("query") or "",
        request.args.get("entry_price"),
        request.args.get("shares"),
        request.args.get("hold_days"),
        force=request.args.get("force")=="1"
    ))

@app.route("/api/entry-check", methods=["POST"])
@login_required
def api_entry_check_post():
    data=request.get_json(force=True)
    return jsonify(get_entry_check_user(
        current_user()["id"],
        data.get("code") or data.get("query") or "",
        data.get("entry_price"),
        data.get("shares"),
        data.get("hold_days"),
        force=data.get("force") is True
    ))

@app.route("/api/selftest")
def api_selftest():
    return jsonify({
        "ok": True,
        "auth": "enabled",
        "routes": ["/api/register","/api/login","/api/me","/api/logout","/api/holdings","/api/candidates"],
        "note": "ログイン後に個人別 holdings/watchlist をSQLiteに保存"
    })

@app.route("/api/free-data-core", methods=["POST"])
@login_required
def api_free_data_core():
    data = request.get_json(force=True)
    return jsonify(get_free_data_core_user(current_user()["id"], data.get("code") or ""))

@app.route("/api/trader-core", methods=["POST"])
@login_required
def api_trader_core():
    data = request.get_json(force=True)
    return jsonify(get_trader_core_user(
        current_user()["id"],
        data.get("code") or "",
        data.get("entry_price"),
        data.get("shares"),
        data.get("hold_days"),
        force=True
    ))

@app.route("/api/entry-chat", methods=["POST"])
@login_required
def api_entry_chat():
    data = request.get_json(force=True)
    return jsonify(get_entry_chat_user(
        current_user()["id"],
        data.get("code") or "",
        data.get("question") or "",
        data.get("entry_price"),
        data.get("shares"),
        data.get("hold_days"),
        force=True
    ))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8501)), debug=False)

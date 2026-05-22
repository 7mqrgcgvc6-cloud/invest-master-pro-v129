import os, re, time, math, sqlite3, random, socket
socket.setdefaulttimeout(float(os.environ.get("INVEST_HTTP_TIMEOUT", "0.8")))
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
import json

DB_PATH = os.environ.get("INVEST_DB_PATH", os.path.join(os.path.dirname(__file__), "database", "invest_master.db"))
_cache = {}

NAMES = {
    "3350":"メタプラネット", "4425":"Kudan", "6740":"ジャパンディスプレイ", "1909":"日本ドライケミカル",
    "5016":"JX金属", "7203":"トヨタ自動車", "8306":"三菱UFJ", "9101":"日本郵船", "8058":"三菱商事",
    "8411":"みずほFG", "5401":"日本製鉄", "1605":"INPEX", "9432":"NTT", "9433":"KDDI",
    "7011":"三菱重工業", "7012":"川崎重工業", "7013":"IHI", "6501":"日立製作所",
    "6526":"ソシオネクスト", "8035":"東京エレクトロン", "6857":"アドバンテスト", "6146":"ディスコ",
    "5803":"フジクラ", "5802":"住友電工", "9501":"東京電力HD", "9503":"関西電力",
    "3778":"さくらインターネット", "4816":"東映アニメーション", "5253":"カバー",
}
SEED_HOLDINGS = [("3350","メタプラネット",1100,304,None),("4425","Kudan",300,2674,None),("6740","ジャパンディスプレイ",558,67,None)]
SEED_WATCH = [("5016","JX金属"),("1909","日本ドライケミカル")]
CANDIDATE_CODES = [
    "3350","4425","6740","1909","5016","7203","8306","9101","8058","8411","5401","1605","9432","9433",
    "7011","7012","7013","6501","6526","8035","6857","6146","5803","5802","9501","9503","3778","5253"
]

# 無料ローカル版の材料データ。
# 将来、TDnet/RSS/ニュースAPIをつなぐ時は、この構造に流し込めばAIスコアへ反映される。
THEME_MAP = {
    "defense": {"label":"防衛・地政学", "macro":18, "codes":["1909","7011","7012","7013"]},
    "semiconductor": {"label":"半導体・AI", "macro":16, "codes":["6526","8035","6857","6146","5803","5802"]},
    "datacenter": {"label":"データセンター・電力", "macro":15, "codes":["3778","6501","5803","9501","9503","9432","9433"]},
    "rate_bank": {"label":"金利上昇メリット", "macro":12, "codes":["8306","8411"]},
    "weak_yen": {"label":"円安メリット", "macro":10, "codes":["7203","8058","9101","1605","5401"]},
    "crypto": {"label":"ビットコイン関連", "macro":10, "codes":["3350"]},
    "ai_robotics": {"label":"AI・自動運転", "macro":14, "codes":["4425","6501","7203"]},
}

CATALYST_DATA = {
    "1909": {"earnings":"防災・防衛関連需要を評価", "news":["防衛・防災テーマ", "インフラ老朽化対策"], "earnings_score":16, "news_score":14},
    "7011": {"earnings":"受注残・防衛関連テーマを評価", "news":["防衛費拡大", "宇宙・原子力・ガスタービン"], "earnings_score":18, "news_score":18},
    "7012": {"earnings":"防衛・航空・二輪回復テーマ", "news":["防衛関連", "円安メリット"], "earnings_score":14, "news_score":15},
    "7013": {"earnings":"航空エンジン・防衛テーマ", "news":["防衛関連", "航空需要回復"], "earnings_score":14, "news_score":15},
    "6526": {"earnings":"AI半導体テーマを評価", "news":["AI半導体", "先端SoC"], "earnings_score":13, "news_score":17},
    "8035": {"earnings":"半導体製造装置の代表格", "news":["AI投資", "半導体サイクル"], "earnings_score":15, "news_score":16},
    "6857": {"earnings":"生成AI向けテスター需要", "news":["AI半導体", "HBM関連"], "earnings_score":16, "news_score":16},
    "6146": {"earnings":"半導体装置・高収益企業", "news":["AI半導体", "装置需要"], "earnings_score":16, "news_score":15},
    "5803": {"earnings":"データセンター光配線テーマ", "news":["生成AI", "データセンター"], "earnings_score":17, "news_score":17},
    "5802": {"earnings":"電線・電力インフラテーマ", "news":["データセンター", "送電網投資"], "earnings_score":14, "news_score":14},
    "6501": {"earnings":"電力・データセンター・AIインフラ", "news":["生成AIインフラ", "電力網"], "earnings_score":16, "news_score":16},
    "3778": {"earnings":"国産クラウド・AI計算基盤テーマ", "news":["データセンター", "国策クラウド"], "earnings_score":12, "news_score":18},
    "8306": {"earnings":"金利上昇メリット", "news":["日銀正常化", "銀行株"], "earnings_score":14, "news_score":12},
    "8411": {"earnings":"金利上昇メリット", "news":["日銀正常化", "銀行株"], "earnings_score":13, "news_score":12},
    "8058": {"earnings":"資源・円安・株主還元", "news":["総合商社", "資源価格"], "earnings_score":15, "news_score":12},
    "1605": {"earnings":"資源高・円安メリット", "news":["原油・天然ガス", "円安"], "earnings_score":13, "news_score":12},
    "3350": {"earnings":"BTC価格連動テーマ", "news":["ビットコイン", "暗号資産財務戦略"], "earnings_score":8, "news_score":16},
    "4425": {"earnings":"空間認識AIテーマ", "news":["AI", "自動運転・ロボット"], "earnings_score":8, "news_score":15},
    "5016": {"earnings":"非鉄・半導体素材テーマ", "news":["銅価格", "半導体材料"], "earnings_score":12, "news_score":12},
}

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def normalize_code(q):
    q = str(q or "").strip()
    m = re.search(r"(\d{4})", q)
    if m: return m.group(1)
    for c,n in NAMES.items():
        if q.lower() in n.lower() or n.lower() in q.lower(): return c
    return q[:4] if q else ""

def name_for(code):
    return NAMES.get(str(code), f"銘柄{code}")

def clear_cache():
    _cache.clear()
    return {"ok": True, "message": "cache cleared"}

def _http_json(url, timeout=1.2):
    req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _cache_get(key, ttl=600):
    v = _cache.get(key)
    if v and time.time() - v[0] < ttl: return v[1]
    return None

def _cache_set(key, val):
    _cache[key] = (time.time(), val)
    return val

def _safe_float(v):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)): return None
        return float(v)
    except Exception:
        return None

def _fallback_price(code):
    base = {"3350":302,"4425":1900,"6740":19,"1909":3100,"5016":930,"7203":2900,"8306":1900,"9101":5000,"8058":3000,"8411":3900,"5401":3200,"1605":2000,"9432":155,"9433":4850}.get(str(code), 1000)
    rnd = random.Random(str(code)+datetime.now().strftime("%Y%m%d%H"))
    price = round(base * (1 + rnd.uniform(-0.025,0.025)), 1)
    prev = round(price * (1 - rnd.uniform(-0.02,0.02)), 1)
    return price, prev, "demo_fallback"

def get_price(code, force=False):
    code = normalize_code(code)
    ck = f"price:{code}"
    if not force and (cached := _cache_get(ck, 300)): return cached
    price = prev = None; source = "yahoo_finance_jp"
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.T?range=5d&interval=1d"
        j = _http_json(url)
        res = j["chart"]["result"][0]
        meta = res.get("meta", {})
        price = _safe_float(meta.get("regularMarketPrice"))
        closes = [c for c in res.get("indicators",{}).get("quote",[{}])[0].get("close",[]) if c is not None]
        if closes:
            if price is None: price = _safe_float(closes[-1])
            prev = _safe_float(closes[-2] if len(closes) >= 2 else closes[-1])
    except Exception:
        price, prev, source = _fallback_price(code)
    change = None if price is None or prev in (None,0) else price-prev
    change_pct = None if change is None or prev in (None,0) else change/prev*100
    return _cache_set(ck, {"ok": True, "code": code, "name": name_for(code), "price": price, "prev_close": prev, "change": change, "change_pct": change_pct, "price_source": source, "updated_at": datetime.now().strftime("%H:%M")})

def get_price_user(code, uid=None, force=False):
    code = normalize_code(code)
    manual = None
    if uid:
        try:
            with _conn() as con:
                r = con.execute("SELECT manual_price FROM holdings WHERE user_id=? AND code=?", (uid, code)).fetchone()
                manual = _safe_float(r["manual_price"]) if r else None
        except Exception: pass
    p = get_price(code, force)
    if manual:
        p = dict(p); p["price"] = manual; p["price_source"] = "manual"
    return p

def _series_fallback(code, days=150, interval="1d"):
    now = datetime.now(); price = get_price(code).get("price") or 1000
    rnd = random.Random(str(code)+str(interval))
    arr=[]; v=price*(1-rnd.uniform(-.1,.1))
    intraday = str(interval).endswith("m") or str(interval).endswith("h")
    step_minutes = {"5m":5,"15m":15,"30m":30,"60m":60,"1h":60}.get(str(interval), 1440)
    for i in range(days):
        dt = now - (timedelta(minutes=step_minutes*(days-i)) if intraday else timedelta(days=days-i))
        drift = rnd.uniform(-.006,.007) if intraday else rnd.uniform(-.025,.027)
        o = v; c=max(1,o*(1+drift)); h=max(o,c)*(1+rnd.uniform(0,.008 if intraday else .018)); l=min(o,c)*(1-rnd.uniform(0,.008 if intraday else .018)); vol=int(rnd.uniform(20_000,900_000) if intraday else rnd.uniform(80_000,3_000_000))
        fmt="%m-%d %H:%M" if intraday else "%Y-%m-%d"
        arr.append({"time":dt.strftime(fmt),"open":round(o,2),"high":round(h,2),"low":round(l,2),"close":round(c,2),"volume":vol})
        v=c
    return arr

def _download_series(code, range_="3mo", interval="1d", force=False):
    interval = str(interval or "1d")
    range_ = str(range_ or "3mo")
    # Yahoo Financeで安定しやすい組み合わせ。取れない足はfallbackで画面を止めない。
    default_days = {"5d":260,"1mo":260,"3mo":100,"6mo":160,"1y":260,"5y":260,"10y":260,"max":260}.get(range_,160)
    ck=f"chart:{code}:{range_}:{interval}"
    if not force and (cached := _cache_get(ck, 900)): return cached
    try:
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.T?range={range_}&interval={interval}"
        j=_http_json(url)
        res=j["chart"]["result"][0]; ts=res.get("timestamp",[]); q=res["indicators"]["quote"][0]
        arr=[]
        intraday = interval.endswith("m") or interval in ("60m","1h")
        fmt = "%m-%d %H:%M" if intraday else "%Y-%m-%d"
        for i,t in enumerate(ts):
            if q["close"][i] is None: continue
            close=_safe_float(q["close"][i]);
            if close is None: continue
            op=_safe_float(q["open"][i]) or close; hi=_safe_float(q["high"][i]) or close; lo=_safe_float(q["low"][i]) or close
            arr.append({"time":datetime.fromtimestamp(t).strftime(fmt),"open":round(op,2),"high":round(hi,2),"low":round(lo,2),"close":round(close,2),"volume":int(q.get("volume",[0]*len(ts))[i] or 0)})
        if len(arr) < 20: raise RuntimeError("short chart")
    except Exception:
        arr=_series_fallback(code, default_days, interval); source="demo_fallback"
    else:
        source=f"yahoo_finance_jp:{interval}"
    return _cache_set(ck, (arr, source))

def _sma(vals,n):
    out=[]
    for i in range(len(vals)):
        out.append(None if i+1<n else sum(vals[i+1-n:i+1])/n)
    return out

def _ema(vals,n):
    out=[]; k=2/(n+1); e=None
    for v in vals:
        e = v if e is None else v*k + e*(1-k)
        out.append(e)
    return out

def _rsi(vals,n=14):
    out=[None]*len(vals); gains=[]; losses=[]
    for i in range(1,len(vals)):
        diff=vals[i]-vals[i-1]; gains.append(max(diff,0)); losses.append(max(-diff,0))
        if i>=n:
            ag=sum(gains[-n:])/n; al=sum(losses[-n:])/n
            out[i]=100 if al==0 else 100-(100/(1+ag/al))
    return out

def _indicators(arr):
    closes=[x["close"] for x in arr]
    sma25=_sma(closes,25); sma75=_sma(closes,75); sma200=_sma(closes,200); rsi=_rsi(closes)
    ema12=_ema(closes,12); ema26=_ema(closes,26); macd=[a-b for a,b in zip(ema12,ema26)]; sig=_ema(macd,9)
    cum_pv=0; cum_vol=0
    for i,x in enumerate(arr):
        x["sma25"] = round(sma25[i],2) if sma25[i] else None
        x["sma75"] = round(sma75[i],2) if sma75[i] else None
        x["sma200"] = round(sma200[i],2) if sma200[i] else None
        vol=x.get("volume") or 0
        typical=((x.get("high") or x["close"])+(x.get("low") or x["close"])+x["close"])/3
        cum_pv += typical*vol; cum_vol += vol
        x["vwap"] = round(cum_pv/cum_vol,2) if cum_vol else None
        if i>=20:
            win=closes[i-19:i+1]; mid=sum(win)/20; sd=(sum((v-mid)**2 for v in win)/20)**0.5
            x["bb_mid"]=round(mid,2); x["bb_upper"]=round(mid+2*sd,2); x["bb_lower"]=round(mid-2*sd,2)
        else: x["bb_mid"]=x["bb_upper"]=x["bb_lower"]=None
        x["rsi14"] = round(rsi[i],2) if rsi[i] else None
        x["macd"] = round(macd[i],3) if macd[i] is not None else None
        x["macd_signal"] = round(sig[i],3) if sig[i] is not None else None
    return arr

def _strategy(arr):
    last=arr[-1]; closes=[x["close"] for x in arr[-25:]]; price=last["close"]
    support=round(min(closes),1); resistance=round(max(closes),1); rsi=last.get("rsi14")
    loss=round(support*0.97,1); tp1=round(resistance*1.03,1); tp2=round(resistance*1.10,1)
    status="様子見"
    if rsi is not None and rsi<35 and price<=support*1.05: status="反発狙い"
    elif price>resistance*.98 and (last.get("macd") or 0)>(last.get("macd_signal") or 0): status="上抜け監視"
    elif rsi is not None and rsi>72: status="過熱注意"
    return {"status":status,"support":support,"resistance":resistance,"buy_zone":f"{support}〜{round(support*1.04,1)}円","take_profit_1":f"{tp1}円","take_profit_2":f"{tp2}円","loss_cut":f"{loss}円","rsi14":rsi,"volume_ratio":round((last.get("volume") or 1)/(sum(x.get("volume") or 1 for x in arr[-20:])/20),2),"reason":f"支持線{support}円、抵抗線{resistance}円。RSIは{rsi or '—'}。MACDと移動平均の向きで売買判断。"}

def _evals(per,pbr,roe,dy,rsi=None,vol=None):
    def e(label,color): return {"label":label,"color":color}
    return {"per": e("割安" if per and per<=10 else "基準外", "red" if per and per<=10 else "green"),
            "pbr": e("割安" if pbr and pbr<=0.8 else "基準外", "red" if pbr and pbr<=0.8 else "green"),
            "roe": e("強い" if roe and roe>=30 else "普通", "red" if roe and roe>=30 else "orange"),
            "dy": e("高配当" if dy and dy>=4.2 else "普通", "red" if dy and dy>=4.2 else "orange"),
            "rsi": e("売られすぎ" if rsi and rsi<35 else "通常", "red" if rsi and rsi<35 else "orange"),
            "vol": e("出来高増" if vol and vol>=1.5 else "通常", "red" if vol and vol>=1.5 else "orange")}


def _theme_analysis(code):
    code = str(code)
    tags = []
    macro_score = 0
    for _, item in THEME_MAP.items():
        if code in item["codes"]:
            tags.append(item["label"])
            macro_score += item["macro"]
    # テーマが多すぎる銘柄が過剰加点にならないよう上限
    return tags, min(35, macro_score)

def _catalyst_analysis(code):
    code = str(code)
    data = CATALYST_DATA.get(code, {})
    tags, macro_score = _theme_analysis(code)
    earnings_score = int(data.get("earnings_score", 0))
    news_score = int(data.get("news_score", 0))
    news = list(data.get("news", []))
    earnings = data.get("earnings", "目立つ決算材料は未登録")
    catalyst_score = min(100, earnings_score + news_score + macro_score)
    reasons = []
    if earnings_score:
        reasons.append(f"良決算/業績材料 +{earnings_score}")
    if news_score:
        reasons.append(f"ニュース材料 +{news_score}")
    if macro_score:
        reasons.append(f"世界情勢テーマ +{macro_score}")
    reason = " / ".join(reasons) if reasons else "材料スコアは低め。テクニカル・割安性中心で判定。"
    return {
        "earnings_score": earnings_score,
        "news_score": news_score,
        "macro_score": macro_score,
        "catalyst_score": catalyst_score,
        "earnings_summary": earnings,
        "news_tags": news,
        "theme_tags": tags,
        "catalyst_reason": reason,
    }

def _score_breakdown(per, pbr, roe, dy, st, catalyst):
    value_score = 0
    if per and per <= 10: value_score += 12
    elif per and per <= 15: value_score += 6
    if pbr and pbr <= 0.8: value_score += 12
    elif pbr and pbr <= 1.5: value_score += 6
    if roe and roe >= 30: value_score += 12
    elif roe and roe >= 15: value_score += 6
    if dy and dy >= 4.2: value_score += 8
    elif dy and dy >= 3: value_score += 4

    technical_score = 0
    rsi = st.get("rsi14")
    vol = st.get("volume_ratio")
    if rsi is not None and 30 <= rsi <= 55: technical_score += 8
    elif rsi is not None and rsi < 30: technical_score += 5
    if vol and vol >= 1.5: technical_score += 8
    if st.get("status") in ("反発狙い", "上抜け監視"): technical_score += 8

    catalyst_points = round((catalyst.get("catalyst_score", 0) or 0) * 0.45)
    total = 35 + value_score + technical_score + catalyst_points
    return {
        "value_score": min(45, value_score),
        "technical_score": min(30, technical_score),
        "catalyst_points": catalyst_points,
        "total": min(99, total),
    }

def fundamentals(code):
    rnd=random.Random(str(code)); per=round(rnd.uniform(6,28),1); pbr=round(rnd.uniform(.4,3.5),2); roe=round(rnd.uniform(3,38),1); dy=round(rnd.uniform(0,5.2),2)
    return per,pbr,roe,dy

def get_chart(code, range_="3mo", interval="1d", force=False):
    code=normalize_code(code); arr,source=_download_series(code, range_, interval, force); arr=_indicators(arr); st=_strategy(arr)
    return {"ok":True,"code":code,"name":name_for(code),"source":source,"range":range_,"interval":interval,"count":len(arr),"data":arr,"strategy":st}

def _sync_price_with_chart(price_obj, chart_obj):
    """一覧価格とチャート価格を一致させる。Yahooのprice APIがfallbackになった場合でも、
    チャートの最新足 close を現在値として優先する。"""
    p = dict(price_obj or {})
    data = (chart_obj or {}).get("data") or []
    if data:
        last = data[-1] or {}
        prev = data[-2] if len(data) >= 2 else last
        chart_price = _safe_float(last.get("close"))
        chart_prev = _safe_float(prev.get("close"))
        if chart_price is not None:
            old_price = p.get("price")
            p["price"] = chart_price
            p["prev_close"] = chart_prev
            p["change"] = None if chart_prev in (None, 0) else chart_price - chart_prev
            p["change_pct"] = None if p["change"] is None or chart_prev in (None, 0) else p["change"] / chart_prev * 100
            p["price_source"] = "chart_sync:" + str((chart_obj or {}).get("source", "chart"))
            p["price_synced_from_chart"] = True
            p["price_before_sync"] = old_price
    return p

def analyze_user(code, uid=None, force=False):
    code = normalize_code(code)
    # チャートを先に取得し、その最新終値を一覧の現在値にも使う
    ch = get_chart(code, force=True if force else False)
    p = get_price_user(code, uid, force)
    p = _sync_price_with_chart(p, ch)
    st = ch["strategy"]
    per, pbr, roe, dy = fundamentals(code)
    catalyst = _catalyst_analysis(code)
    breakdown = _score_breakdown(per, pbr, roe, dy, st, catalyst)
    ev = _evals(per, pbr, roe, dy, st.get("rsi14"), st.get("volume_ratio"))

    all_tags = (catalyst.get("theme_tags") or []) + (catalyst.get("news_tags") or [])
    theme_text = " / ".join(all_tags[:4]) if all_tags else "バリュー/テクニカル"

    ai_reason = (
        f"{catalyst.get('catalyst_reason')}。"
        f" 割安{breakdown['value_score']}点、テクニカル{breakdown['technical_score']}点、"
        f"材料加点{breakdown['catalyst_points']}点。"
        f" {catalyst.get('earnings_summary')}"
    )

    d = {
        **p,
        "per": per,
        "pbr": pbr,
        "roe": roe,
        "dividend_yield": dy,
        "evals": ev,
        "strategy": st,
        "ai_score": breakdown["total"],
        "score_breakdown": breakdown,
        "category": "AI候補",
        "theme": theme_text,
        "theme_tags": catalyst.get("theme_tags", []),
        "news_tags": catalyst.get("news_tags", []),
        "earnings_score": catalyst.get("earnings_score", 0),
        "news_score": catalyst.get("news_score", 0),
        "macro_score": catalyst.get("macro_score", 0),
        "catalyst_score": catalyst.get("catalyst_score", 0),
        "earnings_summary": catalyst.get("earnings_summary", ""),
        "catalyst_reason": catalyst.get("catalyst_reason", ""),
        "ai_reason": ai_reason,
    }

    if uid:
        with _conn() as con:
            h = con.execute("SELECT * FROM holdings WHERE user_id=? AND code=?", (uid, code)).fetchone()
        if h:
            d.update({"shares": h["shares"], "avg_price": h["avg_price"]})
            if d.get("price") is not None:
                d["value"] = d["price"] * h["shares"]
                d["cost"] = h["avg_price"] * h["shares"]
                d["profit"] = d["value"] - d["cost"]
                d["profit_pct"] = None if d["cost"] == 0 else d["profit"] / d["cost"] * 100
    return d

def _ensure_seed(uid):
    now=datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        if con.execute("SELECT COUNT(*) c FROM holdings WHERE user_id=?", (uid,)).fetchone()["c"]==0:
            for c,n,s,a,m in SEED_HOLDINGS:
                con.execute("INSERT OR IGNORE INTO holdings(user_id,code,name,shares,avg_price,manual_price,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uid,c,n,s,a,m,now,now))
        if con.execute("SELECT COUNT(*) c FROM watchlist WHERE user_id=?", (uid,)).fetchone()["c"]==0:
            for c,n in SEED_WATCH:
                con.execute("INSERT OR IGNORE INTO watchlist(user_id,code,name,created_at) VALUES(?,?,?,?)",(uid,c,n,now))
        con.commit()

def get_holdings_analysis_user(uid, force=False):
    _ensure_seed(uid)
    with _conn() as con: rows=con.execute("SELECT * FROM holdings WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    out=[]
    for r in rows:
        d=analyze_user(r["code"], uid, force); d.update({"shares":r["shares"],"avg_price":r["avg_price"],"manual_price":r["manual_price"]})
        if d.get("price") is not None:
            d["value"]=d["price"]*r["shares"]; d["cost"]=r["avg_price"]*r["shares"]; d["profit"]=d["value"]-d["cost"]; d["profit_pct"]=None if d["cost"]==0 else d["profit"]/d["cost"]*100
        out.append(d)
    return out

def get_watchlist_analysis_user(uid, force=False):
    _ensure_seed(uid)
    with _conn() as con: rows=con.execute("SELECT * FROM watchlist WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    return [analyze_user(r["code"], uid, force) for r in rows]

def get_candidates_user(uid, limit=20, mode="total", force=False):
    # AI候補一覧はチャート価格とズレないよう毎回チャート最新足で価格同期
    arr = [analyze_user(c, uid, True) for c in CANDIDATE_CODES]
    if mode == "value":
        arr.sort(key=lambda x: ((x.get("per") or 999) + (x.get("pbr") or 99) * 5, -(x.get("ai_score") or 0)))
    elif mode == "dividend":
        arr.sort(key=lambda x: (x.get("dividend_yield") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode == "growth":
        arr.sort(key=lambda x: (x.get("catalyst_score") or 0, x.get("news_score") or 0, x.get("ai_score") or 0), reverse=True)
    else:
        arr.sort(key=lambda x: (x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return arr[:int(limit or 20)]


def get_screener_user(uid, filters=None, force=False):
    """条件付きスクリーナー。無料版ではCANDIDATE_CODESを母集団にして、材料・指標・テクニカルで絞り込み。"""
    filters = filters or {}
    def fnum(k, default=None):
        try:
            v = filters.get(k, default)
            return default if v in (None, "") else float(v)
        except Exception:
            return default
    min_score = fnum("min_score", 0)
    max_per = fnum("max_per", None)
    max_pbr = fnum("max_pbr", None)
    min_roe = fnum("min_roe", None)
    min_dividend = fnum("min_dividend", None)
    min_material = fnum("min_material", 0)
    only_breakout = str(filters.get("breakout", "0")) == "1"
    only_oversold = str(filters.get("oversold", "0")) == "1"
    theme = str(filters.get("theme", "")).strip()
    mode = str(filters.get("mode", "total")).strip() or "total"
    limit = int(fnum("limit", 50) or 50)

    arr = [analyze_user(c, uid, True) for c in CANDIDATE_CODES]
    out = []
    for x in arr:
        st = x.get("strategy") or {}
        tags = [str(t) for t in (x.get("theme_tags") or []) + (x.get("news_tags") or [])]
        material = x.get("catalyst_score") or 0
        if (x.get("ai_score") or 0) < min_score: continue
        if max_per is not None and (x.get("per") is None or x.get("per") > max_per): continue
        if max_pbr is not None and (x.get("pbr") is None or x.get("pbr") > max_pbr): continue
        if min_roe is not None and (x.get("roe") is None or x.get("roe") < min_roe): continue
        if min_dividend is not None and (x.get("dividend_yield") is None or x.get("dividend_yield") < min_dividend): continue
        if material < min_material: continue
        if only_breakout and "上抜け" not in str(st.get("status", "")): continue
        if only_oversold and not (st.get("rsi14") is not None and st.get("rsi14") < 40): continue
        if theme and theme not in " ".join(tags) and theme not in str(x.get("theme", "")): continue
        out.append(x)

    if mode == "material":
        out.sort(key=lambda x: (x.get("catalyst_score") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode == "value":
        out.sort(key=lambda x: ((x.get("per") or 999) + (x.get("pbr") or 99) * 5, -(x.get("ai_score") or 0)))
    elif mode == "technical":
        out.sort(key=lambda x: ((x.get("score_breakdown") or {}).get("technical_score") or 0, x.get("ai_score") or 0), reverse=True)
    else:
        out.sort(key=lambda x: (x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return {"ok": True, "count": len(out), "filters": filters, "items": out[:limit], "updated_at": datetime.now().strftime("%H:%M")}

def get_ai_report_user(uid, code=None, force=False):
    """AIレポート用。銘柄指定なら1銘柄、未指定なら候補上位5件を文章化。"""
    items = [analyze_user(normalize_code(code), uid, force)] if code else get_candidates_user(uid, limit=5, mode="total", force=force)
    reports = []
    for x in items:
        st = x.get("strategy") or {}
        bd = x.get("score_breakdown") or {}
        tags = (x.get("theme_tags") or []) + (x.get("news_tags") or [])
        action = "様子見"
        if (x.get("ai_score") or 0) >= 80 and st.get("status") in ("上抜け監視", "反発狙い"):
            action = "買い候補上位"
        elif (x.get("ai_score") or 0) >= 70:
            action = "監視強め"
        elif (x.get("ai_score") or 0) < 55:
            action = "優先度低め"
        text = (
            f"{x.get('name')}（{x.get('code')}）はAIスコア{x.get('ai_score')}。"
            f"判断は『{action}』。材料点{x.get('catalyst_score')}、割安点{bd.get('value_score')}、"
            f"テクニカル点{bd.get('technical_score')}。"
            f"主な材料は{', '.join(tags[:5]) if tags else '特になし'}。"
            f"売買戦略は{st.get('status')}、買いゾーンは{st.get('buy_zone')}、"
            f"利確目安は{st.get('take_profit_1')} / {st.get('take_profit_2')}、損切り目安は{st.get('loss_cut')}。"
            f"理由：{x.get('ai_reason')} {st.get('reason')}"
        )
        reports.append({"code": x.get("code"), "name": x.get("name"), "action": action, "summary": text, "item": x})
    return {"ok": True, "updated_at": datetime.now().strftime("%H:%M"), "reports": reports}


def get_dashboard_user(uid, force=False):
    hs=get_holdings_analysis_user(uid, force); total=sum(x.get("value") or 0 for x in hs); cost=sum(x.get("cost") or 0 for x in hs); profit=total-cost
    today=sum(((x.get("price") or 0)-(x.get("prev_close") or x.get("price") or 0))*(x.get("shares") or 0) for x in hs)
    return {"ok":True,"total_value":total,"cost":cost,"profit":profit,"profit_pct":None if cost==0 else profit/cost*100,"today_profit":today,"today_pct":None if total==0 else today/total*100,"holdings_count":len(hs),"updated_at":datetime.now().strftime("%H:%M")}

def add_holding_user(uid, query, shares, avg_price, manual_price=None):
    code=normalize_code(query); 
    if not code: return {"ok":False,"error":"銘柄コードを入力"}
    now=datetime.now().isoformat(timespec="seconds")
    try: shares=float(shares or 0); avg=float(avg_price or 0); mp=_safe_float(manual_price)
    except Exception: return {"ok":False,"error":"株数・平均取得単価は数字で入力"}
    with _conn() as con:
        con.execute("INSERT INTO holdings(user_id,code,name,shares,avg_price,manual_price,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,code) DO UPDATE SET shares=excluded.shares,avg_price=excluded.avg_price,manual_price=excluded.manual_price,updated_at=excluded.updated_at", (uid,code,name_for(code),shares,avg,mp,now,now))
        con.commit()
    return {"ok":True,"code":code,"name":name_for(code)}

def delete_holding_user(uid, code):
    with _conn() as con: con.execute("DELETE FROM holdings WHERE user_id=? AND code=?", (uid, normalize_code(code))); con.commit()
    return {"ok":True}

def add_watchlist_user(uid, query):
    code=normalize_code(query)
    if not code: return {"ok":False,"error":"銘柄コードを入力"}
    now=datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO watchlist(user_id,code,name,created_at) VALUES(?,?,?,?)", (uid,code,name_for(code),now)); con.commit()
    return {"ok":True,"code":code,"name":name_for(code)}

def delete_watchlist_user(uid, code):
    with _conn() as con: con.execute("DELETE FROM watchlist WHERE user_id=? AND code=?", (uid, normalize_code(code))); con.commit()
    return {"ok":True}


# ===== v6.6 JPX CSV / live-news compatible overrides =====
UNIVERSE_CSV = os.environ.get("JPX_UNIVERSE_CSV", os.path.join(os.path.dirname(__file__), "jpx_universe.csv"))
_universe_loaded = False

def _ensure_universe_loaded():
    """jpx_universe.csvを母集団として読み込む。フルJPX CSVに差し替えれば全市場スキャンに拡張できる。"""
    global _universe_loaded, CANDIDATE_CODES, NAMES
    if _universe_loaded:
        return CANDIDATE_CODES
    rows = []
    try:
        import csv
        with open(UNIVERSE_CSV, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                code = normalize_code(r.get("code", ""))
                name = (r.get("name") or "").strip()
                if code and len(code) == 4:
                    rows.append((code, name or NAMES.get(code, f"銘柄{code}"), (r.get("theme") or "").strip()))
    except Exception:
        rows = []
    if rows:
        for code, name, theme in rows:
            NAMES[code] = name
            if theme and code not in CATALYST_DATA:
                # CSVテーマから最低限の材料タグを自動付与
                CATALYST_DATA[code] = {"earnings":"JPXユニバース登録銘柄", "news":[theme], "earnings_score":0, "news_score":6}
        CANDIDATE_CODES = [r[0] for r in rows]
    _universe_loaded = True
    return CANDIDATE_CODES

# 起動時にCSVを読み込む
_ensure_universe_loaded()

def _fetch_live_news_tags(code, name):
    """無料版の簡易ニュース取得。失敗時は空で返し、静的材料だけで動かす。"""
    ck = f"live_news:{code}"
    if (cached := _cache_get(ck, 3600)) is not None:
        return cached
    tags = []
    try:
        import xml.etree.ElementTree as ET
        from urllib.parse import quote
        # Yahoo!ニュース検索RSS。環境によって取得できない場合は静的データにフォールバック。
        q = quote(f"{name} {code} 決算 増配 上方修正 受注")
        url = f"https://news.yahoo.co.jp/rss/search?p={q}"
        req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req, timeout=float(os.environ.get("INVEST_HTTP_TIMEOUT", "0.8"))) as r:
            xml = r.read()
        root = ET.fromstring(xml)
        titles = [el.text or "" for el in root.findall('.//item/title')][:5]
        text = " ".join(titles)
        keyword_map = {
            "良決算":"決算", "上方修正":"上方修正", "増配":"増配", "自社株買い":"自社株買い",
            "大型受注":"受注", "提携":"提携", "防衛":"防衛", "半導体":"半導体",
            "AI":"AI", "データセンター":"データセンター", "円安":"円安", "金利":"金利",
        }
        for tag, kw in keyword_map.items():
            if kw in text and tag not in tags:
                tags.append(tag)
    except Exception:
        tags = []
    return _cache_set(ck, tags[:5])

def _catalyst_analysis(code):
    code = str(code)
    data = CATALYST_DATA.get(code, {})
    name = name_for(code)
    tags, macro_score = _theme_analysis(code)
    earnings_score = int(data.get("earnings_score", 0))
    news_score = int(data.get("news_score", 0))
    news = list(data.get("news", []))
    live_tags = _fetch_live_news_tags(code, name)
    if live_tags:
        for t in live_tags:
            if t not in news: news.append(t)
        news_score += min(12, len(live_tags) * 3)
    earnings = data.get("earnings", "目立つ決算材料は未登録")
    catalyst_score = min(100, earnings_score + news_score + macro_score)
    reasons = []
    if earnings_score:
        reasons.append(f"良決算/業績材料 +{earnings_score}")
    if news_score:
        reasons.append(f"ニュース材料 +{news_score}")
    if macro_score:
        reasons.append(f"世界情勢テーマ +{macro_score}")
    if live_tags:
        reasons.append("簡易ニュース取得あり")
    reason = " / ".join(reasons) if reasons else "材料スコアは低め。テクニカル・割安性中心で判定。"
    return {
        "earnings_score": earnings_score,
        "news_score": news_score,
        "macro_score": macro_score,
        "catalyst_score": catalyst_score,
        "earnings_summary": earnings,
        "news_tags": news,
        "live_news_tags": live_tags,
        "news_source": "YahooニュースRSS/登録材料" if live_tags else "登録材料/テーマCSV",
        "theme_tags": tags,
        "catalyst_reason": reason,
    }

def get_candidates_user(uid, limit=20, mode="total", force=False):
    codes = _ensure_universe_loaded()
    # 無料ローカル版では初回が重くなりすぎないよう、通常は上位候補用に先頭80件まで分析。
    # jpx_universe.csvを全銘柄版に差し替えた場合もスクリーナー側でlimit調整可能。
    scan_limit = int(os.environ.get("JPX_SCAN_LIMIT", "60"))
    arr = [analyze_user(c, uid, force) for c in codes[:scan_limit]]
    if mode == "value":
        arr.sort(key=lambda x: ((x.get("per") or 999) + (x.get("pbr") or 99) * 5, -(x.get("ai_score") or 0)))
    elif mode == "dividend":
        arr.sort(key=lambda x: (x.get("dividend_yield") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode == "growth":
        arr.sort(key=lambda x: (x.get("catalyst_score") or 0, x.get("news_score") or 0, x.get("ai_score") or 0), reverse=True)
    else:
        arr.sort(key=lambda x: (x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return arr[:int(limit or 20)]

def get_screener_user(uid, filters=None, force=False):
    """JPX CSV母集団対応スクリーナー。"""
    filters = filters or {}
    def fnum(k, default=None):
        try:
            v = filters.get(k, default)
            return default if v in (None, "") else float(v)
        except Exception:
            return default
    min_score = fnum("min_score", 0)
    max_per = fnum("max_per", None)
    max_pbr = fnum("max_pbr", None)
    min_roe = fnum("min_roe", None)
    min_dividend = fnum("min_dividend", None)
    min_material = fnum("min_material", 0)
    only_breakout = str(filters.get("breakout", "0")) == "1"
    only_oversold = str(filters.get("oversold", "0")) == "1"
    theme = str(filters.get("theme", "")).strip()
    mode = str(filters.get("mode", "total")).strip() or "total"
    limit = int(fnum("limit", 50) or 50)
    scan_limit = int(fnum("scan_limit", os.environ.get("JPX_SCAN_LIMIT", 60)) or 60)
    codes = _ensure_universe_loaded()[:scan_limit]
    arr = [analyze_user(c, uid, force) for c in codes]
    out = []
    for x in arr:
        st = x.get("strategy") or {}
        tags = [str(t) for t in (x.get("theme_tags") or []) + (x.get("news_tags") or [])]
        material = x.get("catalyst_score") or 0
        if (x.get("ai_score") or 0) < min_score: continue
        if max_per is not None and (x.get("per") is None or x.get("per") > max_per): continue
        if max_pbr is not None and (x.get("pbr") is None or x.get("pbr") > max_pbr): continue
        if min_roe is not None and (x.get("roe") is None or x.get("roe") < min_roe): continue
        if min_dividend is not None and (x.get("dividend_yield") is None or x.get("dividend_yield") < min_dividend): continue
        if material < min_material: continue
        if only_breakout and "上抜け" not in str(st.get("status", "")): continue
        if only_oversold and not (st.get("rsi14") is not None and st.get("rsi14") < 40): continue
        if theme and theme not in " ".join(tags) and theme not in str(x.get("theme", "")): continue
        out.append(x)
    if mode == "material":
        out.sort(key=lambda x: (x.get("catalyst_score") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode == "value":
        out.sort(key=lambda x: ((x.get("per") or 999) + (x.get("pbr") or 99) * 5, -(x.get("ai_score") or 0)))
    elif mode == "technical":
        out.sort(key=lambda x: ((x.get("score_breakdown") or {}).get("technical_score") or 0, x.get("ai_score") or 0), reverse=True)
    else:
        out.sort(key=lambda x: (x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return {"ok": True, "count": len(out), "scanned": len(codes), "universe_total": len(_ensure_universe_loaded()), "filters": filters, "items": out[:limit], "updated_at": datetime.now().strftime("%H:%M")}

def get_ai_report_user(uid, code=None, force=False):
    items = [analyze_user(normalize_code(code), uid, force)] if code else get_candidates_user(uid, limit=5, mode="total", force=force)
    reports = []
    for x in items:
        st = x.get("strategy") or {}
        bd = x.get("score_breakdown") or {}
        tags = (x.get("theme_tags") or []) + (x.get("news_tags") or [])
        action = "様子見"
        if (x.get("ai_score") or 0) >= 80 and st.get("status") in ("上抜け監視", "反発狙い"):
            action = "買い候補上位"
        elif (x.get("ai_score") or 0) >= 70:
            action = "監視強め"
        elif (x.get("ai_score") or 0) < 55:
            action = "優先度低め"
        text = (
            f"{x.get('name')}（{x.get('code')}）はAIスコア{x.get('ai_score')}。判断は『{action}』。"
            f"材料スコア{x.get('catalyst_score')}点、割安{bd.get('value_score')}点、テクニカル{bd.get('technical_score')}点。"
            f"主な材料は{', '.join(tags[:6]) if tags else '特になし'}。ニュース元は{x.get('news_source','登録材料')}。"
            f"売買戦略は{st.get('status')}、買いゾーンは{st.get('buy_zone')}、利確目安は{st.get('take_profit_1')} / {st.get('take_profit_2')}、損切り目安は{st.get('loss_cut')}。"
            f"理由：{x.get('ai_reason')} {st.get('reason')}"
        )
        reports.append({"code": x.get("code"), "name": x.get("name"), "action": action, "summary": text, "item": x})
    return {"ok": True, "updated_at": datetime.now().strftime("%H:%M"), "reports": reports}


# ===== v6.7 起動高速化 / 永続キャッシュ / 非同期スキャン =====
# 目的：アプリ起動時にYahoo/ニュース/チャート取得を一気に走らせず、前回結果を即表示して裏で更新する。
import threading

CACHE_DIR = os.environ.get("INVEST_CACHE_DIR", os.path.join(os.path.dirname(__file__), "database", "cache"))
os.makedirs(CACHE_DIR, exist_ok=True)
SCAN_CACHE_FILE = os.path.join(CACHE_DIR, "scan_results.json")
PRICE_CACHE_FILE = os.path.join(CACHE_DIR, "price_cache.json")
SCAN_TTL_SECONDS = int(os.environ.get("INVEST_SCAN_CACHE_TTL", str(60 * 60 * 6)))
PRICE_TTL_SECONDS = int(os.environ.get("INVEST_PRICE_CACHE_TTL", str(60 * 15)))
FAST_SCAN_LIMIT = int(os.environ.get("JPX_SCAN_LIMIT", "60"))
_scan_lock = threading.Lock()
_scan_state = {"running": False, "started_at": None, "finished_at": None, "progress": 0, "total": 0, "message": "待機中", "last_error": None}

# 元の重い分析関数を退避。詳細画面や裏スキャンではこれを使う。
_analyze_user_full_v67 = analyze_user
_get_candidates_full_v67 = get_candidates_user
_get_screener_full_v67 = get_screener_user
_get_ai_report_full_v67 = get_ai_report_user


def _json_read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _json_write(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _now_ts():
    return time.time()


def _cache_age_seconds(payload):
    try:
        return max(0, int(_now_ts() - float(payload.get("created_ts", 0))))
    except Exception:
        return 10**9


def _price_disk_get(code):
    data = _json_read(PRICE_CACHE_FILE, {})
    item = data.get(str(code))
    if item and _cache_age_seconds(item) <= PRICE_TTL_SECONDS:
        return item.get("value")
    return None


def _price_disk_set(code, value):
    data = _json_read(PRICE_CACHE_FILE, {})
    data[str(code)] = {"created_ts": _now_ts(), "value": value}
    _json_write(PRICE_CACHE_FILE, data)


def get_price_quick(code, uid=None):
    """起動用の超高速価格取得。ネットには出ず、永続キャッシュ→デモ価格の順で返す。"""
    code = normalize_code(code)
    cached = _price_disk_get(code)
    if cached:
        # 保有銘柄の手入力価格だけは反映
        if uid:
            try:
                with _conn() as con:
                    r = con.execute("SELECT manual_price FROM holdings WHERE user_id=? AND code=?", (uid, code)).fetchone()
                    mp = _safe_float(r["manual_price"]) if r else None
                if mp:
                    cached = dict(cached); cached["price"] = mp; cached["price_source"] = "manual"
            except Exception:
                pass
        return cached
    price, prev, source = _fallback_price(code)
    change = None if price is None or prev in (None,0) else price-prev
    change_pct = None if change is None or prev in (None,0) else change/prev*100
    val = {"ok": True, "code": code, "name": name_for(code), "price": price, "prev_close": prev, "change": change, "change_pct": change_pct, "price_source": "quick_" + source, "updated_at": datetime.now().strftime("%H:%M")}
    _price_disk_set(code, val)
    return val


def _quick_strategy(code, price):
    rnd = random.Random("quick_strategy:" + str(code))
    price = float(price or 1000)
    support = round(price * rnd.uniform(0.90, 0.97), 1)
    resistance = round(price * rnd.uniform(1.04, 1.13), 1)
    rsi = round(rnd.uniform(32, 68), 1)
    vol = round(rnd.uniform(0.8, 2.4), 2)
    status = "様子見"
    if rsi < 40:
        status = "反発狙い"
    elif vol >= 1.6 and price >= support * 1.04:
        status = "上抜け監視"
    return {"status": status, "support": support, "resistance": resistance, "buy_zone": f"{support}〜{round(support*1.04,1)}円", "take_profit_1": f"{round(resistance*1.03,1)}円", "take_profit_2": f"{round(resistance*1.10,1)}円", "loss_cut": f"{round(support*0.97,1)}円", "rsi14": rsi, "volume_ratio": vol, "reason": f"高速判定。支持線{support}円、抵抗線{resistance}円、RSI{rsi}、出来高{vol}倍。詳細画面では実チャートで再計算。"}



def _catalyst_analysis_light(code):
    """高速版材料判定。ニュースRSSにはアクセスせず、登録材料・テーマCSVだけを使う。"""
    code = str(code)
    data = CATALYST_DATA.get(code, {})
    tags, macro_score = _theme_analysis(code)
    earnings_score = int(data.get("earnings_score", 0))
    news_score = int(data.get("news_score", 0))
    news = list(data.get("news", []))
    earnings = data.get("earnings", "目立つ決算材料は未登録")
    catalyst_score = min(100, earnings_score + news_score + macro_score)
    reasons = []
    if earnings_score: reasons.append(f"良決算/業績材料 +{earnings_score}")
    if news_score: reasons.append(f"ニュース材料 +{news_score}")
    if macro_score: reasons.append(f"世界情勢テーマ +{macro_score}")
    reason = " / ".join(reasons) if reasons else "材料スコアは低め。テクニカル・割安性中心で判定。"
    return {"earnings_score": earnings_score, "news_score": news_score, "macro_score": macro_score, "catalyst_score": catalyst_score, "earnings_summary": earnings, "news_tags": news, "live_news_tags": [], "news_source": "登録材料/テーマCSV", "theme_tags": tags, "catalyst_reason": reason}

def analyze_user_light(code, uid=None):
    """一覧・起動用。ネット/チャート取得なしで材料・指標・簡易テクニカルを計算。"""
    code = normalize_code(code)
    p = get_price_quick(code, uid)
    st = _quick_strategy(code, p.get("price"))
    per, pbr, roe, dy = fundamentals(code)
    catalyst = _catalyst_analysis_light(code)
    breakdown = _score_breakdown(per, pbr, roe, dy, st, catalyst)
    ev = _evals(per, pbr, roe, dy, st.get("rsi14"), st.get("volume_ratio"))
    tags = (catalyst.get("theme_tags") or []) + (catalyst.get("news_tags") or [])
    theme_text = " / ".join(tags[:4]) if tags else "バリュー/テクニカル"
    d = {**p, "per": per, "pbr": pbr, "roe": roe, "dividend_yield": dy, "evals": ev, "strategy": st, "ai_score": breakdown["total"], "score_breakdown": breakdown, "category": "AI候補", "theme": theme_text, "theme_tags": catalyst.get("theme_tags", []), "news_tags": catalyst.get("news_tags", []), "earnings_score": catalyst.get("earnings_score", 0), "news_score": catalyst.get("news_score", 0), "macro_score": catalyst.get("macro_score", 0), "catalyst_score": catalyst.get("catalyst_score", 0), "earnings_summary": catalyst.get("earnings_summary", ""), "catalyst_reason": catalyst.get("catalyst_reason", ""), "news_source": catalyst.get("news_source", "登録材料/テーマCSV"), "ai_reason": f"{catalyst.get('catalyst_reason')}。割安{breakdown['value_score']}点、テクニカル{breakdown['technical_score']}点、材料加点{breakdown['catalyst_points']}点。{catalyst.get('earnings_summary')}", "fast_mode": True}
    if uid:
        try:
            with _conn() as con:
                h = con.execute("SELECT * FROM holdings WHERE user_id=? AND code=?", (uid, code)).fetchone()
            if h:
                d.update({"shares": h["shares"], "avg_price": h["avg_price"]})
                if d.get("price") is not None:
                    d["value"] = d["price"] * h["shares"]
                    d["cost"] = h["avg_price"] * h["shares"]
                    d["profit"] = d["value"] - d["cost"]
                    d["profit_pct"] = None if d["cost"] == 0 else d["profit"] / d["cost"] * 100
        except Exception:
            pass
    return d


def _sort_items(arr, mode="total"):
    if mode == "value":
        arr.sort(key=lambda x: ((x.get("per") or 999) + (x.get("pbr") or 99) * 5, -(x.get("ai_score") or 0)))
    elif mode == "dividend":
        arr.sort(key=lambda x: (x.get("dividend_yield") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode in ("growth", "material"):
        arr.sort(key=lambda x: (x.get("catalyst_score") or 0, x.get("news_score") or 0, x.get("ai_score") or 0), reverse=True)
    elif mode == "technical":
        arr.sort(key=lambda x: ((x.get("score_breakdown") or {}).get("technical_score") or 0, x.get("ai_score") or 0), reverse=True)
    else:
        arr.sort(key=lambda x: (x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return arr


def _load_scan_cache():
    payload = _json_read(SCAN_CACHE_FILE, {})
    if not isinstance(payload, dict):
        return {}
    return payload


def _save_scan_cache(items):
    payload = {"created_ts": _now_ts(), "updated_at": datetime.now().strftime("%H:%M"), "items": items, "count": len(items), "universe_total": len(_ensure_universe_loaded())}
    _json_write(SCAN_CACHE_FILE, payload)
    return payload


def _scan_worker(uid, force=False):
    global _scan_state
    codes = _ensure_universe_loaded()[:FAST_SCAN_LIMIT]
    with _scan_lock:
        _scan_state.update({"running": True, "started_at": datetime.now().strftime("%H:%M:%S"), "finished_at": None, "progress": 0, "total": len(codes), "message": "裏スキャン中", "last_error": None})
    items = []
    try:
        for i, code in enumerate(codes, start=1):
            try:
                item = _analyze_user_full_v67(code, uid, force)
                # フル取得できた価格を永続キャッシュへ保存
                if item.get("price") is not None:
                    _price_disk_set(code, {k: item.get(k) for k in ["ok","code","name","price","prev_close","change","change_pct","price_source","updated_at"]})
                items.append(item)
            except Exception:
                items.append(analyze_user_light(code, uid))
            if i % 5 == 0 or i == len(codes):
                _save_scan_cache(_sort_items(list(items), "total"))
                with _scan_lock:
                    _scan_state.update({"progress": i, "message": f"裏スキャン中 {i}/{len(codes)}"})
        _save_scan_cache(_sort_items(items, "total"))
        with _scan_lock:
            _scan_state.update({"running": False, "finished_at": datetime.now().strftime("%H:%M:%S"), "progress": len(codes), "message": "更新完了"})
    except Exception as e:
        with _scan_lock:
            _scan_state.update({"running": False, "finished_at": datetime.now().strftime("%H:%M:%S"), "last_error": str(e), "message": "裏スキャン失敗"})


def start_background_scan(uid, force=False):
    with _scan_lock:
        if _scan_state.get("running"):
            return {"ok": True, "started": False, "status": dict(_scan_state)}
        t = threading.Thread(target=_scan_worker, args=(uid, force), daemon=True)
        t.start()
        _scan_state.update({"running": True, "message": "裏スキャン開始"})
    return {"ok": True, "started": True, "status": get_scan_status()}


def get_scan_status():
    payload = _load_scan_cache()
    with _scan_lock:
        st = dict(_scan_state)
    st["cache_age_sec"] = _cache_age_seconds(payload) if payload else None
    st["cache_count"] = len(payload.get("items", [])) if payload else 0
    st["cache_updated_at"] = payload.get("updated_at") if payload else None
    st["universe_total"] = len(_ensure_universe_loaded())
    return st


def _cached_or_light_items(uid, force=False):
    if force:
        start_background_scan(uid, force=True)
    payload = _load_scan_cache()
    if payload and payload.get("items") and _cache_age_seconds(payload) <= SCAN_TTL_SECONDS:
        start_background_scan(uid, force=False)  # 古くなくても裏で差分更新。既に走っていれば無視。
        return list(payload.get("items") or []), "disk_cache", payload
    # キャッシュがない初回でも、ネットに行かず即席候補を返す
    codes = _ensure_universe_loaded()[:FAST_SCAN_LIMIT]
    items = [analyze_user_light(c, uid) for c in codes]
    _save_scan_cache(_sort_items(list(items), "total"))
    start_background_scan(uid, force=False)
    return items, "quick_first_load", _load_scan_cache()


def analyze_user(code, uid=None, force=False):
    # 詳細ページ・チャート起点ではforce=Trueが来るためフル分析。通常APIは下の一覧関数でlight/cacheを使う。
    return _analyze_user_full_v67(code, uid, force)


def get_holdings_analysis_user(uid, force=False):
    _ensure_seed(uid)
    with _conn() as con:
        rows = con.execute("SELECT * FROM holdings WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    out=[]
    for r in rows:
        d = _analyze_user_full_v67(r["code"], uid, force) if force else analyze_user_light(r["code"], uid)
        d.update({"shares":r["shares"],"avg_price":r["avg_price"],"manual_price":r["manual_price"]})
        if d.get("price") is not None:
            d["value"]=d["price"]*r["shares"]; d["cost"]=r["avg_price"]*r["shares"]; d["profit"]=d["value"]-d["cost"]; d["profit_pct"]=None if d["cost"]==0 else d["profit"]/d["cost"]*100
        out.append(d)
    if not force:
        start_background_scan(uid, force=False)
    return out


def get_watchlist_analysis_user(uid, force=False):
    _ensure_seed(uid)
    with _conn() as con:
        rows=con.execute("SELECT * FROM watchlist WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    out = [(_analyze_user_full_v67(r["code"], uid, force) if force else analyze_user_light(r["code"], uid)) for r in rows]
    if not force:
        start_background_scan(uid, force=False)
    return out


def get_candidates_user(uid, limit=20, mode="total", force=False):
    items, source, payload = _cached_or_light_items(uid, force=force)
    arr = _sort_items(list(items), mode)
    return arr[:int(limit or 20)]


def get_screener_user(uid, filters=None, force=False):
    filters = filters or {}
    def fnum(k, default=None):
        try:
            v = filters.get(k, default)
            return default if v in (None, "") else float(v)
        except Exception:
            return default
    min_score = fnum("min_score", 0); max_per = fnum("max_per", None); max_pbr = fnum("max_pbr", None)
    min_roe = fnum("min_roe", None); min_dividend = fnum("min_dividend", None); min_material = fnum("min_material", 0)
    only_breakout = str(filters.get("breakout", "0")) == "1"; only_oversold = str(filters.get("oversold", "0")) == "1"
    theme = str(filters.get("theme", "")).strip(); mode = str(filters.get("mode", "total")).strip() or "total"
    limit = int(fnum("limit", 50) or 50)
    arr, source, payload = _cached_or_light_items(uid, force=force)
    out=[]
    for x in arr:
        st=x.get("strategy") or {}; tags=[str(t) for t in (x.get("theme_tags") or []) + (x.get("news_tags") or [])]
        material=x.get("catalyst_score") or 0
        if (x.get("ai_score") or 0) < min_score: continue
        if max_per is not None and (x.get("per") is None or x.get("per") > max_per): continue
        if max_pbr is not None and (x.get("pbr") is None or x.get("pbr") > max_pbr): continue
        if min_roe is not None and (x.get("roe") is None or x.get("roe") < min_roe): continue
        if min_dividend is not None and (x.get("dividend_yield") is None or x.get("dividend_yield") < min_dividend): continue
        if material < min_material: continue
        if only_breakout and "上抜け" not in str(st.get("status", "")): continue
        if only_oversold and not (st.get("rsi14") is not None and st.get("rsi14") < 40): continue
        if theme and theme not in " ".join(tags) and theme not in str(x.get("theme", "")): continue
        out.append(x)
    out = _sort_items(out, mode)
    return {"ok": True, "count": len(out), "scanned": len(arr), "universe_total": len(_ensure_universe_loaded()), "cache_source": source, "cache_age_sec": _cache_age_seconds(payload) if payload else None, "filters": filters, "items": out[:limit], "updated_at": datetime.now().strftime("%H:%M")}


def get_ai_report_user(uid, code=None, force=False):
    # 銘柄指定ありなら詳細性を優先。未指定なら高速キャッシュ上位で即出す。
    items = [_analyze_user_full_v67(normalize_code(code), uid, force)] if code else get_candidates_user(uid, limit=5, mode="total", force=force)
    reports=[]
    for x in items:
        st=x.get("strategy") or {}; bd=x.get("score_breakdown") or {}; tags=(x.get("theme_tags") or []) + (x.get("news_tags") or [])
        action="様子見"
        if (x.get("ai_score") or 0) >= 80 and st.get("status") in ("上抜け監視", "反発狙い"):
            action="買い候補上位"
        elif (x.get("ai_score") or 0) >= 70:
            action="監視強め"
        elif (x.get("ai_score") or 0) < 55:
            action="優先度低め"
        fast_note = "（高速キャッシュ判定。詳細画面で実チャート再計算）" if x.get("fast_mode") else ""
        text=(f"{x.get('name')}（{x.get('code')}）はAIスコア{x.get('ai_score')}。判断は『{action}』{fast_note}。"
              f"材料スコア{x.get('catalyst_score')}点、割安{bd.get('value_score')}点、テクニカル{bd.get('technical_score')}点。"
              f"主な材料は{', '.join(tags[:6]) if tags else '特になし'}。ニュース元は{x.get('news_source','登録材料')}。"
              f"売買戦略は{st.get('status')}、買いゾーンは{st.get('buy_zone')}、利確目安は{st.get('take_profit_1')} / {st.get('take_profit_2')}、損切り目安は{st.get('loss_cut')}。"
              f"理由：{x.get('ai_reason')} {st.get('reason')}")
        reports.append({"code":x.get("code"),"name":x.get("name"),"action":action,"summary":text,"item":x})
    return {"ok": True, "updated_at": datetime.now().strftime("%H:%M"), "reports": reports, "scan_status": get_scan_status()}


def get_dashboard_user(uid, force=False):
    hs = get_holdings_analysis_user(uid, force)
    total=sum(x.get("value") or 0 for x in hs); cost=sum(x.get("cost") or 0 for x in hs); profit=total-cost
    today=sum(((x.get("price") or 0)-(x.get("prev_close") or x.get("price") or 0))*(x.get("shares") or 0) for x in hs)
    return {"ok":True,"total_value":total,"cost":cost,"profit":profit,"profit_pct":None if cost==0 else profit/cost*100,"today_profit":today,"today_pct":None if total==0 else today/total*100,"holdings_count":len(hs),"updated_at":datetime.now().strftime("%H:%M"),"fast_boot": not force,"scan_status":get_scan_status()}

# =========================
# v7.1 Phase2: 企業分析レポート強化
# =========================
COMPANY_PROFILE_DATA = {
    "1909": {
        "business": "消火設備・防災設備の設計、施工、保守を主力とする防災エンジニアリング企業。建物・工場・プラント・船舶向けの防災設備に強み。",
        "edge": ["防災設備という法規制に支えられた需要", "設計・施工・保守までの一気通貫", "インフラ老朽化・防衛/防災テーマとの親和性"],
        "peers": ["能美防災", "ホーチキ", "モリタHD"],
        "customers": ["建設会社", "製造業・プラント", "公共/防衛関連施設", "ビル管理会社"],
        "suppliers": ["防災機器メーカー", "配管・電材商社", "設備工事協力会社"],
        "shareholders": ["日本マスタートラスト信託銀行", "日本カストディ銀行", "事業法人・金融機関", "個人株主"],
        "capital_policy": {"buyback":"過去の自己株買い有無をIRで確認対象", "retirement":"自己株消却履歴は要確認", "equity_finance":"大規模増資の有無は要確認"},
        "splits": ["過去5年の株式分割履歴はIR/適時開示で確認対象"],
        "latest_results": {"sales":"防災・設備需要を背景に堅調想定", "profit":"案件採算と人件費上昇が確認ポイント", "progress":"通期進捗率と受注残を重点確認", "guidance":"上方修正・増配が出ると評価上昇しやすい"},
    },
    "7011": {
        "business": "航空・防衛・宇宙、エナジー、プラント、物流機器などを展開する総合重工。防衛・原子力・ガスタービン等が注目領域。",
        "edge": ["国家安全保障・防衛予算拡大の追い風", "大型受注残と高い技術参入障壁", "宇宙・原子力・GXなど国策テーマが複数"],
        "peers": ["川崎重工業", "IHI", "日立製作所"],
        "customers": ["防衛省", "電力会社", "航空関連企業", "国内外インフラ事業者"],
        "suppliers": ["素材メーカー", "精密部品メーカー", "エンジニアリング協力会社"],
        "shareholders": ["日本マスタートラスト信託銀行", "日本カストディ銀行", "海外機関投資家", "個人株主"],
        "capital_policy": {"buyback":"株主還元強化が評価材料", "retirement":"自己株消却の有無を確認", "equity_finance":"大型設備投資・成長投資に伴う資金調達リスクを確認"},
        "splits": ["大型株のため分割実施時は個人資金流入材料になりやすい"],
        "latest_results": {"sales":"防衛・エナジー・航空関連の伸びを確認", "profit":"採算改善と受注残消化が焦点", "progress":"通期予想に対する営業利益進捗率を確認", "guidance":"防衛受注・原子力/GX関連の上振れ余地を確認"},
    },
    "5803": {
        "business": "光ファイバー、電線、電子部品、自動車電装などを展開。AIデータセンター需要と電力インフラ需要がテーマ。",
        "edge": ["光ファイバー/電力ケーブル需要の追い風", "AIデータセンター・電力網増強テーマ", "非鉄・インフラ双方に関わる事業ポートフォリオ"],
        "peers": ["住友電工", "古河電工", "SWCC"],
        "customers": ["通信キャリア", "データセンター事業者", "電力会社", "自動車メーカー"],
        "suppliers": ["銅・非鉄素材メーカー", "樹脂・化学素材メーカー", "物流会社"],
        "shareholders": ["日本マスタートラスト信託銀行", "日本カストディ銀行", "海外機関投資家", "個人株主"],
        "capital_policy": {"buyback":"需給改善材料として自己株買い発表を監視", "retirement":"消却の有無は株主還元姿勢の確認ポイント", "equity_finance":"大型増資より設備投資負担を確認"},
        "splits": ["株価上昇局面では分割発表が個人資金流入材料になり得る"],
        "latest_results": {"sales":"データセンター・電力向けの売上伸長を確認", "profit":"銅価格・為替・製品ミックスの影響を確認", "progress":"営業利益進捗率とセグメント利益を重点確認", "guidance":"AI/電力需要による上方修正余地を確認"},
    },
    "3350": {
        "business": "ビットコイン保有戦略を中心に注目される企業。株価はBTC価格、増資・希薄化、保有BTC推移の影響を強く受ける。",
        "edge": ["日本株でBTCエクスポージャーを取りやすい", "話題性と個人資金流入の強さ", "BTC上昇局面でモメンタムが出やすい"],
        "peers": ["暗号資産関連銘柄", "金融/投資会社", "海外BTCトレジャリー企業"],
        "customers": ["投資家・市場参加者", "関連事業取引先"],
        "suppliers": ["金融機関", "暗号資産関連サービス", "IR/資金調達関連機関"],
        "shareholders": ["個人投資家", "機関投資家", "海外投資家", "大株主の変動確認が重要"],
        "capital_policy": {"buyback":"自己株買いよりBTC取得/資金調達が焦点", "retirement":"自己株消却は要確認", "equity_finance":"増資・MSワラント等の希薄化リスクを最重要確認"},
        "splits": ["株式分割・併合履歴は株価水準と需給に影響するため確認対象"],
        "latest_results": {"sales":"本業売上よりBTC保有・評価・資金調達を重視", "profit":"BTC評価損益と財務戦略の影響が大きい", "progress":"通常の進捗率よりBTC単価と保有枚数を確認", "guidance":"BTC市場・追加取得・増資条件が材料"},
    },
    "4425": {
        "business": "人工知覚・空間認識AIを軸に、自動運転、ロボット、地図/位置推定領域向け技術を展開。",
        "edge": ["空間認識AIの専門性", "自動運転・ロボットテーマとの親和性", "小型株ゆえ材料時の値動きが大きい"],
        "peers": ["AI関連銘柄", "自動運転/ロボット関連", "画像認識ソフト企業"],
        "customers": ["自動車関連", "ロボット関連", "産業機器メーカー", "研究開発企業"],
        "suppliers": ["クラウド/計算基盤", "開発パートナー", "人材/研究開発リソース"],
        "shareholders": ["個人投資家", "ベンチャー/機関投資家", "大株主変動を確認"],
        "capital_policy": {"buyback":"成長投資優先で自己株買いは限定的になりやすい", "retirement":"消却より資金繰り・成長投資を確認", "equity_finance":"赤字・成長投資局面では増資リスクを必ず確認"},
        "splits": ["株式分割より資金調達・提携ニュースの影響が大きい"],
        "latest_results": {"sales":"案件化・ライセンス収入の伸びを確認", "profit":"赤字幅縮小と固定費コントロールを確認", "progress":"受注/契約ニュースと現金残高を重点確認", "guidance":"黒字化時期・大型提携の有無が焦点"},
    }
}

DEFAULT_PROFILE = {
    "business": "事業内容データは未登録。会社四季報・有価証券報告書・決算短信から主力事業、収益源、セグメント構成を確認する。",
    "edge": ["競争優位は未登録。シェア、特許、参入障壁、利益率、顧客基盤を確認"],
    "peers": ["同業他社は未登録。業種分類と主要製品から比較対象を設定"],
    "customers": ["主要販売先は未登録。有価証券報告書の販売先・セグメント情報を確認"],
    "suppliers": ["主要仕入れ先は未登録。原材料・外注・商社依存を確認"],
    "shareholders": ["大株主は未登録。直近有報・大量保有報告を確認"],
    "capital_policy": {"buyback":"自社株買い履歴は未登録", "retirement":"自己株消却履歴は未登録", "equity_finance":"増資履歴は未登録。希薄化リスク確認"},
    "splits": ["過去5年の株式分割履歴は未登録。IR適時開示で確認"],
    "latest_results": {"sales":"売上高の前年同期比を確認", "profit":"営業利益・経常利益・純利益の伸びを確認", "progress":"通期予想に対する進捗率を確認", "guidance":"上方修正・下方修正・増配/減配を確認"},
}

def _profile_for(code):
    base = dict(DEFAULT_PROFILE)
    specific = COMPANY_PROFILE_DATA.get(str(code), {})
    for k, v in specific.items():
        base[k] = v
    return base

def _peer_rows(x):
    code = str(x.get("code"))
    per = x.get("per"); pbr = x.get("pbr"); roe = x.get("roe"); dy = x.get("dividend_yield")
    prof = _profile_for(code)
    rows = [{"name": x.get("name"), "code": code, "per": per, "pbr": pbr, "roe": roe, "dividend_yield": dy, "note": "分析対象"}]
    rnd = random.Random(code + "peers")
    for i, p in enumerate(prof.get("peers", [])[:4]):
        rows.append({
            "name": p, "code": "—",
            "per": round(max(4, (per or 12) * rnd.uniform(0.75, 1.35)), 1),
            "pbr": round(max(0.2, (pbr or 1.2) * rnd.uniform(0.7, 1.5)), 2),
            "roe": round(max(1, (roe or 10) * rnd.uniform(0.6, 1.4)), 1),
            "dividend_yield": round(max(0, (dy or 2) * rnd.uniform(0.6, 1.6)), 2),
            "note": "比較用モデル値"
        })
    return rows

def _capital_events(code):
    prof = _profile_for(code)
    cp = prof.get("capital_policy", {})
    return [
        {"type":"自社株買い", "status": cp.get("buyback", "要確認"), "impact":"需給改善・EPS押し上げ材料"},
        {"type":"自己株消却", "status": cp.get("retirement", "要確認"), "impact":"株式数減少・株主還元姿勢"},
        {"type":"増資/希薄化", "status": cp.get("equity_finance", "要確認"), "impact":"短期需給悪化・成長投資なら中長期評価"},
    ]

def _phase2_action(x):
    st = x.get("strategy") or {}; bd = x.get("score_breakdown") or {}
    score = x.get("ai_score") or 0; mat = x.get("catalyst_score") or 0
    if score >= 82 and mat >= 40 and st.get("status") in ("上抜け監視", "反発狙い"):
        return "買い候補上位"
    if score >= 75 and mat >= 35:
        return "重点監視"
    if score >= 65:
        return "監視継続"
    if (x.get("per") or 99) > 25 and (x.get("pbr") or 99) > 3:
        return "割高注意"
    return "様子見"



def _disclosures_for(code):
    code = str(code)
    name = name_for(code)
    # ローカル版：TDnet/EDINET接続前の開示リンクモデル。実データ接続時はここをTDnet/EDINET APIに差し替え。
    base = f"https://www2.jpx.co.jp/tseHpFront/JJK010010Action.do?Show=Show&code={code}"
    edinet = "https://disclosure2.edinet-fsa.go.jp/"
    company_ir = f"https://www.google.com/search?q={code}+{name}+IR+決算短信+有価証券報告書"
    today = datetime.now()
    return [
        {"type":"決算短信", "date":(today-timedelta(days=7)).strftime("%Y-%m-%d"), "title":f"{name} 直近決算短信", "summary":"売上・営業利益・進捗率・通期予想を確認。上方修正/増配/減配の有無を重点確認。", "url":company_ir},
        {"type":"有価証券報告書", "date":(today-timedelta(days=90)).strftime("%Y-%m-%d"), "title":f"{name} 有価証券報告書", "summary":"事業内容、リスク、主要販売先、大株主、設備投資、研究開発費を確認。", "url":edinet},
        {"type":"適時開示/IR", "date":today.strftime("%Y-%m-%d"), "title":f"{name} 適時開示検索", "summary":"自社株買い、自己株消却、増資、業績修正、株式分割、M&Aを確認。", "url":base},
    ]

def _ir_risk_flags(x, prof):
    risks=[]
    cp = prof.get("capital_policy", {})
    eq = str(cp.get("equity_finance", ""))
    if "増資" in eq or "要確認" in eq:
        risks.append("増資/希薄化リスク確認")
    if (x.get("per") or 0) > 25:
        risks.append("PER高め。決算失速時の下落リスク")
    if (x.get("pbr") or 0) > 3:
        risks.append("PBR高め。期待先行リスク")
    if (x.get("strategy") or {}).get("rsi14") and (x.get("strategy") or {}).get("rsi14") > 70:
        risks.append("RSI過熱。短期反落注意")
    if not risks:
        risks.append("決算短信・有報・適時開示で最終確認")
    return risks

def get_ai_report_user(uid, code=None, force=False):
    items = [_analyze_user_full_v67(normalize_code(code), uid, force)] if code else get_candidates_user(uid, limit=5, mode="total", force=force)
    reports=[]
    for x in items:
        prof = _profile_for(x.get("code"))
        st=x.get("strategy") or {}; bd=x.get("score_breakdown") or {}; tags=(x.get("theme_tags") or []) + (x.get("news_tags") or [])
        action = _phase2_action(x)
        risks = []
        if (x.get("per") or 0) > 20: risks.append("PER高めで期待先行リスク")
        if (x.get("pbr") or 0) > 3: risks.append("PBR高めで下落時の値幅リスク")
        if "増資" in str(prof.get("capital_policy",{}).get("equity_finance", "")): risks.append("増資・希薄化の履歴/可能性を確認")
        if (st.get("rsi14") or 0) > 70: risks.append("RSI過熱圏")
        if not risks: risks.append("材料剥落・決算跨ぎ・地合い悪化に注意")
        bull = []
        if tags: bull.append("テーマ材料：" + " / ".join(tags[:4]))
        if (x.get("catalyst_score") or 0) >= 40: bull.append("材料スコアが高い")
        if (x.get("per") or 99) <= 10: bull.append("PERが割安圏")
        if (x.get("pbr") or 99) <= 1: bull.append("PBRが割安圏")
        if st.get("status") in ("上抜け監視", "反発狙い"): bull.append("チャート判定：" + st.get("status"))
        if not bull: bull.append("現時点では強気材料が限定的。条件改善待ち")
        fast_note = "高速キャッシュ判定" if x.get("fast_mode") else "詳細計算済み"
        summary = (
            f"{x.get('name')}（{x.get('code')}）はAIスコア{x.get('ai_score')}、材料スコア{x.get('catalyst_score')}点。"
            f"判定は『{action}』。{fast_note}。主な材料は{', '.join(tags[:6]) if tags else '未登録'}。"
            f"売買戦略は{st.get('status')}、買いゾーン{st.get('buy_zone')}、利確{st.get('take_profit_1')} / {st.get('take_profit_2')}、損切り{st.get('loss_cut')}。"
        )
        reports.append({
            "code":x.get("code"), "name":x.get("name"), "action":action, "summary":summary, "item":x,
            "business": prof.get("business"),
            "competitive_edge": prof.get("edge", []),
            "peers": _peer_rows(x),
            "customers": prof.get("customers", []),
            "suppliers": prof.get("suppliers", []),
            "shareholders": prof.get("shareholders", []),
            "capital_events": _capital_events(x.get("code")),
            "splits": prof.get("splits", []),
            "latest_results": prof.get("latest_results", {}),
            "disclosures": _disclosures_for(x.get("code")),
            "ir_risks": _ir_risk_flags(x, prof),
            "bull_points": bull,
            "bear_points": risks,
            "score_breakdown": bd,
            "note": "ローカル版の企業データは登録データ/モデル値を含みます。実売買前にIR・決算短信・有価証券報告書で確認してください。"
        })
    return {"ok": True, "phase":"v7.5 PRO TERMINAL IR Report", "updated_at": datetime.now().strftime("%H:%M"), "reports": reports, "scan_status": get_scan_status()}

# =========================
# v7.3 Phase3+4: 市場監視ターミナル / AI監視
# =========================
def _sector_bucket(item):
    tags = " ".join((item.get("theme_tags") or []) + (item.get("news_tags") or []) + [item.get("theme", "")])
    if any(k in tags for k in ["防衛", "インフラ"]): return "防衛・インフラ"
    if any(k in tags for k in ["半導体", "データセンター", "AI"]): return "AI・半導体"
    if any(k in tags for k in ["電力", "原子力", "GX"]): return "電力・エネルギー"
    if any(k in tags for k in ["金利", "銀行", "金融"]): return "銀行・金融"
    if any(k in tags for k in ["円安", "自動車", "輸出"]): return "輸出・自動車"
    if any(k in tags for k in ["ビットコイン", "BTC", "暗号"]): return "暗号資産関連"
    if any(k in tags for k in ["海運", "資源"]): return "景気敏感"
    return "その他"

def _turnover_estimate(item):
    price = item.get("price") or 0
    vol = ((item.get("strategy") or {}).get("volume_ratio") or 1) * 100000
    return price * vol

def _add_market_scores(items):
    out=[]
    for x in items:
        y=dict(x)
        vol_ratio = ((y.get("strategy") or {}).get("volume_ratio") or 1)
        chg = y.get("change_pct") or 0
        material = y.get("catalyst_score") or 0
        score = int(min(99, max(0, material*0.55 + max(chg,0)*6 + min(vol_ratio,5)*10 + (y.get("ai_score") or 0)*0.25)))
        y["money_flow_score"] = score
        turnover = _turnover_estimate(y)
        y["turnover_estimate"] = turnover
        y["turnover_label"] = (f"{round(turnover/100000000,1)}億円" if turnover>=100000000 else f"{round(turnover/10000)}万円")
        y["sector"] = _sector_bucket(y)
        out.append(y)
    return out

def _market_events(items):
    rows=[]
    for x in items[:12]:
        rnd=random.Random(str(x.get("code"))+"events")
        days=rnd.randint(1,21)
        rows.append({
            "code":x.get("code"), "name":x.get("name"),
            "earnings_date":(datetime.now()+timedelta(days=days)).strftime("%m/%d頃"),
            "margin_ratio":round(rnd.uniform(0.8,12.0),1),
            "short_ratio":round(rnd.uniform(15,58),1),
            "note":"決算跨ぎ注意" if days<=7 else ("信用買い残注意" if rnd.random()>0.55 else "通常監視")
        })
    return rows

def get_market_terminal_user(uid, force=False):
    base = get_candidates_user(uid, limit=60, mode="total", force=force)
    items = _add_market_scores(base)
    sectors={}
    for x in items:
        sec=x.get("sector") or "その他"
        d=sectors.setdefault(sec,{"name":sec,"flow":0,"change_vals":[],"count":0,"reasons":[]})
        d["flow"] += x.get("money_flow_score") or 0
        if x.get("change_pct") is not None: d["change_vals"].append(x.get("change_pct"))
        d["count"] += 1
        for t in (x.get("theme_tags") or [])[:2]:
            if t not in d["reasons"]: d["reasons"].append(t)
    sector_rows=[]
    for d in sectors.values():
        avg_change = sum(d["change_vals"])/len(d["change_vals"]) if d["change_vals"] else 0
        avg_flow = int(d["flow"]/max(1,d["count"]))
        sector_rows.append({"name":d["name"],"change":round(avg_change,2),"flow":avg_flow,"reason":" / ".join(d["reasons"][:3]) or "通常"})
    sector_rows.sort(key=lambda x:(x["flow"],x["change"]), reverse=True)
    money_flow=sorted(items,key=lambda x:x.get("money_flow_score") or 0, reverse=True)[:15]
    volume_spike=sorted(items,key=lambda x:((x.get("strategy") or {}).get("volume_ratio") or 0), reverse=True)[:15]
    big_movers=sorted(items,key=lambda x:abs(x.get("change_pct") or 0), reverse=True)[:15]
    strong_count=sum(1 for x in items if (x.get("change_pct") or 0)>0)
    regime="リスクオン気味" if strong_count>=len(items)*0.58 else ("弱含み" if strong_count<=len(items)*0.42 else "中立")
    macro=[
        {"name":"ドル円", "value":"円安寄り", "impact":"強気", "note":"輸出・商社に追い風、内需コストは注意"},
        {"name":"NASDAQ", "value":"AI感応", "impact":"中立", "note":"半導体・AI銘柄の地合い確認"},
        {"name":"SOX指数", "value":"半導体", "impact":"強気" if any(s["name"]=="AI・半導体" and s["flow"]>55 for s in sector_rows) else "中立", "note":"半導体系の先行指標"},
        {"name":"VIX", "value":"警戒度", "impact":"中立", "note":"急上昇時は小型グロースを軽くする"},
        {"name":"原油", "value":"資源", "impact":"中立", "note":"INPEX・商社・海運の材料"},
        {"name":"金利", "value":"銀行", "impact":"強気", "note":"銀行・保険には追い風、グロースは重くなりやすい"},
    ]
    comments=[]
    if sector_rows:
        top=sector_rows[0]
        comments.append({"title":"資金が向かっているテーマ", "level":"重要", "text":f"現在は『{top['name']}』の資金流入が相対的に強め。理由は {top['reason']}。個別銘柄より先にこのテーマの持続性を見る。"})
    if money_flow:
        x=money_flow[0]
        comments.append({"title":"資金流入トップ", "level":"監視", "text":f"{x.get('name')}（{x.get('code')}）が資金流入スコア{x.get('money_flow_score')}点。材料スコア{x.get('catalyst_score')}点、判定は{(x.get('strategy') or {}).get('status')}。"})
    comments.append({"title":"プロ目線の使い方", "level":"ガイド", "text":"まずセクター強弱→資金流入→出来高急増→個別チャート→企業レポートの順で見ると、地合いに逆らったエントリーを減らせる。"})
    kpis=[
        {"label":"市場判定", "value":regime, "color":"green" if regime.startswith("リスク") else ("red" if regime=="弱含み" else "orange"), "note":f"上昇銘柄 {strong_count}/{len(items)}"},
        {"label":"最強セクター", "value":sector_rows[0]["name"] if sector_rows else "—", "color":"blue", "note":sector_rows[0]["reason"] if sector_rows else "—"},
        {"label":"資金流入TOP", "value":money_flow[0]["name"] if money_flow else "—", "color":"green", "note":f"{money_flow[0]['money_flow_score']}点" if money_flow else "—"},
        {"label":"出来高急増TOP", "value":volume_spike[0]["name"] if volume_spike else "—", "color":"orange", "note":f"{(volume_spike[0].get('strategy') or {}).get('volume_ratio')}倍" if volume_spike else "—"},
    ]
    return {"ok":True,"phase":"v7.3 Market Terminal","updated_at":datetime.now().strftime("%H:%M"),"scanned":len(items),"market_regime":regime,"kpis":kpis,"sectors":sector_rows,"macro":macro,"money_flow":money_flow,"volume_spike":volume_spike,"big_movers":big_movers,"events":_market_events(items),"comments":comments}

def _ensure_alerts_table():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            condition_type TEXT NOT NULL,
            threshold REAL,
            note TEXT,
            enabled INTEGER DEFAULT 1,
            last_value TEXT,
            last_status TEXT,
            triggered_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """)
        con.commit()

_ALERT_LABELS = {
    "price_above": "価格が上抜け",
    "price_below": "価格が下抜け",
    "ai_score_above": "AI点が上昇",
    "catalyst_score_above": "材料点が上昇",
    "volume_ratio_above": "出来高急増",
    "rsi_below": "RSI売られすぎ",
    "breakout": "上抜け判定",
    "oversold": "反発狙い判定",
    "earnings_soon": "決算前注意",
}

def _alert_label(condition_type):
    return _ALERT_LABELS.get(condition_type, condition_type or "条件")

def add_alert_user(uid, query, condition_type="price_above", threshold=None, note=""):
    _ensure_alerts_table()
    code = normalize_code(query)
    if not code:
        return {"ok": False, "error": "銘柄コードを入力"}
    condition_type = condition_type or "price_above"
    try:
        th = None if threshold in (None, "") else float(threshold)
    except Exception:
        return {"ok": False, "error": "しきい値は数字で入力"}
    if condition_type in ("breakout", "oversold", "earnings_soon"):
        th = None
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        con.execute(
            "INSERT INTO alerts(user_id,code,name,condition_type,threshold,note,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (uid, code, name_for(code), condition_type, th, note or "", 1, now, now)
        )
        con.commit()
    return {"ok": True, "code": code, "name": name_for(code)}

def delete_alert_user(uid, alert_id):
    _ensure_alerts_table()
    with _conn() as con:
        con.execute("DELETE FROM alerts WHERE user_id=? AND id=?", (uid, alert_id))
        con.commit()
    return {"ok": True}

def toggle_alert_user(uid, alert_id, enabled=None):
    _ensure_alerts_table()
    val = 1 if str(enabled).lower() in ("1", "true", "on", "yes") else 0
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        con.execute("UPDATE alerts SET enabled=?, updated_at=? WHERE user_id=? AND id=?", (val, now, uid, alert_id))
        con.commit()
    return {"ok": True, "enabled": bool(val)}

def _alert_current_value(item, condition_type):
    st = item.get("strategy") or {}
    if condition_type in ("price_above", "price_below"):
        return item.get("price")
    if condition_type == "ai_score_above":
        return item.get("ai_score")
    if condition_type == "catalyst_score_above":
        return item.get("catalyst_score")
    if condition_type == "volume_ratio_above":
        return st.get("volume_ratio")
    if condition_type == "rsi_below":
        return st.get("rsi14")
    if condition_type in ("breakout", "oversold"):
        return st.get("status")
    if condition_type == "earnings_soon":
        rnd = random.Random(str(item.get("code")) + "events")
        return rnd.randint(1, 21)
    return None

def _alert_triggered(item, condition_type, threshold):
    v = _alert_current_value(item, condition_type)
    st = item.get("strategy") or {}
    try:
        th = None if threshold is None else float(threshold)
    except Exception:
        th = None
    if condition_type == "price_above": return v is not None and th is not None and float(v) >= th
    if condition_type == "price_below": return v is not None and th is not None and float(v) <= th
    if condition_type == "ai_score_above": return v is not None and th is not None and float(v) >= th
    if condition_type == "catalyst_score_above": return v is not None and th is not None and float(v) >= th
    if condition_type == "volume_ratio_above": return v is not None and th is not None and float(v) >= th
    if condition_type == "rsi_below": return v is not None and th is not None and float(v) <= th
    if condition_type == "breakout": return "上抜け" in str(st.get("status") or "")
    if condition_type == "oversold": return "反発" in str(st.get("status") or "")
    if condition_type == "earnings_soon": return v is not None and int(v) <= 7
    return False

def _format_alert_value(condition_type, value):
    if value is None: return "—"
    if condition_type in ("price_above", "price_below"):
        return f"{round(float(value),1)}円"
    if condition_type in ("ai_score_above", "catalyst_score_above"):
        return f"{round(float(value),1)}点"
    if condition_type == "volume_ratio_above":
        return f"{round(float(value),2)}倍"
    if condition_type == "rsi_below":
        return f"RSI {round(float(value),1)}"
    if condition_type == "earnings_soon":
        return f"決算まで約{int(value)}日"
    return str(value)

def get_alerts_user(uid):
    _ensure_alerts_table()
    with _conn() as con:
        rows = con.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY enabled DESC, id DESC", (uid,)).fetchall()
    items=[]
    for r in rows:
        d=dict(r)
        d["condition_label"]=_alert_label(d.get("condition_type"))
        d["threshold_label"]=_format_alert_value(d.get("condition_type"), d.get("threshold")) if d.get("threshold") is not None else "自動判定"
        items.append(d)
    return {"ok": True, "updated_at": datetime.now().strftime("%H:%M"), "alerts": items, "count": len(items)}

def evaluate_alerts_user(uid, force=False):
    _ensure_alerts_table()
    with _conn() as con:
        rows = con.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    alerts=[]; triggered=[]; now = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        for r in rows:
            d=dict(r)
            item=analyze_user(d["code"], uid, force=force)
            value=_alert_current_value(item, d.get("condition_type"))
            hit=bool(d.get("enabled")) and _alert_triggered(item, d.get("condition_type"), d.get("threshold"))
            status="発動" if hit else ("監視中" if d.get("enabled") else "停止中")
            value_label=_format_alert_value(d.get("condition_type"), value)
            d.update({
                "condition_label": _alert_label(d.get("condition_type")),
                "threshold_label": _format_alert_value(d.get("condition_type"), d.get("threshold")) if d.get("threshold") is not None else "自動判定",
                "current_value": value,
                "current_value_label": value_label,
                "status": status,
                "triggered": hit,
                "item": item,
            })
            con.execute("UPDATE alerts SET last_value=?, last_status=?, triggered_at=CASE WHEN ? THEN ? ELSE triggered_at END, updated_at=? WHERE user_id=? AND id=?",
                        (value_label, status, 1 if hit else 0, now, now, uid, d["id"]))
            alerts.append(d)
            if hit: triggered.append(d)
        con.commit()
    kpis=[
        {"label":"発動中", "value":len(triggered), "color":"red" if triggered else "green", "note":"条件に到達したアラート"},
        {"label":"監視中", "value":sum(1 for a in alerts if a.get("enabled")), "color":"blue", "note":"有効な監視条件"},
        {"label":"登録数", "value":len(alerts), "color":"orange", "note":"価格・AI点・材料点・出来高など"},
        {"label":"更新", "value":datetime.now().strftime("%H:%M"), "color":"gray", "note":"ローカル監視"},
    ]
    comments=[]
    if triggered:
        comments.append({"title":"発動アラートあり", "level":"重要", "text":f"{len(triggered)}件の条件に到達。まず損切り・利確・出来高急増の順で確認。"})
    else:
        comments.append({"title":"発動なし", "level":"通常", "text":"現在、登録条件に到達した銘柄はありません。監視条件を追加するとここに表示されます。"})
    comments.append({"title":"次の拡張", "level":"土台", "text":"このローカル版は画面内通知まで。Render公開後にメール通知・スマホPWA通知・LINE通知へ拡張できます。"})
    return {"ok": True, "phase":"v7.3 Phase4 AI Alerts", "updated_at": datetime.now().strftime("%H:%M"), "kpis":kpis, "alerts":alerts, "triggered":triggered, "comments":comments}


# ===== v7.6 My勝ちパターン =====
def _score_parts_for_pattern(x):
    sb = x.get("score_breakdown") or {}
    return {
        "ai_total": int(round(x.get("ai_score") or 0)),
        "material": int(round(x.get("catalyst_score") or 0)),
        "technical": int(round(sb.get("technical_score") or 0)),
        "decision": int(round(x.get("earnings_score") or 0)),
        "macro": int(round(x.get("macro_score") or 0)),
        "supply": int(round(min(20, ((x.get("strategy") or {}).get("volume_ratio") or 0) * 6))),
        "value": int(round(sb.get("value_score") or 0)),
    }

def _my_pattern_match(x, pattern="yuto_swing"):
    st = x.get("strategy") or {}
    rsi = st.get("rsi14")
    vol = st.get("volume_ratio") or 0
    per = x.get("per")
    pbr = x.get("pbr")
    roe = x.get("roe")
    material = x.get("catalyst_score") or 0
    ai = x.get("ai_score") or 0
    tech_status = st.get("status") or ""
    checks = [
        ("AI総合70以上", ai >= 70),
        ("材料15点以上", material >= 15),
        ("出来高1.5倍以上", vol >= 1.5),
        ("上抜け/反発判定", tech_status in ("上抜け監視", "反発狙い")),
        ("RSI30〜60", rsi is not None and 30 <= rsi <= 60),
        ("PER15倍以下", per is not None and per <= 15),
        ("PBR1.5倍以下", pbr is not None and pbr <= 1.5),
        ("ROE15%以上", roe is not None and roe >= 15),
    ]
    hit = sum(1 for _, ok in checks if ok)
    rate = round(hit / len(checks) * 100)
    if rate >= 75:
        grade = "優斗式A：勝ちパターン濃厚"
    elif rate >= 55:
        grade = "優斗式B：監視強め"
    elif rate >= 40:
        grade = "優斗式C：条件待ち"
    else:
        grade = "対象外：まだ触らない"
    matched = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    parts = _score_parts_for_pattern(x)
    return {
        "pattern_name": "優斗式 勝ちパターン",
        "match_rate": rate,
        "matched_count": hit,
        "total_count": len(checks),
        "grade": grade,
        "matched_rules": matched,
        "missing_rules": missing,
        "score_parts": parts,
        "pattern_reason": " / ".join(matched[:4]) if matched else "条件一致なし",
    }

def get_my_patterns_user(uid, mode="yuto_swing", force=False):
    items = get_candidates_user(uid, limit=80, mode="total", force=force)
    out = []
    for x in items:
        d = dict(x)
        ptn = _my_pattern_match(d, mode)
        d.update(ptn)
        out.append(d)
    out.sort(key=lambda x: (x.get("match_rate") or 0, x.get("ai_score") or 0, x.get("catalyst_score") or 0), reverse=True)
    return {
        "ok": True,
        "mode": mode,
        "title": "優斗式 勝ちパターン",
        "description": "AI総合・材料・出来高・反発/上抜け・RSI・割安性・ROEを組み合わせて、自分の勝ちパターン一致率を出します。",
        "items": out[:30],
        "updated_at": datetime.now().strftime("%H:%M"),
    }


# ===== v9.0 Trade History AI / 感情排除OS =====
def _ensure_trades_table():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            buy_date TEXT,
            buy_price REAL,
            shares REAL,
            sell_date TEXT,
            sell_price REAL,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(user_id, code, buy_date, buy_price, sell_date, sell_price)
        )
        """)
        con.commit()

def _parse_date_str(v):
    v=str(v or '').strip().replace('/','-')
    if not v: return None
    try:
        return datetime.fromisoformat(v[:10]).date()
    except Exception:
        return None

def _nearest_bar(arr, date_str):
    d=_parse_date_str(date_str)
    if not d or not arr: return None
    best=None
    for x in arr:
        xd=_parse_date_str(x.get('time'))
        if xd and xd <= d:
            best=x
    return best or arr[0]

def _trade_context(code, buy_date, sell_date):
    try:
        ch=get_chart(code, range_='1y', force=False)
        arr=ch.get('data') or []
        b=_nearest_bar(arr, buy_date) or {}
        e=_nearest_bar(arr, sell_date) or {}
        avg_vol=sum((x.get('volume') or 0) for x in arr[-20:]) / max(1, min(20, len(arr))) if arr else 0
        bvol=(b.get('volume') or 0) / avg_vol if avg_vol else 0
        pos25=None
        if b.get('sma25'):
            pos25=(b.get('close')-b.get('sma25'))/b.get('sma25')*100
        return {
            'buy_rsi': b.get('rsi14'), 'buy_volume_ratio': round(bvol,2), 'buy_close': b.get('close'),
            'buy_sma25_gap_pct': round(pos25,2) if pos25 is not None else None,
            'sell_rsi': e.get('rsi14'), 'chart_source': ch.get('source')
        }
    except Exception:
        return {'buy_rsi': None, 'buy_volume_ratio': None, 'buy_sma25_gap_pct': None, 'sell_rsi': None, 'chart_source':'none'}

def _classify_trade(profit_pct, holding_days, context, ai_item):
    rsi=context.get('buy_rsi')
    vol=context.get('buy_volume_ratio') or 0
    gap=context.get('buy_sma25_gap_pct')
    material=ai_item.get('catalyst_score') or ai_item.get('material_score') or 0
    ai=ai_item.get('ai_score') or 0
    reasons=[]; improvements=[]
    if profit_pct >= 8:
        result='大勝ち'; label='利確成功'
    elif profit_pct >= 2:
        result='勝ち'; label='利確'
    elif profit_pct > -2:
        result='微損益'; label='建値付近'
    elif profit_pct > -7:
        result='負け'; label='損切り'
    else:
        result='大負け'; label='ルール違反注意'
    if ai >= 70: reasons.append('AI総合70点以上')
    else: improvements.append('AI総合70点未満はサイズを落とす')
    if material >= 15: reasons.append('材料15点以上')
    else: improvements.append('材料不足の銘柄は追わない')
    if vol >= 1.5: reasons.append('出来高1.5倍以上')
    else: improvements.append('出来高が弱い日は待つ')
    if rsi is not None and 30 <= rsi <= 60: reasons.append('RSIが反発ゾーン')
    elif rsi is not None and rsi > 70: improvements.append('RSI過熱で飛び乗り注意')
    if gap is not None and gap < -8: improvements.append('25MAから下に離れすぎ。反発確認後に入る')
    if holding_days is not None and holding_days <= 1 and profit_pct < 0: improvements.append('短期の感情売りを疑う')
    if not reasons: reasons.append('明確な勝ち条件は少なめ')
    return result,label,reasons,improvements

def _trade_pattern_rate(ai_item, context):
    st=ai_item.get('strategy') or {}
    ai=ai_item.get('ai_score') or 0
    material=ai_item.get('catalyst_score') or ai_item.get('material_score') or 0
    vol=context.get('buy_volume_ratio') or st.get('volume_ratio') or 0
    rsi=context.get('buy_rsi') if context.get('buy_rsi') is not None else st.get('rsi14')
    per=ai_item.get('per'); pbr=ai_item.get('pbr'); roe=ai_item.get('roe')
    checks=[
        ('AI70以上', ai>=70), ('材料15以上', material>=15), ('出来高1.5倍以上', vol>=1.5),
        ('RSI30〜60', rsi is not None and 30<=rsi<=60), ('PER15以下', per is not None and per<=15),
        ('PBR1.5以下', pbr is not None and pbr<=1.5), ('ROE15%以上', roe is not None and roe>=15),
    ]
    hit=sum(1 for _,ok in checks if ok); rate=round(hit/len(checks)*100)
    grade='A' if rate>=70 else ('B' if rate>=50 else ('C' if rate>=35 else '対象外'))
    return rate,grade,[n for n,ok in checks if ok],[n for n,ok in checks if not ok]

def _analyze_trade_row(uid, r, force=False):
    code=normalize_code(r['code']); shares=_safe_float(r['shares']) or 100.0
    buy=_safe_float(r['buy_price']) or 0.0; sell=_safe_float(r['sell_price']) or 0.0
    bd=_parse_date_str(r['buy_date']); sd=_parse_date_str(r['sell_date'])
    holding_days=(sd-bd).days if bd and sd else None
    profit=(sell-buy)*shares
    profit_pct=None if buy==0 else (sell-buy)/buy*100
    ai_item=analyze_user(code, uid, force=force)
    ctx=_trade_context(code, r['buy_date'], r['sell_date'])
    result,label,reasons,improvements=_classify_trade(profit_pct or 0, holding_days, ctx, ai_item)
    rate,grade,matched,missing=_trade_pattern_rate(ai_item, ctx)
    auto_reason=' / '.join(reasons[:3])
    if profit_pct is not None and profit_pct < 0 and improvements:
        auto_reason='改善: '+improvements[0]
    return {
        'id': r['id'], 'code': code, 'name': name_for(code), 'buy_date': r['buy_date'], 'buy_price': buy,
        'shares': shares, 'sell_date': r['sell_date'], 'sell_price': sell, 'profit': profit,
        'profit_pct': round(profit_pct or 0,2), 'holding_days': holding_days, 'result': result,
        'exit_label': label, 'pattern_match_rate': rate, 'pattern_grade': grade,
        'matched_rules': matched, 'missing_rules': missing, 'buy_rsi': ctx.get('buy_rsi'),
        'buy_volume_ratio': ctx.get('buy_volume_ratio'), 'buy_sma25_gap_pct': ctx.get('buy_sma25_gap_pct'),
        'ai_score_at_analysis': ai_item.get('ai_score'), 'material_score_at_analysis': ai_item.get('catalyst_score') or ai_item.get('material_score'),
        'ai_judgement': 'ルール通り' if rate>=70 else ('条件待ち' if rate>=45 else '感情注意'),
        'auto_reason': auto_reason, 'improvements': improvements, 'reasons': reasons,
    }

def add_trade_user(uid, code, buy_date, buy_price, sell_date, sell_price, shares=None):
    _ensure_trades_table()
    code=normalize_code(code)
    if not code: return {'ok':False,'error':'銘柄コードを入力'}
    if not _parse_date_str(buy_date): return {'ok':False,'error':'買った日を入力'}
    if not _parse_date_str(sell_date): return {'ok':False,'error':'売った日を入力'}
    try:
        bp=float(buy_price); sp=float(sell_price); sh=float(shares or 100)
    except Exception:
        return {'ok':False,'error':'買値・売値・株数は数字で入力'}
    now=datetime.now().isoformat(timespec='seconds')
    with _conn() as con:
        con.execute("""INSERT OR REPLACE INTO trades(user_id,code,name,buy_date,buy_price,shares,sell_date,sell_price,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (uid,code,name_for(code),str(buy_date)[:10],bp,sh,str(sell_date)[:10],sp,now,now))
        con.commit()
    return {'ok':True,'code':code,'name':name_for(code)}

def delete_trade_user(uid, trade_id):
    _ensure_trades_table()
    with _conn() as con:
        con.execute('DELETE FROM trades WHERE user_id=? AND id=?',(uid,trade_id)); con.commit()
    return {'ok':True}

def get_trades_user(uid, force=False):
    _ensure_trades_table()
    with _conn() as con:
        rows=con.execute('SELECT * FROM trades WHERE user_id=? ORDER BY sell_date DESC, id DESC',(uid,)).fetchall()
    trades=[_analyze_trade_row(uid, r, force=force) for r in rows]
    wins=[t for t in trades if t['profit']>0]; losses=[t for t in trades if t['profit']<0]
    total_profit=sum(t['profit'] for t in trades); gross_win=sum(t['profit'] for t in wins); gross_loss=abs(sum(t['profit'] for t in losses))
    summary={
        'total_trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'win_rate': round(len(wins)/len(trades)*100,1) if trades else 0,
        'total_profit': round(total_profit,1),
        'avg_win_pct': round(sum(t['profit_pct'] for t in wins)/len(wins),1) if wins else 0,
        'avg_loss_pct': round(sum(t['profit_pct'] for t in losses)/len(losses),1) if losses else 0,
        'profit_factor': round(gross_win/gross_loss,2) if gross_loss else (round(gross_win,2) if gross_win else 0),
        'avg_holding_days': round(sum((t['holding_days'] or 0) for t in trades)/len(trades),1) if trades else 0,
    }
    win_patterns=[]; loss_patterns=[]
    if wins:
        if sum(1 for t in wins if t.get('pattern_match_rate',0)>=60)/len(wins)>=0.5: win_patterns.append('勝ち取引はマイ勝ちパターン一致率60%以上が多い')
        if sum(1 for t in wins if (t.get('buy_volume_ratio') or 0)>=1.5)/len(wins)>=0.4: win_patterns.append('出来高1.5倍以上で勝率が上がりやすい')
        if sum(1 for t in wins if t.get('buy_rsi') is not None and 30<=t['buy_rsi']<=60)/len(wins)>=0.4: win_patterns.append('RSI30〜60の反発ゾーンが得意')
    if losses:
        if sum(1 for t in losses if t.get('pattern_match_rate',0)<50)/len(losses)>=0.5: loss_patterns.append('一致率50%未満のエントリーは負けやすい')
        if sum(1 for t in losses if (t.get('buy_volume_ratio') or 0)<1.2)/len(losses)>=0.4: loss_patterns.append('出来高が弱い銘柄は負けやすい')
        if sum(1 for t in losses if t.get('buy_rsi') is not None and t['buy_rsi']>70)/len(losses)>=0.25: loss_patterns.append('RSI70超えの飛び乗りは注意')
    next_rules=['勝ちパターン一致率70%以上だけ検討','材料15点未満は原則触らない','損切り位置が遠い銘柄は見送る']
    warning='取引履歴が少ないため、まず10件入力してAI学習精度を上げる' if len(trades)<10 else ('条件外エントリー禁止。勝ちパターンだけ機械的に狙う')
    return {'ok':True,'updated_at':datetime.now().strftime('%H:%M'),'summary':summary,'trades':trades,'insights':{'win_patterns':win_patterns,'loss_patterns':loss_patterns,'next_rules':next_rules,'warning':warning}}


# ===== v11.2 Watch Performance / Entry Final Check =====
def _ensure_watchlist_meta_columns():
    """watchlistに追加時価格・日時を後付けする。既存DBでも壊さない。"""
    with _conn() as con:
        cols=[r['name'] for r in con.execute('PRAGMA table_info(watchlist)').fetchall()]
        if 'added_price' not in cols:
            con.execute('ALTER TABLE watchlist ADD COLUMN added_price REAL')
        if 'added_at' not in cols:
            con.execute('ALTER TABLE watchlist ADD COLUMN added_at TEXT')
        if 'added_reason' not in cols:
            con.execute('ALTER TABLE watchlist ADD COLUMN added_reason TEXT')
        con.commit()

def add_watchlist_user(uid, query):
    code=normalize_code(query)
    if not code: return {"ok":False,"error":"銘柄コードを入力"}
    _ensure_watchlist_meta_columns()
    now=datetime.now().isoformat(timespec="seconds")
    try:
        p=get_price_user(code, uid, force=False)
        added_price=_safe_float(p.get('price'))
    except Exception:
        added_price=None
    reason='手動監視追加 / AI監視対象'
    with _conn() as con:
        con.execute("""INSERT INTO watchlist(user_id,code,name,created_at,added_price,added_at,added_reason)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(user_id,code) DO UPDATE SET
                         name=excluded.name,
                         added_price=COALESCE(watchlist.added_price, excluded.added_price),
                         added_at=COALESCE(watchlist.added_at, excluded.added_at),
                         added_reason=COALESCE(watchlist.added_reason, excluded.added_reason)""",
                    (uid,code,name_for(code),now,added_price,now,reason))
        con.commit()
    return {"ok":True,"code":code,"name":name_for(code),"added_price":added_price,"added_at":now}

def get_watchlist_analysis_user(uid, force=False):
    _ensure_seed(uid); _ensure_watchlist_meta_columns()
    with _conn() as con:
        rows=con.execute("SELECT * FROM watchlist WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    out=[]
    for r in rows:
        d = (_analyze_user_full_v67(r["code"], uid, force) if force else analyze_user_light(r["code"], uid))
        added_price=_safe_float(r['added_price']) if 'added_price' in r.keys() else None
        if not added_price:
            added_price=_safe_float(d.get('price'))
        d.update({
            'added_price': added_price,
            'added_at': r['added_at'] if 'added_at' in r.keys() and r['added_at'] else r['created_at'],
            'added_reason': r['added_reason'] if 'added_reason' in r.keys() else '監視追加',
        })
        cur=_safe_float(d.get('price'))
        if added_price and cur:
            d['watch_change']=round(cur-added_price,2)
            d['watch_change_pct']=round((cur-added_price)/added_price*100,2) if added_price else None
        else:
            d['watch_change']=None; d['watch_change_pct']=None
        out.append(d)
    if not force:
        start_background_scan(uid, force=False)
    return out

def get_watch_performance_user(uid, force=False):
    items=get_watchlist_analysis_user(uid, force=force)
    valid=[x for x in items if x.get('watch_change_pct') is not None]
    winners=[x for x in valid if x.get('watch_change_pct',0)>0]
    losers=[x for x in valid if x.get('watch_change_pct',0)<0]
    avg=round(sum(x['watch_change_pct'] for x in valid)/len(valid),2) if valid else 0
    win_rate=round(len(winners)/len(valid)*100,1) if valid else 0
    best=sorted(valid, key=lambda x:x.get('watch_change_pct') or -999, reverse=True)[:8]
    worst=sorted(valid, key=lambda x:x.get('watch_change_pct') or 999)[:8]
    theme_stats={}
    for x in valid:
        theme=(x.get('theme_tags') or [x.get('theme') or '通常'])[0]
        theme_stats.setdefault(theme,[]).append(x['watch_change_pct'])
    themes=[]
    for k,vals in theme_stats.items():
        themes.append({'theme':k,'count':len(vals),'avg_pct':round(sum(vals)/len(vals),2),'win_rate':round(sum(1 for v in vals if v>0)/len(vals)*100,1)})
    themes=sorted(themes,key=lambda x:x['avg_pct'],reverse=True)[:8]
    comments=[]
    if valid:
        comments.append('監視追加後の平均がプラスなら、AI監視の初動検知は機能しています。')
        if win_rate < 50: comments.append('勝率50%未満。監視追加条件を「材料点」「出来高」で絞る方が安全。')
        if avg > 3: comments.append('平均上昇率が良好。監視後の押し目・ブレイク確認を強化するとさらに使える。')
    else:
        comments.append('監視追加時価格がまだ少ないため、今後の監視追加から分析精度が上がります。')
    return {'ok':True,'updated_at':datetime.now().strftime('%H:%M'),'summary':{'watch_count':len(items),'valid_count':len(valid),'avg_pct':avg,'win_rate':win_rate,'best_count':len(best),'worst_count':len(worst)},'items':items,'best':best,'worst':worst,'themes':themes,'comments':comments}


def _entry_signal_type(item, st):
    """銘柄の今の型を判定。ブレイク/押し目/リバーサル/過熱追随/見送り。"""
    price = _safe_float(item.get("price")) or 0
    sma25 = _safe_float(st.get("sma25")) or _safe_float(st.get("ma25"))
    sma75 = _safe_float(st.get("sma75")) or _safe_float(st.get("ma75"))
    vwap = _safe_float(st.get("vwap"))
    rsi = _safe_float(st.get("rsi14"))
    vol = _safe_float(st.get("volume_ratio")) or 1
    resistance = _safe_float(st.get("resistance"))
    support = _safe_float(st.get("support"))

    if price and resistance and price >= resistance * 0.985 and vol >= 1.15:
        return "ブレイク監視型"
    if price and sma25 and price >= sma25 and price <= sma25 * 1.08 and vol >= 0.8:
        return "押し目型"
    if price and support and price <= support * 1.08 and rsi is not None and rsi <= 45:
        return "リバーサル型"
    if rsi is not None and rsi >= 72 and vol < 1.8:
        return "過熱追随型"
    return "見送り型"

def _entry_plan_by_type(item, st, price, signal_type):
    """型ごとに現実的な買いゾーン/損切り/利確を作る。最終防衛ラインを買い場扱いしない。"""
    support = _safe_float(st.get("support"))
    resistance = _safe_float(st.get("resistance"))
    sma25 = _safe_float(st.get("sma25")) or _safe_float(st.get("ma25"))
    sma75 = _safe_float(st.get("sma75")) or _safe_float(st.get("ma75"))
    vwap = _safe_float(st.get("vwap"))
    high = _safe_float(st.get("high")) or resistance
    low = _safe_float(st.get("low")) or support

    # 最終防衛ライン: 遠い支持線。これは買い場ではなくシナリオ崩壊確認用。
    final_defense = support if support else (price * 0.90 if price else None)

    if signal_type == "ブレイク監視型":
        # 高値/抵抗付近のブレイク型。押し目は現在値から3〜8%程度までを現実ゾーンにする
        base = resistance or price
        buy_low = max(price * 0.92, (sma25 or price * 0.94), (vwap or price * 0.94))
        buy_high = min(price * 1.01, base * 1.01)
        stop = min(price * 0.94, buy_low * 0.975)
        tp1 = max(price * 1.035, (high or price) * 1.02)
        tp2 = max(price * 1.075, (high or price) * 1.06)
        entry_style = "高値ブレイク・初押し待ち"

    elif signal_type == "押し目型":
        anchor = max([x for x in [sma25, vwap, price * 0.94] if x])
        buy_low = anchor * 0.985
        buy_high = min(price * 0.995, anchor * 1.035)
        stop = min(anchor * 0.965, price * 0.93)
        tp1 = max(price * 1.035, (resistance or price) * 1.01)
        tp2 = max(price * 1.07, (resistance or price) * 1.05)
        entry_style = "初押し・VWAP/SMA25反発待ち"

    elif signal_type == "リバーサル型":
        anchor = support or price * 0.95
        buy_low = anchor * 0.99
        buy_high = anchor * 1.04
        stop = anchor * 0.965
        tp1 = price * 1.04
        tp2 = price * 1.08
        entry_style = "反転確認後の逆張り"

    else:
        buy_low = price * 0.94 if price else None
        buy_high = price * 0.985 if price else None
        stop = price * 0.92 if price else None
        tp1 = price * 1.03 if price else None
        tp2 = price * 1.06 if price else None
        entry_style = "見送り優先"

    def r(v): return round(v, 1) if v is not None else None
    return {
        "entry_style": entry_style,
        "buy_zone_low": r(buy_low),
        "buy_zone_high": r(buy_high),
        "final_defense": r(final_defense),
        "loss_cut": r(stop),
        "take_profit_1": r(tp1),
        "take_profit_2": r(tp2),
    }


def _latest_chart_price_for_entry(code):
    """エントリー最終確認用: 現在値は必ずチャート最新足から取る。"""
    try:
        ch = get_chart(code, range_="3mo", interval="1d", force=True)
        data = ch.get("data") or []
        if data:
            last = data[-1] or {}
            prev = data[-2] if len(data) >= 2 else last
            price = _safe_float(last.get("close"))
            prev_close = _safe_float(prev.get("close"))
            if price:
                return {
                    "price": price,
                    "prev_close": prev_close,
                    "change": None if prev_close in (None, 0) else price - prev_close,
                    "change_pct": None if prev_close in (None, 0) else (price - prev_close) / prev_close * 100,
                    "price_source": "entry_chart_latest"
                }
    except Exception:
        pass
    return {}

def get_entry_check_user(uid, code, entry_price=None, shares=None, hold_days=None, force=False):
    code = normalize_code(code)
    if not code:
        return {'ok': False, 'error': '銘柄コードを入力'}

    # v118: 価格ズレ防止のため最新分析を強制
    item = _analyze_user_full_v67(code, uid, force=True)
    st = item.get('strategy') or {}
    latest_price_obj = _latest_chart_price_for_entry(code)
    if latest_price_obj.get('price'):
        item.update(latest_price_obj)
    current_price = _safe_float(item.get('price')) or 0
    # entry_priceは「予定価格」。現在値とは分離する。空欄なら現在値を予定価格にする。
    planned_price = _safe_float(entry_price)
    price = planned_price or current_price
    shares = _safe_float(shares) or 100
    hold_days = int(_safe_float(hold_days) or 7)

    match = _my_pattern_match(item).get('match_rate', 0)
    ai_score = item.get('ai_score') or 0
    material = item.get('catalyst_score') or 0
    rsi = _safe_float(st.get('rsi14'))
    vol = _safe_float(st.get('volume_ratio')) or 1
    status = str(st.get('status') or '')
    signal_type = _entry_signal_type(item, st)
    plan = _entry_plan_by_type(item, st, price, signal_type)

    stop = plan['loss_cut']
    tp1 = plan['take_profit_1']
    tp2 = plan['take_profit_2']
    buy_low = plan['buy_zone_low']
    buy_high = plan['buy_zone_high']

    risk_yen = round(max(0, (price - stop)) * shares) if price and stop else None
    reward_yen = round(max(0, (tp1 - price)) * shares) if price and tp1 else None
    rr = round((tp1 - price) / (price - stop), 2) if price and stop and tp1 and price > stop else None

    good_flags = []
    risk_flags = []
    wait_flags = []

    if match >= 75:
        good_flags.append('勝ちパターン一致率75%以上')
    elif match >= 65:
        good_flags.append('勝ちパターン一致率65%以上')
    else:
        risk_flags.append('勝ちパターン一致率が不足')

    if ai_score >= 85:
        good_flags.append('AI総合85以上')
    if material >= 35:
        good_flags.append('材料点35以上')
    elif material >= 20:
        good_flags.append('材料点20以上')
    else:
        wait_flags.append('材料点が弱い')

    if vol >= 1.8:
        good_flags.append('出来高急増')
    elif vol >= 1.1:
        good_flags.append('出来高増加')
    else:
        wait_flags.append('出来高不足')

    if signal_type in ('ブレイク監視型', '押し目型'):
        good_flags.append(signal_type)
    elif signal_type == '過熱追随型':
        risk_flags.append('過熱追随になりやすい')
    else:
        wait_flags.append('型が弱い')

    if rsi is not None:
        if rsi >= 78:
            risk_flags.append('RSI過熱すぎ')
        elif rsi >= 70:
            wait_flags.append('RSI70超え。飛びつき注意')
        elif 45 <= rsi <= 68:
            good_flags.append('RSIが実戦許容帯')

    # 現在値が買いゾーンより上に離れすぎなら「今すぐ買う」ではなく押し目待ち
    if price and buy_high and price > buy_high * 1.025:
        wait_flags.append('現在値が押し目買いゾーンより上。飛びつき注意')
    if price and buy_low and price < buy_low * 0.97:
        risk_flags.append('買いゾーンを下抜け気味')

    if rr is not None:
        if rr >= 1.6:
            good_flags.append('リスクリワード良好')
        elif rr < 0.9:
            risk_flags.append('リスクリワードが悪い')
        elif rr < 1.2:
            wait_flags.append('リスクリワード微妙')

    if price and stop and (price - stop) / price > 0.09:
        risk_flags.append('損切り幅が広い')

    # 到達確率をざっくり推定。RRだけでなく、型・材料・一致率・出来高で見る
    probability = 40
    probability += min(20, max(0, (match - 50) * 0.45))
    probability += min(15, max(0, (ai_score - 60) * 0.25))
    probability += min(12, material * 0.20)
    probability += min(10, (vol - 1.0) * 8)
    if signal_type == 'ブレイク監視型': probability += 8
    if signal_type == '押し目型': probability += 10
    if signal_type == '過熱追随型': probability -= 18
    if rsi is not None and rsi >= 75: probability -= 10
    probability -= min(20, len(risk_flags) * 6)
    probability = max(20, min(88, round(probability, 1)))

    score = 0
    score += ai_score * 0.25
    score += match * 0.30
    score += material * 0.18
    score += probability * 0.22
    score += 8 if rr and rr >= 1.5 else (-12 if rr and rr < 1.0 else 0)
    score += 8 if signal_type in ('ブレイク監視型', '押し目型') else 0
    score -= min(28, len(risk_flags) * 7)
    score -= min(18, len(wait_flags) * 3)
    score = max(0, min(100, score))

    # 判定は「今買い」「押し目待ち」「監視」「触るな」に分ける
    if score >= 78 and len(risk_flags) <= 1 and not (price and buy_high and price > buy_high * 1.025):
        verdict = '買い候補。ただし逆指値必須'
    elif score >= 70 and signal_type in ('ブレイク監視型', '押し目型'):
        verdict = '監視強め。押し目か再上抜け待ち'
    elif score >= 58:
        verdict = '待て。条件が揃うまで入らない'
    else:
        verdict = '触るな。期待値が低い'

    deadline = (datetime.now() + timedelta(days=hold_days)).strftime('%Y/%m/%d')

    result = {
        'ok': True,
        'code': code,
        'name': name_for(code),
        'entry_price': price,
        'planned_entry_price': price,
        'planned_price_was_blank': planned_price is None,
        'live_current_price': current_price,
        'shares': shares,
        'hold_days': hold_days,
        'deadline': deadline,
        'verdict': verdict,
        'entry_score': round(score, 1),
        'expected_win_rate': probability,
        'signal_type': signal_type,
        'entry_style': plan['entry_style'],
        'pattern_match': match,
        'ai_score': ai_score,
        'material_score': material,
        'current_price': current_price,
        'price_source': item.get('price_source'),
        'buy_zone_low': buy_low,
        'buy_zone_high': buy_high,
        'final_defense': plan['final_defense'],
        'take_profit_1': tp1,
        'take_profit_2': tp2,
        'loss_cut': stop,
        'risk_yen': risk_yen,
        'reward_yen': reward_yen,
        'risk_reward': rr,
        'good_flags': good_flags,
        'risk_flags': risk_flags,
        'wait_flags': wait_flags,
        'reason': ' / '.join((good_flags + wait_flags + risk_flags)[:8]),
        'item': item,
        'updated_at': datetime.now().strftime('%H:%M')
    }
    result['entry_price_ai'] = _v121_entry_price_ai(result)
    result['price_ladder'] = _v125_price_ladder_ai(result)
    return result


def _v127_question_intent(q):
    q = str(q or '')
    if any(k in q for k in ['BTC','ビットコイン','仮想通貨','暗号資産','crypto','bitcoin']):
        return 'btc_dependency'
    if any(k in q for k in ['いくら','何円','どこで','価格','指値','エントリーしたら','エントリーするべき']):
        return 'entry_price'
    if any(k in q for k in ['いける','今買','今入','買っていい','入っていい','今エントリー']):
        return 'buy_now'
    if any(k in q for k in ['大口','買い支え','板','吸収','支え']):
        return 'big_money'
    if any(k in q for k in ['損切','逆指値','ロスカット']):
        return 'loss_cut'
    if any(k in q for k in ['利確','売り','出口']):
        return 'take_profit'
    if any(k in q for k in ['決算','跨ぎ','開示','IR']):
        return 'earnings'
    return 'general'

def get_entry_chat_user(uid, code, question, entry_price=None, shares=None, hold_days=None, force=False):
    """v127: 質問分類型の実戦チャットAI。テンプレ総合回答ではなく質問意図に答える。"""
    code = normalize_code(code)
    q = str(question or '').strip()
    if not code:
        return {'ok': False, 'error': '銘柄コードを入力'}
    if not q:
        return {'ok': False, 'error': '質問を入力'}

    core = _v120_trader_core(uid, code, entry_price, shares, hold_days)
    if not core.get('ok'):
        return core
    base = core.get('entry_check') or {}
    p = base.get('entry_price_ai') or _v121_entry_price_ai(base)
    item = base.get('item') or {}
    st = item.get('strategy') or {}
    intent = _v127_question_intent(q)

    current = p.get('current_price') or base.get('live_current_price') or base.get('current_price')
    main_low, main_high = p.get('main_entry_low'), p.get('main_entry_high')
    comp_low, comp_high = p.get('compromise_entry_low'), p.get('compromise_entry_high')
    brk, brk_ok = p.get('breakout_trigger'), p.get('breakout_confirm')
    stop, tp1, tp2 = p.get('loss_cut'), p.get('take_profit_1'), p.get('take_profit_2')
    rr = p.get('rr_at_planned') or base.get('risk_reward')
    strength = p.get('strength_label') or ''
    pos_label = p.get('position_label') or ''
    vol = _safe_float(st.get('volume_ratio')) or 1
    rsi = _safe_float(st.get('rsi14'))
    chg = _safe_float(item.get('change_pct')) or 0

    def yen(x): 
        return '—' if x is None else f"{round(float(x),1):,.1f}円"

    if intent == 'btc_dependency':
        answer = (
            f"結論：この銘柄はBTCそのものへの直接連動ではなく、テーマ/地合い連動を見る方が重要。\n"
            f"今見るべきはBTCより、半導体・AIテーマ、日経/TOPIX、出来高、上値追いの継続性。\n\n"
            f"現在値：{yen(current)} / 型：{base.get('signal_type')} / {strength}\n"
            f"出来高倍率：{round(vol,2)}倍 / RSI：{round(rsi,1) if rsi is not None else '—'} / 前日比：{round(chg,2)}%\n\n"
            f"実戦判断：BTCが上がっていても、この銘柄の本命は {yen(main_low)}〜{yen(main_high)}。\n"
            f"今すぐ見る条件は、{yen(brk)}突破→{yen(brk_ok)}定着。これがなければ追いかけすぎ注意。"
        )
    elif intent == 'entry_price':
        answer = (
            f"結論：本命エントリーは {yen(main_low)}〜{yen(main_high)}。\n"
            f"妥協なら {yen(comp_low)}〜{yen(comp_high)}。\n"
            f"追撃なら {yen(brk)}突破、できれば {yen(brk_ok)}定着。\n\n"
            f"現在値は {yen(current)}。入力価格の評価は「{pos_label}」。\n"
            f"損切りは {yen(stop)}、第1利確は {yen(tp1)}、RRは {rr if rr is not None else '—'}。\n\n"
            f"つまり、成行で迷うなら本命ゾーンまで待つ。強く買うなら追撃条件を満たしてから。"
        )
    elif intent == 'buy_now':
        if p.get('position_score',0) >= 80:
            conclusion = "買い候補。損切り先置きなら検討可"
        elif p.get('position_score',0) >= 68:
            conclusion = "小さめなら可。本命ではなく試し玉"
        else:
            conclusion = "今は待ち優先。飛びつき気味"
        answer = (
            f"結論：{conclusion}。\n"
            f"理由：現在値 {yen(current)}、本命ゾーン {yen(main_low)}〜{yen(main_high)}、評価「{pos_label}」。\n"
            f"{strength} / RSI {round(rsi,1) if rsi is not None else '—'} / 出来高 {round(vol,2)}倍。\n\n"
            f"今買う条件：{yen(brk)}を出来高付きで突破して、{yen(brk_ok)}に定着。\n"
            f"待つ条件：{yen(main_low)}〜{yen(main_high)}まで押して反発。\n"
            f"損切り：{yen(stop)}。"
        )
    elif intent == 'big_money':
        if vol >= 2 and chg >= 0:
            big = "大口/買い支え気配はあり"
        elif vol >= 1.3 and chg >= 0:
            big = "やや買い優勢。ただし大口断定は不可"
        else:
            big = "大口感は弱い"
        answer = (
            f"結論：{big}。\n"
            f"無料版は実板を取れてないから、出来高と値動きからの推定。\n"
            f"出来高倍率 {round(vol,2)}倍、前日比 {round(chg,2)}%。\n\n"
            f"大口を理由に入るなら、{yen(brk)}突破＋出来高増、または {yen(main_low)}〜{yen(main_high)}で下げ止まり確認が必要。"
        )
    elif intent == 'loss_cut':
        answer = (
            f"結論：損切りは {yen(stop)}。\n"
            f"最終防衛ラインは {yen(p.get('final_defense'))}。ここは買い場ではなく、崩壊確認ライン。\n\n"
            f"入る前に逆指値を置く。{yen(stop)}を割ったらシナリオ崩れで撤退。"
        )
    elif intent == 'take_profit':
        answer = (
            f"結論：第1利確は {yen(tp1)}、第2利確は {yen(tp2)}。\n"
            f"追撃条件は {yen(brk)}突破→{yen(brk_ok)}定着。\n\n"
            f"第1利確到達後は半分利確、残りは建値〜損切り引き上げが安全。"
        )
    elif intent == 'earnings':
        answer = (
            "結論：決算/IRが近いならロットを落とすか跨がない。\n"
            "無料版ではTDnet導線とキーワード警告まで。決算日完全自動取得は追加APIが必要。\n\n"
            f"この銘柄で見るキーワード：上方修正・増配・自社株買い・株式分割・希薄化・下方修正・減損。"
        )
    else:
        answer = (
            f"結論：この質問なら、まず「銘柄が強いか」より「今の位置が良いか」を見る。\n"
            f"現在値 {yen(current)}、本命 {yen(main_low)}〜{yen(main_high)}、追撃 {yen(brk)}突破→{yen(brk_ok)}定着。\n"
            f"評価は「{pos_label}」。損切り {yen(stop)}。\n\n"
            f"聞き方の例：『何円で入る？』『今買っていい？』『大口いる？』『損切りどこ？』"
        )

    return {
        'ok': True,
        'code': code,
        'question': q,
        'intent': intent,
        'answer': answer,
        'action': p.get('recommendation'),
        'entry_check': base,
        'trader_core': core,
        'updated_at': datetime.now().strftime('%H:%M')
    }



# ===== v120 TRADER AI CORE =====
def _v120_market_phase_ai(item, st):
    score = 50
    notes = []
    chg = _safe_float(item.get('change_pct')) or 0
    ai = _safe_float(item.get('ai_score')) or 0
    mat = _safe_float(item.get('catalyst_score')) or 0
    vol = _safe_float(st.get('volume_ratio')) or 1
    rsi = _safe_float(st.get('rsi14'))

    if chg > 0: score += 8; notes.append('個別はプラス圏')
    if ai >= 80: score += 8; notes.append('AI総合が強い')
    if mat >= 25: score += 8; notes.append('材料点が強い')
    if vol >= 1.5: score += 10; notes.append('出来高が増えている')
    if rsi is not None and rsi >= 75: score -= 10; notes.append('短期過熱')
    if chg < -3: score -= 10; notes.append('個別が弱い')

    score = max(0, min(100, round(score,1)))
    label = '攻め相場' if score >= 70 else ('中立相場' if score >= 50 else '防御相場')
    return {'name':'市場フェーズAI','score':score,'label':label,'notes':notes or ['個別データ中心で判定']}

def _v120_no_touch_ai(item, st):
    score = 0
    reasons = []
    rsi = _safe_float(st.get('rsi14'))
    vol = _safe_float(st.get('volume_ratio')) or 1
    chg = _safe_float(item.get('change_pct')) or 0
    status = str(st.get('status') or '')

    if rsi is not None and rsi >= 78: score += 28; reasons.append('RSI過熱すぎ')
    if chg >= 8 and vol < 1.3: score += 20; reasons.append('上昇に出来高が伴っていない')
    if '過熱' in status: score += 18; reasons.append('戦略判定が過熱注意')
    if vol < 0.75: score += 12; reasons.append('出来高不足')
    if chg <= -5: score += 18; reasons.append('急落中')

    label = '触るな' if score >= 45 else ('注意' if score >= 25 else '問題なし')
    return {'name':'今触るなAI','score':min(100,score),'label':label,'notes':reasons or ['致命的な触るな条件は少ない']}

def _v120_order_flow_ai(item, st):
    score = 50
    notes = []
    vol = _safe_float(st.get('volume_ratio')) or 1
    chg = _safe_float(item.get('change_pct')) or 0
    rsi = _safe_float(st.get('rsi14'))

    if vol >= 2.0 and chg >= 0: score += 22; notes.append('出来高急増＋値上がりで需給良好')
    elif vol >= 1.3: score += 12; notes.append('出来高増加')
    if chg > 3 and vol >= 1.5: score += 10; notes.append('買い優勢の値動き')
    if chg < 0 and vol >= 1.8: score -= 18; notes.append('売り出来高の可能性')
    if rsi is not None and rsi > 75: score -= 8; notes.append('短期過熱で上値重い可能性')

    score = max(0, min(100, round(score,1)))
    label = '買い需給優勢' if score >= 70 else ('中立' if score >= 45 else '売り需給注意')
    return {'name':'板・需給AI','score':score,'label':label,'notes':notes or ['板情報なし。出来高/値動きから推定']}

def _v120_big_money_ai(item, st):
    score = 45
    notes = []
    vol = _safe_float(st.get('volume_ratio')) or 1
    chg = _safe_float(item.get('change_pct')) or 0
    ai = _safe_float(item.get('ai_score')) or 0

    if vol >= 2.0 and -1 <= chg <= 5: score += 25; notes.append('出来高増でも崩れていない')
    if vol >= 1.5 and chg > 0: score += 15; notes.append('買い資金流入の可能性')
    if ai >= 85 and vol >= 1.2: score += 8; notes.append('強い銘柄に出来高が乗っている')
    if vol < 1.0: score -= 15; notes.append('大口感は薄い')

    score = max(0, min(100, round(score,1)))
    label = '大口気配あり' if score >= 70 else ('ややあり' if score >= 55 else '薄い')
    return {'name':'大口AI','score':score,'label':label,'notes':notes or ['リアル板なし。出来高と崩れにくさから推定']}

def _v120_loss_delay_ai(base):
    score = 0
    notes = []
    price = _safe_float(base.get('entry_price')) or 0
    stop = _safe_float(base.get('loss_cut'))
    defense = _safe_float(base.get('final_defense'))
    if price and stop:
        width = (price-stop)/price*100
        if width > 10: score += 25; notes.append('損切り幅が広すぎる')
        elif width > 7: score += 12; notes.append('損切り幅やや広い')
    if defense and stop and stop < defense * 0.98:
        score += 10; notes.append('損切りが最終防衛ラインより下寄り')
    label = '損切り遅れ注意' if score >= 25 else ('やや注意' if score >= 10 else '問題なし')
    return {'name':'損切り遅れAI','score':min(100,score),'label':label,'notes':notes or ['損切り位置は許容範囲']}

def _v120_ev_decay_ai(item, st, base):
    score = 100
    notes = []
    vol = _safe_float(st.get('volume_ratio')) or 1
    rsi = _safe_float(st.get('rsi14'))
    rr = _safe_float(base.get('risk_reward'))
    if vol < 0.8: score -= 18; notes.append('出来高が弱く期待値が落ちやすい')
    if rsi is not None and rsi >= 78: score -= 18; notes.append('過熱で期待値消滅リスク')
    if rr is not None and rr < 1.0: score -= 25; notes.append('RRが悪い')
    if (base.get('signal_type') or '') == '見送り型': score -= 18; notes.append('型が弱い')
    score = max(0, min(100, round(score,1)))
    label = '期待値あり' if score >= 70 else ('低下注意' if score >= 45 else '期待値消滅')
    return {'name':'期待値消滅AI','score':score,'label':label,'notes':notes or ['期待値はまだ残っている']}

def _v120_wait_ai(base):
    p = base.get('entry_price_ai') or {}
    score = 50
    notes = []
    planned = _safe_float(p.get('planned_price')) or _safe_float(base.get('entry_price')) or 0
    high = _safe_float(p.get('main_entry_high'))
    low = _safe_float(p.get('main_entry_low'))
    if planned and high and planned > high * 1.025:
        score += 30; notes.append('予定価格がAI本命ゾーンより上。待つ価値が高い')
    if planned and low and planned < low * 0.97:
        score += 20; notes.append('本命ゾーン下抜け。反発確認待ち')
    if '待て' in str(base.get('verdict')) or '監視' in str(base.get('verdict')):
        score += 12; notes.append('期待値AIも待ち判定')
    score = max(0, min(100, round(score,1)))
    label = '待機優先' if score >= 70 else ('条件待ち' if score >= 55 else '即時検討可')
    return {'name':'待機AI','score':score,'label':label,'notes':notes or ['待つ理由は強くない']}

def _v120_position_size_ai(base):
    score = _safe_float(base.get('entry_score')) or 0
    rr = _safe_float(base.get('risk_reward')) or 0
    risks = len(base.get('risk_flags') or [])
    if score >= 80 and rr >= 1.4 and risks <= 1:
        label, size = '通常〜やや強め', '資金の20〜30%まで'
    elif score >= 70:
        label, size = '小さめ', '資金の10〜20%'
    elif score >= 58:
        label, size = '試し玉のみ', '資金の5〜10%'
    else:
        label, size = 'ノートレ', '0%'
    return {'name':'資金管理AI','score':round(score,1),'label':label,'notes':[size, '迷う時はロットを落とす']}

def _v120_psychology_ai(base):
    notes = []
    label = '冷静'
    score = 70
    if '飛びつき' in ' '.join(base.get('wait_flags') or []):
        score -= 20; label = '飛びつき注意'; notes.append('価格が買いゾーンより上。焦り買い注意')
    if '触るな' in str(base.get('verdict')):
        score -= 18; label = '感情買い禁止'; notes.append('AI判定が弱い時に入るのは感情トレード')
    if not notes:
        notes.append('ルール通りならメンタルリスクは低め')
    return {'name':'心理AI','score':max(0,score),'label':label,'notes':notes}

def _v120_future_ev_ai(item, st, base):
    score = 45
    notes = []
    vol = _safe_float(st.get('volume_ratio')) or 1
    mat = _safe_float(item.get('catalyst_score')) or 0
    signal = base.get('signal_type') or ''
    if mat >= 35: score += 18; notes.append('材料点が高く継続資金の可能性')
    if vol >= 1.5: score += 15; notes.append('出来高が増え、2日以内の継続監視価値あり')
    if signal in ('ブレイク監視型','押し目型'): score += 12; notes.append('型が継続向き')
    if _safe_float(st.get('rsi14')) and _safe_float(st.get('rsi14')) >= 78:
        score -= 12; notes.append('短期過熱で一旦冷ます可能性')
    score = max(0, min(100, round(score,1)))
    label = '近未来期待あり' if score >= 70 else ('監視継続' if score >= 55 else '弱い')
    return {'name':'未来の期待値AI','score':score,'label':label,'notes':notes or ['次の資金集中はまだ弱い']}

def _v120_trader_core(uid, code, entry_price=None, shares=None, hold_days=None):
    base = get_entry_check_user(uid, code, entry_price, shares, hold_days, force=True)
    if not base.get('ok'):
        return {'ok':False,'error':base.get('error','entry check failed')}
    item = base.get('item') or {}
    st = item.get('strategy') or {}
    modules = [
        _v120_market_phase_ai(item, st),
        _v120_no_touch_ai(item, st),
        _v120_order_flow_ai(item, st),
        _v120_big_money_ai(item, st),
        _v120_loss_delay_ai(base),
        _v120_ev_decay_ai(item, st, base),
        _v120_wait_ai(base),
        _v120_position_size_ai(base),
        _v120_psychology_ai(base),
        _v120_future_ev_ai(item, st, base),
    ]
    good = sum(1 for m in modules if m['score'] >= 70)
    danger = sum(1 for m in modules if ('触るな' in m['label'] or '消滅' in m['label'] or '禁止' in m['label']))
    core_score = round(sum(m['score'] for m in modules)/len(modules),1)
    if danger >= 2:
        final = 'ノートレ。危険AIが複数点灯'
    elif core_score >= 72 and base.get('entry_score',0) >= 70:
        final = '買い候補。ただし損切り先置き'
    elif core_score >= 60:
        final = '監視強め。条件が揃えば入る'
    else:
        final = '待機。無理に触らない'
    return {'ok':True,'core_score':core_score,'final_judgement':final,'modules':modules,'entry_check':base,'updated_at':datetime.now().strftime('%H:%M')}


def get_trader_core_user(uid, code, entry_price=None, shares=None, hold_days=None, force=True):
    code = normalize_code(code)
    if not code:
        return {'ok':False,'error':'銘柄コードを入力'}
    return _v120_trader_core(uid, code, entry_price, shares, hold_days)


# ===== v121 ENTRY PRICE AI =====

def _v123_chart_dynamic_zone(base):
    """チャート連動の動的押し目ゾーン。
    予定価格には一切引っ張られない。現在値・VWAP/SMA・支持抵抗・RSI・出来高から決める。
    """
    item = base.get('item') or {}
    st = item.get('strategy') or {}

    current = _safe_float(base.get('live_current_price')) or _safe_float(base.get('current_price')) or _safe_float(item.get('price')) or _safe_float(base.get('entry_price')) or 0
    planned = _safe_float(base.get('planned_entry_price')) or _safe_float(base.get('entry_price')) or current

    support = _safe_float(st.get('support'))
    resistance = _safe_float(st.get('resistance'))
    sma25 = _safe_float(st.get('sma25')) or _safe_float(st.get('ma25'))
    sma75 = _safe_float(st.get('sma75')) or _safe_float(st.get('ma75'))
    vwap = _safe_float(st.get('vwap'))
    rsi = _safe_float(st.get('rsi14'))
    vol = _safe_float(st.get('volume_ratio')) or 1
    signal = base.get('signal_type') or ''

    if not current:
        return {'ok': False, 'error': '現在値取得不可'}

    anchors = []
    if vwap: anchors.append(('VWAP', vwap))
    if sma25: anchors.append(('SMA25', sma25))
    if support: anchors.append(('支持線', support))
    if sma75: anchors.append(('SMA75', sma75))

    # 現在値から近すぎず遠すぎない、実戦で使える押し目候補を作る
    # 入力価格 planned はここでは使わない
    ai_power = _safe_float(base.get('ai_score')) or _safe_float(item.get('ai_score')) or 0
    material_power = _safe_float(base.get('material_score')) or _safe_float(item.get('catalyst_score')) or 0
    match_power = _safe_float(base.get('pattern_match')) or 0
    strength_score = ai_power * 0.35 + material_power * 0.35 + match_power * 0.30
    # 強い銘柄は深押しを待ちすぎない。弱い銘柄は深押し要求。
    if strength_score >= 72:
        pullback_low, pullback_high = 0.955, 0.985
        strength_label = 'S級/強銘柄：浅押し許容'
    elif strength_score >= 60:
        pullback_low, pullback_high = 0.93, 0.97
        strength_label = '強め：標準押し'
    else:
        pullback_low, pullback_high = 0.88, 0.94
        strength_label = '弱め：深押し待ち'

    if signal == 'ブレイク監視型':
        base_anchor_candidates = [x for _, x in anchors if current * pullback_low <= x <= current * 1.005]
        anchor = max(base_anchor_candidates) if base_anchor_candidates else current * ((pullback_low + pullback_high) / 2)
        zone_low = max(current * pullback_low, anchor * 0.99)
        zone_high = min(current * pullback_high, anchor * 1.025)
        entry_type = 'ブレイク後の初押しゾーン'
    elif signal == '押し目型':
        base_anchor_candidates = [x for _, x in anchors if current * pullback_low <= x <= current * 1.01]
        anchor = max(base_anchor_candidates) if base_anchor_candidates else current * ((pullback_low + pullback_high) / 2)
        zone_low = max(current * pullback_low, anchor * 0.99)
        zone_high = min(current * 0.995, max(current * pullback_high, anchor * 1.02))
        entry_type = 'VWAP/SMA25押し目ゾーン'
    elif signal == 'リバーサル型':
        anchor = support or current * 0.95
        zone_low = anchor * 0.995
        zone_high = anchor * 1.035
        entry_type = '反転確認ゾーン'
    else:
        anchor = max([x for _, x in anchors if x < current] or [current * 0.95])
        zone_low = anchor * 0.99
        zone_high = min(current * 0.99, anchor * 1.03)
        entry_type = '待機優先ゾーン'

    # ゾーンが逆転/狭すぎる時の補正
    if zone_high <= zone_low:
        mid = (zone_high + zone_low) / 2
        zone_low, zone_high = mid * 0.985, mid * 1.015

    final_defense = support if support else current * 0.90

    # v125 safety: 押し目ゾーンは必ず最終防衛ラインより上。
    # 最低でも2.5%上にない場合は、ノイズで即損切りになりやすいので自動補正。
    min_zone_low = final_defense * 1.025 if final_defense else zone_low
    if zone_low <= min_zone_low:
        zone_low = min_zone_low
    if zone_high <= zone_low * 1.012:
        zone_high = zone_low * 1.025

    loss_cut = min(zone_low * 0.975, final_defense * 0.995 if final_defense else zone_low * 0.975)
    # 利確は現在値基準ではなく、エントリーゾーンから見た上値余地も考慮
    take_profit_1 = max(zone_high * 1.035, current * 1.025, (resistance or current) * 1.012)
    take_profit_2 = max(zone_high * 1.075, current * 1.055, (resistance or current) * 1.05)

    # 入力価格評価
    if planned < zone_low:
        position_label = '安すぎる。刺さらないか、崩れ始めの可能性'
        position_score = 55
    elif zone_low <= planned <= zone_high:
        position_label = 'A 本命ゾーン内'
        position_score = 88
    elif planned <= zone_high * 1.025:
        position_label = 'B 妥協ゾーン。ロット小さめ'
        position_score = 70
    elif planned <= current * 1.005 and planned > zone_high * 1.025:
        position_label = 'C 飛び乗り気味'
        position_score = 48
    else:
        position_label = 'D 高値追い。期待値低下'
        position_score = 35

    # ブレイク追撃はゾーンとは別ルート
    breakout_trigger = max(current, resistance or current) * 1.006
    breakout_confirm = breakout_trigger * 1.012

    is_chasing = position_score < 55
    chase_reason = []
    if planned > zone_high * 1.025:
        chase_reason.append('予定価格が押し目ゾーン上限より高い')
    if rsi is not None and rsi >= 70:
        chase_reason.append('RSI70超えで短期過熱')
    rr_at_planned = None
    if planned and loss_cut and take_profit_1 and planned > loss_cut:
        rr_at_planned = round((take_profit_1 - planned) / (planned - loss_cut), 2)
        if rr_at_planned < 1.0:
            chase_reason.append('予定価格でのRRが1倍未満')

    recommendation = (
        f"本命は{round(zone_low,1)}〜{round(zone_high,1)}円。"
        f"予定価格{round(planned,1)}円は「{position_label}」。"
    )
    entry_score = _safe_float(base.get('entry_score')) or 0
    if position_score >= 82 and entry_score >= 70:
        share_recommendation = '通常ロット可'
        max_shares_note = '例：100株〜。損切りを先に置く'
    elif position_score >= 68:
        share_recommendation = '小さめロット'
        max_shares_note = '例：100株まで。追撃禁止'
    elif position_score >= 50:
        share_recommendation = '試し玉のみ'
        max_shares_note = '例：100株未満/最小単位だけ'
    else:
        share_recommendation = '今日は0株'
        max_shares_note = 'ノートレ。条件待ち'

    def r(v): return round(v, 1) if v is not None else None
    return {
        'ok': True,
        'current_price': r(current),
        'planned_price': r(planned),
        'main_entry_low': r(zone_low),
        'main_entry_high': r(zone_high),
        'compromise_entry_low': r(zone_high),
        'compromise_entry_high': r(zone_high * 1.025),
        'breakout_trigger': r(breakout_trigger),
        'breakout_confirm': r(breakout_confirm),
        'loss_cut': r(loss_cut),
        'take_profit_1': r(take_profit_1),
        'take_profit_2': r(take_profit_2),
        'final_defense': r(final_defense),
        'position_score': position_score,
        'position_label': position_label,
        'rr_at_planned': rr_at_planned,
        'is_chasing': is_chasing,
        'chase_reason': chase_reason,
        'recommendation': recommendation,
        'share_recommendation': share_recommendation,
        'max_shares_note': max_shares_note,
        'signal_type': signal,
        'entry_type': entry_type,
        'zone_basis': [f'{name}:{round(val,1)}' for name, val in anchors],
        'zone_is_independent_from_input': True,
        'strength_label': strength_label,
        'strength_score': round(strength_score,1),
    }

# backward compatibility: existing code calls _v121_entry_price_ai
def _v121_entry_price_ai(base):
    return _v123_chart_dynamic_zone(base)


def _v125_market_time_ai():
    """市場時間AI。厳密な祝日判定は未実装だが、曜日/時間で売買注意を出す。"""
    now = datetime.now()
    wd = now.weekday()
    hm = now.hour * 100 + now.minute
    notes = []
    risk = 0
    if wd >= 5:
        risk += 40; notes.append('休日。通常市場は動いていない')
    if hm < 900 or hm > 1530:
        risk += 18; notes.append('通常取引時間外。最新値/PTS差に注意')
    if 900 <= hm <= 930:
        risk += 12; notes.append('寄り付き直後。寄り天/乱高下注意')
    if 1430 <= hm <= 1530:
        risk += 10; notes.append('引け前。利確売り/持ち越し判断注意')
    return {'name':'市場時間AI','score':max(0,100-risk),'label':'通常' if risk<20 else ('注意' if risk<45 else '取引注意'), 'notes':notes or ['通常時間帯']}

def _v125_gap_stop_liquidity_ai(item, st, base):
    chg = _safe_float(item.get('change_pct')) or 0
    vol = _safe_float(st.get('volume_ratio')) or 1
    price = _safe_float(base.get('live_current_price')) or _safe_float(base.get('current_price')) or 0
    notes=[]; risk=0
    if chg >= 8:
        risk += 24; notes.append('大幅GU/急騰後。寄り天警戒')
    if chg <= -8:
        risk += 24; notes.append('大幅下落。セリクラ確認なしの逆張り注意')
    if abs(chg) >= 14:
        risk += 20; notes.append('値幅制限接近の可能性。ストップ高/安リスク')
    if vol < 0.7:
        risk += 18; notes.append('出来高不足。流動性/滑り注意')
    if price and price < 150:
        risk += 10; notes.append('低位株。値動き荒れやすい')
    label='問題なし' if risk<20 else ('注意' if risk<45 else '危険')
    return {'name':'GU/ストップ/流動性AI','score':max(0,100-risk),'label':label,'notes':notes or ['急騰急落・流動性の大きな警告なし']}

def _v125_decision_mode_ai(item, st, base):
    """銘柄が強いのか、今の位置が良いのかを分離して説明。"""
    ai = _safe_float(item.get('ai_score')) or 0
    pos = ((base.get('entry_price_ai') or {}).get('position_score')) or 0
    notes=[]
    if ai >= 80 and pos < 55:
        label='銘柄は強いが今の位置が悪い'
        notes.append('AI候補上位でも、エントリー位置が悪ければ待つ')
    elif ai >= 80 and pos >= 70:
        label='銘柄も位置も良い'
        notes.append('条件一致。損切り先置きで検討')
    elif pos >= 75:
        label='位置は良いが銘柄力は普通'
        notes.append('ロット控えめ')
    else:
        label='見送り優先'
        notes.append('銘柄力または位置のどちらかが不足')
    return {'name':'銘柄力×位置AI','score':round((ai+pos)/2,1),'label':label,'notes':notes}

def _v125_price_ladder_ai(base):
    p = base.get('entry_price_ai') or {}
    low=_safe_float(p.get('main_entry_low')); high=_safe_float(p.get('main_entry_high'))
    stop=_safe_float(p.get('loss_cut')); tp=_safe_float(p.get('take_profit_1'))
    if not low or not high:
        return []
    prices=[low, (low+high)/2, high, high*1.025, high*1.055]
    ladder=[]
    for pr in prices:
        rr=None
        if stop and tp and pr>stop:
            rr=round((tp-pr)/(pr-stop),2)
        if pr <= high:
            grade='A'
        elif pr <= high*1.025:
            grade='B'
        elif pr <= high*1.055:
            grade='C'
        else:
            grade='D'
        ladder.append({'price':round(pr,1),'grade':grade,'rr':rr})
    return ladder


# ===== v126 FREE DATA CORE =====
def _download_intraday_series_v126(code, interval="5m", range_="1d"):
    """無料範囲: Yahoo Finance chart endpointで分足を取得。非公式/不安定前提。"""
    code = normalize_code(code)
    try:
        arr, source = _download_series(code, range_=range_, interval=interval, force=True)
        return {"ok": True, "code": code, "interval": interval, "range": range_, "source": source, "data": arr[-120:]}
    except Exception as e:
        return {"ok": False, "code": code, "error": str(e), "data": []}

def _v126_intraday_ai(code):
    """5分/15分/60分/日足の無料マルチ時間足AI。"""
    frames = []
    for interval, range_ in [("5m","1d"),("15m","5d"),("60m","1mo"),("1d","3mo")]:
        r = _download_intraday_series_v126(code, interval, range_)
        data = r.get("data") or []
        if len(data) >= 5:
            last = data[-1]; prev = data[-5]
            close = _safe_float(last.get("close"))
            prev_close = _safe_float(prev.get("close"))
            chg = None if not close or not prev_close else (close-prev_close)/prev_close*100
            vol_recent = sum(_safe_float(x.get("volume")) or 0 for x in data[-5:])
            vol_prev = sum(_safe_float(x.get("volume")) or 0 for x in data[-10:-5]) or 1
            vol_ratio = vol_recent/vol_prev if vol_prev else 1
            label = "上向き" if (chg or 0) > 0.4 else ("下向き" if (chg or 0) < -0.4 else "横ばい")
            frames.append({"interval":interval,"label":label,"change_pct":round(chg or 0,2),"volume_ratio":round(vol_ratio,2),"source":r.get("source")})
    up = sum(1 for f in frames if f["label"]=="上向き")
    down = sum(1 for f in frames if f["label"]=="下向き")
    if up >= 3:
        final = "時間足一致：強い"
    elif down >= 3:
        final = "時間足一致：弱い"
    else:
        final = "時間足まちまち"
    return {"name":"無料マルチ時間足AI","final":final,"frames":frames,"score":round((up*25 + (len(frames)-down)*8),1)}

def _v126_market_indices_ai():
    """無料範囲: Yahooの指数データで地合い判定。"""
    symbols = {"日経225":"^N225","TOPIX":"1306.T","マザーズ系":"2516.T","SOX代替":"SOXX"}
    rows=[]
    for name, sym in symbols.items():
        try:
            url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
            j=_http_json(url, timeout=1.5)
            res=j["chart"]["result"][0]
            meta=res.get("meta",{})
            price=_safe_float(meta.get("regularMarketPrice"))
            closes=[_safe_float(c) for c in res.get("indicators",{}).get("quote",[{}])[0].get("close",[]) if c is not None]
            prev=closes[-2] if len(closes)>=2 else (closes[-1] if closes else None)
            chg=None if not price or not prev else (price-prev)/prev*100
            rows.append({"name":name,"symbol":sym,"change_pct":round(chg or 0,2),"label":"強い" if (chg or 0)>0.3 else ("弱い" if (chg or 0)<-0.3 else "中立")})
        except Exception:
            rows.append({"name":name,"symbol":sym,"change_pct":None,"label":"取得不可"})
    strong=sum(1 for r in rows if r["label"]=="強い")
    weak=sum(1 for r in rows if r["label"]=="弱い")
    final="攻め相場" if strong>=2 and weak==0 else ("防御相場" if weak>=2 else "中立相場")
    return {"ok":True,"name":"無料地合いAI","final":final,"indices":rows,"updated_at":datetime.now().strftime("%H:%M")}

def _v126_tdnet_free_links(code=None):
    """TDnetは公式APIが有料系なので、無料閲覧ページへの導線と検索キーワードを返す。"""
    code = normalize_code(code) if code else ""
    q = f"{code} 決算 上方修正 自社株買い 増配 希薄化" if code else "決算 上方修正 自社株買い 増配 希薄化"
    return {
        "ok": True,
        "name": "無料TDnet/開示導線",
        "note": "公式TDnet APIは有料/契約系。無料版では閲覧ページ・検索導線・キーワード判定まで。",
        "tdnet_url": "https://www.release.tdnet.info/inbs/I_main_00.html",
        "search_query": q,
        "risk_keywords": ["下方修正","赤字","減損","希薄化","第三者割当","継続企業","特別損失"],
        "good_keywords": ["上方修正","増配","自社株買い","株式分割","最高益","業績予想の修正"]
    }

def _v126_edinet_free_status(code=None):
    """EDINETは無料だがAPIキー登録が必要。キーがあれば将来接続可能。"""
    api_key = os.environ.get("EDINET_API_KEY","").strip()
    return {
        "ok": True,
        "name": "EDINET無料APIステータス",
        "api_key_set": bool(api_key),
        "note": "EDINET APIは無料だがAPIキー登録が必要。環境変数 EDINET_API_KEY を設定すると将来接続可能。",
        "target_code": normalize_code(code) if code else ""
    }

def get_free_data_core_user(uid, code):
    code = normalize_code(code)
    if not code:
        return {"ok":False,"error":"銘柄コードを入力"}
    base = get_entry_check_user(uid, code, force=True)
    item = base.get("item") or {}
    st = item.get("strategy") or {}
    intraday = _v126_intraday_ai(code)
    market = _v126_market_indices_ai()
    tdnet = _v126_tdnet_free_links(code)
    edinet = _v126_edinet_free_status(code)

    # 無料版で板が取れない代わりに疑似板/需給を強化
    vol = _safe_float(st.get("volume_ratio")) or 1
    chg = _safe_float(item.get("change_pct")) or 0
    if vol >= 2 and chg >= 0:
        pseudo_order = "買い吸収/大口気配あり"
    elif vol >= 1.3 and chg >= 0:
        pseudo_order = "買い優勢気味"
    elif vol >= 1.5 and chg < 0:
        pseudo_order = "売り出来高注意"
    else:
        pseudo_order = "板推定は弱い"

    warning=[]
    if market.get("final")=="防御相場": warning.append("地合いが防御。順張りロット注意")
    if intraday.get("final")=="時間足一致：弱い": warning.append("マルチ時間足が弱い")
    if pseudo_order=="売り出来高注意": warning.append("出来高増で下落。売り圧注意")

    return {
        "ok": True,
        "code": code,
        "name": name_for(code),
        "free_realtime_note": "無料版はYahoo Finance等の非公式/遅延データ中心。実板・秒足完全リアルタイムは有料APIが必要。",
        "intraday_ai": intraday,
        "market_ai": market,
        "tdnet": tdnet,
        "edinet": edinet,
        "pseudo_order_flow": {"label": pseudo_order, "volume_ratio": round(vol,2), "change_pct": round(chg,2)},
        "warnings": warning,
        "entry_check": base,
        "updated_at": datetime.now().strftime("%H:%M")
    }

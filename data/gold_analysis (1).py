#!/usr/bin/env python3
"""Análisis diario del oro con datos públicos de Binance (PAXGUSDT).

No necesita ninguna clave: las velas (klines) de Binance son datos públicos.
PAXG es un token respaldado por oro físico, así que sirve como proxy de XAUUSD
(puede diferir unos dólares del spot y cotiza también en fin de semana).

Escribe data/gold-analysis.json, que la página lee en la sección "Análisis diario".
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOL = "PAXGUSDT"
HOSTS = [
    "https://data-api.binance.vision",  # espejo público de datos de mercado
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api-gcp.binance.com",
]
OUT = Path(__file__).resolve().parent.parent / "data" / "gold-analysis.json"
BOGOTA = ZoneInfo("America/Bogota")


def fetch_klines(interval, limit):
    errors = []
    for host in HOSTS:
        url = f"{host}/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit={limit}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xauusd-volume-lab"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = json.load(r)
            return [
                {"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                 "c": float(k[4]), "v": float(k[5]), "ct": k[6]}
                for k in raw
            ]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{host}: {e}")
    raise RuntimeError("No se pudo leer Binance:\n" + "\n".join(errors))


def closed_only(candles):
    now_ms = int(time.time() * 1000)
    return [c for c in candles if c["ct"] < now_ms]


def ema(values, n):
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes, n=14):
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(candles, n=14):
    trs = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"])))
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def r2(x):
    return round(x, 2)


AI_MODEL = "claude-sonnet-5-5"


def ai_commentary(data):
    """Redacción opcional con Claude. Solo se ejecuta si existe ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    facts = {k: data[k] for k in ("price", "change_24h_pct", "bias", "score", "trend", "indicators", "levels", "signal")}
    prompt = (
        "Eres analista técnico de oro. Con SOLO estos datos reales (no inventes precios ni noticias), "
        "escribe en español, en 3 párrafos cortos: 1) lectura del contexto, 2) qué vigilar hoy, 3) riesgos. "
        "No des asesoría financiera; es contenido educativo.\n\n" + json.dumps(facts, ensure_ascii=False)
    )
    body = json.dumps({"model": AI_MODEL, "max_tokens": 700,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body, method="POST",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
        return "".join(b.get("text", "") for b in out.get("content", [])).strip() or None
    except Exception as e:  # noqa: BLE001
        print(f"Aviso: no se pudo generar el comentario con Claude: {e}", file=sys.stderr)
        return None


# ---------- Sesiones, calendario económico y plan del día ----------
SESSIONS = [  # nombre, zona horaria, apertura local, cierre local
    ("Asia (Tokio)", "Asia/Tokyo", 9, 18),
    ("Londres", "Europe/London", 8, 17),
    ("Nueva York", "America/New_York", 8, 17),
]
EVENTS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"  # feed gratuito de Forex Factory / Fair Economy


def hhmm(dt):
    """Hora de Bogotá en formato 12 h: 7:30 a. m."""
    d = dt.astimezone(BOGOTA)
    h12 = d.hour % 12 or 12
    return f"{h12}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"


def build_sessions(h1, now):
    out = []
    for name, tz, oh, ch in SESSIONS:
        z = ZoneInfo(tz)
        ln = now.astimezone(z)
        start = ln.replace(hour=oh, minute=0, second=0, microsecond=0)
        if start > ln:
            start -= timedelta(days=1)
        end = start.replace(hour=ch)
        nxt = start + timedelta(days=1)
        su, eu, nu = (x.astimezone(timezone.utc) for x in (start, end, nxt))
        if su <= now < eu:
            status, w0, w1 = "en curso", su, eu
        elif (nu - now) <= timedelta(hours=12):
            status, w0, w1 = "pendiente", nu, nu + (eu - su)
        else:
            status, w0, w1 = "cerrada", su, eu
        item = {"name": name, "status": status, "opens": hhmm(w0), "closes": hhmm(w1)}
        if status != "pendiente":
            cs = [c for c in h1 if w0.timestamp() * 1000 <= c["t"] < min(w1, now).timestamp() * 1000]
            if cs:
                item.update(high=r2(max(c["h"] for c in cs)), low=r2(min(c["l"] for c in cs)),
                            change_pct=round((cs[-1]["c"] / cs[0]["o"] - 1) * 100, 2))
                item["range"] = r2(item["high"] - item["low"])
        out.append(item)
    return out


def fetch_events():
    """Devuelve la lista de eventos o None si el feed falló (error, límite de uso o respuesta vacía)."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(EVENTS_URL, headers={"User-Agent": "Mozilla/5.0 xauusd-volume-lab"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = json.load(r)
            if isinstance(raw, list) and len(raw) > 0:
                return raw
            raise ValueError(f"respuesta inesperada del feed: {str(raw)[:120]}")
        except Exception as e:  # noqa: BLE001
            print(f"Aviso calendario (intento {attempt + 1}): {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def build_events(raw, now):
    """Eventos de USD de impacto medio/alto: hoy (hora de Bogotá) y próximos de impacto alto."""
    today, upcoming = [], []
    if raw is None:
        return None, None
    today_d = now.astimezone(BOGOTA).date()
    for e in raw:
        try:
            if e.get("country") not in ("USD", "All") or e.get("impact") not in ("High", "Medium"):
                continue
            dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(BOGOTA)
        except Exception:  # noqa: BLE001
            continue
        item = {"time": hhmm(dt), "title": e.get("title", ""), "impact": e["impact"],
                "forecast": e.get("forecast") or "", "previous": e.get("previous") or "", "_dt": dt, "past": dt < now}
        if dt.date() == today_d:
            today.append(item)
        elif today_d < dt.date() <= today_d + timedelta(days=3) and e["impact"] == "High":
            item["day"] = dt.strftime("%d/%m")
            upcoming.append(item)
    for lst in (today, upcoming):
        lst.sort(key=lambda x: x["_dt"])
        for x in lst:
            x.pop("_dt")
    return today, upcoming[:6]


def build_plan(price, bias, levels, sessions, events_today, signal):
    plan = []
    if bias == "alcista":
        plan.append("Sesgo alcista: prioriza compras en retrocesos hacia el pivote o la EMA20; evita perseguir el precio.")
    elif bias == "bajista":
        plan.append("Sesgo bajista: prioriza ventas en rebotes hacia el pivote o la EMA20; evita perseguir el precio.")
    else:
        plan.append("Sin sesgo claro: espera una ruptura confirmada de los niveles antes de actuar.")
    by = {x["name"]: x for x in sessions}
    asia, lon = by.get("Asia (Tokio)"), by.get("Londres")
    if asia and "high" in asia:
        pos = "por encima" if price > asia["high"] else ("por debajo" if price < asia["low"] else "dentro")
        plan.append(f"Asia: rango {asia['low']}–{asia['high']} ({asia['range']} USD, {asia['change_pct']:+.2f}%). El precio está {pos} de ese rango.")
        if lon and "high" in lon and lon["status"] == "en curso":
            up, dn = lon["high"] > asia["high"], lon["low"] < asia["low"]
            if up and dn:
                plan.append("Londres barrió ambos extremos del rango asiático: volatilidad alta, cuidado con falsas rupturas.")
            elif up:
                plan.append("Londres rompió al alza el máximo asiático.")
            elif dn:
                plan.append("Londres rompió a la baja el mínimo asiático.")
            else:
                plan.append("Londres sigue dentro del rango asiático: aún no hay dirección definida.")
    ny = by.get("Nueva York")
    if ny and ny["status"] == "pendiente":
        plan.append(f"Nueva York abre a las {ny['opens']} (Bogotá): suele traer el movimiento más fuerte del día.")
    if events_today is None:
        plan.append("No se pudo leer el calendario económico hoy; revísalo antes de operar.")
    else:
        highs = [e for e in events_today if e["impact"] == "High"]
        soon = [e for e in highs if not e.get("past")]
        done = [e for e in highs if e.get("past")]
        if soon:
            e = soon[0]
            plan.append(f"Noticia de impacto alto: {e['title']} ({e['time']}, hora de Bogotá). Evita abrir 15 min antes y espera 15 min después.")
        elif done:
            plan.append("Ya salió hoy: " + ", ".join(f"{e['title']} ({e['time']})" for e in done) + ". Mira cómo reaccionó el precio antes de operar.")
        else:
            plan.append("Sin eventos de USD de impacto alto hoy.")
    lv = {"Pivote": levels["pivot"], "R1": levels["r1"], "R2": levels["r2"], "S1": levels["s1"], "S2": levels["s2"],
          "máx. 20 d": levels["high20"], "mín. 20 d": levels["low20"], "máx. de ayer": levels["prev_high"], "mín. de ayer": levels["prev_low"]}
    above = sorted((v, k) for k, v in lv.items() if v > price)[:1]
    below = sorted(((v, k) for k, v in lv.items() if v < price), reverse=True)[:1]
    if above and below:
        plan.append(f"Vigila {above[0][1]} en {above[0][0]} arriba y {below[0][1]} en {below[0][0]} abajo.")
    return plan


def main():
    daily = closed_only(fetch_klines("1d", 300))
    h4 = closed_only(fetch_klines("4h", 300))
    h1 = fetch_klines("1h", 72)

    price = h1[-1]["c"]
    change_24h = (price / h1[-25]["c"] - 1) * 100

    dc = [c["c"] for c in daily]
    hc = [c["c"] for c in h4]
    e20, e50, e200 = ema(dc, 20), ema(dc, 50), ema(dc, 200)
    h20, h50 = ema(hc, 20), ema(hc, 50)
    rsi_d, rsi_h = rsi(dc), rsi(hc)
    atr_d, atr_h = atr(daily), atr(h4)

    prev = daily[-1]
    P = (prev["h"] + prev["l"] + prev["c"]) / 3
    R1, S1 = 2 * P - prev["l"], 2 * P - prev["h"]
    R2, S2 = P + (prev["h"] - prev["l"]), P - (prev["h"] - prev["l"])
    hi20 = max(c["h"] for c in daily[-20:])
    lo20 = min(c["l"] for c in daily[-20:])
    vol_avg = sum(c["v"] for c in daily[-21:-1]) / 20
    vol_ratio = prev["v"] / vol_avg if vol_avg else 0

    # Puntuación de tendencia (-6 a +6)
    score = 0
    score += 1 if dc[-1] > e20 else -1
    score += 1 if e20 > e50 else -1
    score += 1 if e50 > e200 else -1
    score += 1 if rsi_d > 55 else (-1 if rsi_d < 45 else 0)
    score += 1 if hc[-1] > h20 else -1
    score += 1 if h20 > h50 else -1
    bias = "alcista" if score >= 3 else ("bajista" if score <= -3 else "neutral")

    trend_d = "alcista" if e20 > e50 > e200 else ("bajista" if e20 < e50 < e200 else "mixta")
    trend_h = "alcista" if h20 > h50 else "bajista"

    # Señal de ejemplo basada en ATR de 4h (educativa, no es una recomendación)
    signal = {"side": "ninguna"}
    if bias != "neutral":
        d = 1 if bias == "alcista" else -1
        risk = atr_h
        signal = {
            "side": "compra" if d == 1 else "venta",
            "entry": r2(price),
            "sl": r2(price - d * risk),
            "tp1": r2(price + d * 1.5 * risk),
            "tp2": r2(price + d * 2.5 * risk),
            "rr1": 1.5,
            "basis": "Riesgo = 1 ATR(14) en 4h",
        }

    summary = [
        f"Sesgo {bias} (puntuación {score:+d} de ±6). Diario: tendencia {trend_d}; 4h: {trend_h}.",
        f"Precio {r2(price)} frente a EMA20 {r2(e20)}, EMA50 {r2(e50)} y EMA200 {r2(e200)} en diario.",
        f"RSI(14): {rsi_d:.0f} en diario y {rsi_h:.0f} en 4h. ATR diario ≈ {r2(atr_d)} USD.",
        f"Volumen de ayer: {vol_ratio:.2f}× el promedio de 20 días.",
        f"Pivote {r2(P)}; resistencias {r2(R1)} / {r2(R2)}; soportes {r2(S1)} / {r2(S2)}.",
    ]
    scenarios = [
        {"name": "Escenario alcista", "text": f"Cierre de 4h sobre {r2(R1)} abre camino a {r2(R2)}. Se invalida con cierre bajo {r2(P)}."},
        {"name": "Escenario bajista", "text": f"Cierre de 4h bajo {r2(S1)} abre camino a {r2(S2)}. Se invalida con cierre sobre {r2(P)}."},
    ]

    now_dt = datetime.now(timezone.utc)
    sessions = build_sessions(h1, now_dt)
    events_today, events_upcoming = build_events(fetch_events(), now_dt)
    levels_d = {"pivot": r2(P), "r1": r2(R1), "r2": r2(R2), "s1": r2(S1), "s2": r2(S2),
                "high20": r2(hi20), "low20": r2(lo20), "prev_high": r2(prev["h"]), "prev_low": r2(prev["l"])}
    plan = build_plan(price, bias, levels_d, sessions, events_today, signal)

    chart = {
        "interval": "4h",
        "candles": [[c["t"], r2(c["o"]), r2(c["h"]), r2(c["l"]), r2(c["c"])] for c in h4[-60:]],
    }

    now = datetime.now(timezone.utc)
    data = {
        "ready": True,
        "generated_at_utc": now.isoformat(timespec="seconds"),
        "generated_at_bogota": now.astimezone(BOGOTA).isoformat(timespec="seconds"),
        "source": f"Binance {SYMBOL} (proxy del oro; puede diferir del spot XAUUSD)",
        "price": r2(price),
        "change_24h_pct": round(change_24h, 2),
        "bias": bias,
        "score": score,
        "trend": {"daily": trend_d, "h4": trend_h},
        "indicators": {
            "ema20": r2(e20), "ema50": r2(e50), "ema200": r2(e200),
            "rsi_daily": round(rsi_d, 1), "rsi_4h": round(rsi_h, 1),
            "atr_daily": r2(atr_d), "atr_4h": r2(atr_h), "volume_ratio": round(vol_ratio, 2),
        },
        "levels": {
            "pivot": r2(P), "r1": r2(R1), "r2": r2(R2), "s1": r2(S1), "s2": r2(S2),
            "high20": r2(hi20), "low20": r2(lo20),
            "prev_high": r2(prev["h"]), "prev_low": r2(prev["l"]), "prev_close": r2(prev["c"]),
        },
        "signal": signal,
        "chart": chart,
        "plan": plan,
        "sessions": sessions,
        "events_ok": events_today is not None,
        "events_today": events_today or [],
        "events_upcoming": events_upcoming or [],
        "events_source": "Forex Factory (feed gratuito de Fair Economy) · USD, impacto medio y alto · hora de Bogotá",
        "summary": summary,
        "scenarios": scenarios,
        "notes": [
            "Las cifras se calculan con reglas técnicas sobre datos reales; el calendario viene de Forex Factory y no incluye el dato publicado, solo pronóstico y valor previo.",
            "Los días de Binance (diario) abren a las 00:00 UTC (7:00 p. m. en Bogotá).",
            "Contenido educativo; no es asesoría financiera. Los resultados pasados no garantizan resultados futuros.",
        ],
    }
    ai = ai_commentary(data)
    if ai:
        data["ai_commentary"] = ai
        data["ai_model"] = AI_MODEL

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {OUT} · {SYMBOL} {data['price']} · sesgo {bias}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

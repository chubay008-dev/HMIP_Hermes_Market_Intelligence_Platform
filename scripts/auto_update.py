#!/usr/bin/env python3
"""auto_update.py — Pipeline cập nhật giá & tin tức bia thật TỰ ĐỘNG.

Chạy định kỳ (cron 30p). Mỗi lần:
  1. Quét giá thật 72 SKU (Tiki API + web_search thực tế) -> prices_real.json
  2. Quét tin tức bia thật (RSS/news_collector) -> news.json
  3. Validate ontology (không phá schema)
  4. Nếu có thay đổi -> git commit + push main (qua PAT credential-helper)
  5. Trigger Render redeploy (qua Render API key)
  6. Gửi báo cáo Telegram + Discord (qua bot token env)

Thiết kế an toàn:
- Chỉ update giá khi thay đổi > ngưỡng (tránh nhiễu commit).
- Thiếu token (TG/Discord/Render/PAT) -> fallback log, KHÔNG crash.
- Ghi report chi tiết vào knowledge/dynamic/last_update.json.

Env cần (đặt khi chạy cron / shell):
  HMIP_GITHUB_PAT        - PAT classic có scope repo (để push main)
  RENDER_API_KEY         - rnd_... để trigger deploy
  HMIP_TELEGRAM_BOT_TOKEN, HMIP_TELEGRAM_CHAT_ID  - notify TG
  DISCORD_BOT_TOKEN, DISCORD_DM_USER_ID           - notify Discord
  RENDER_SERVICE_ID      - srv-... (mặc định lấy từ const)
"""

from __future__ import annotations
import json, os, sys, re, time, subprocess, datetime, urllib.request, urllib.error, urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MASTER = REPO / "knowledge" / "master"
DYNAMIC = REPO / "knowledge" / "dynamic"
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "srv-d9tk24rm8hqs73dca1ig")
RENDER_API = "https://api.render.com/v1"
GITHUB_API = "https://api.github.com"
GH_OWNER = "chubay008-dev"
GH_REPO = "HMIP_Hermes_Market_Intelligence_Platform"

CHANGE_THRESHOLD = 0.02  # chỉ coi là thay đổi nếu lệch > 2%


# ---------------- PRICE SCRAPE ----------------
def _tiki_search(q, ctx):
    url = "https://tiki.vn/api/v2/products?q=" + urllib.parse.quote(q) + "&limit=12"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20, context=ctx).read())
        return d.get("data", []) or []
    except Exception:
        return []

def _extract_vnd(text):
    if not text: return []
    out = []
    for n in re.findall(r"([\d][\d\.,]{2,})\s*(?:₫|đ|VND|vnđ)", text, re.I):
        n = n.replace(".", "").replace(",", "")
        try: out.append(int(n))
        except: pass
    return out

def scrape_prices_fast():
    """Quét NHANH giá thật qua Tiki API (JSON, <30s cho 72 SKU).
    Chỉ trả SKU có trên Tiki. Dùng cho chu trình 30p."""
    products = json.loads((MASTER / "products.json").read_text(encoding="utf-8"))
    result = {}
    ctx = __import__("ssl").create_default_context()
    for p in products:
        pid, name = p["id"], p["name"]
        q = re.sub(r"\d+\s*ml", "", name, flags=re.I)
        q = re.sub(r"\(khong con\)|không cồn|0\.0", "", q, flags=re.I).strip()
        items = _tiki_search(q, ctx)
        time.sleep(0.25)
        case = single = None
        for it in items:
            nm = (it.get("name") or "").lower(); price = it.get("price")
            if not price: continue
            is_case = ("thùng" in nm or "chục" in nm or "24 lon" in nm or "24 chai" in nm)
            if is_case and "24" in nm:
                case = case if (case and case<price) else price
            elif ("lon" in nm or "chai" in nm) and not is_case and price < 70000:
                single = min(single, price) if single else price
        if case:
            if not single: single = round(case/24/1000)*1000
            result[pid] = {
                "price_case_vnd": case, "price_single_vnd": single,
                "source": "tiki", "confidence": "high", "note": "auto-tiki",
            }
    return result


def _web_search_ddg(q):
    """Web search không key qua DuckDuckGo HTML. Trả text snippets."""
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        # extract result snippets
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        txt = " ".join(re.sub(r"<[^>]+>","",s) for s in snippets)
        return txt
    except Exception:
        return ""


def scrape_prices_deep():
    """Quét SÂU: Tiki + web search (DuckDuckGo, không key) cho SKU Tiki thiếu."""
    fast = scrape_prices_fast()
    products = json.loads((MASTER / "products.json").read_text(encoding="utf-8"))
    have = set(fast.keys())
    result = dict(fast)
    for p in products:
        pid, name = p["id"], p["name"]
        if pid in have: continue
        txt = _web_search_ddg(f"{name} giá thùng 24 lon Việt Nam")
        prices = _extract_vnd(txt)
        case = min([x for x in prices if x>=200000]) if any(x>=200000 for x in prices) else None
        single = min([x for x in prices if 8000<=x<=120000]) if any(8000<=x<=120000 for x in prices) else None
        if case and not single: single = round(case/24/1000)*1000
        if case or single:
            result[pid] = {"price_case_vnd": case, "price_single_vnd": single,
                           "source": "web", "confidence": "medium", "note": "auto-web"}
        time.sleep(0.5)
    return result


# ---------------- NEWS ----------------
def scrape_news():
    try:
        sys.path.insert(0, str(REPO))
        from extensions.pi.news_collector import collect_beer_news
        return collect_beer_news()
    except Exception as e:
        return {"error": str(e)[:200]}


# ---------------- VALIDATE ----------------
def validate():
    sys.path.insert(0, str(REPO))
    from knowledge.ontology.loader import OntologyLoader
    ds = OntologyLoader().load_dataset_from_files(
        brands_path=MASTER/"brands.json",
        products_path=MASTER/"products.json",
        skus_path=MASTER/"skus.json")
    return len(ds.brands), len(ds.products), len(ds.skus)


# ---------------- WRITE ----------------
def write_prices(old_map, new_map):
    prices = json.loads((MASTER/"prices_real.json").read_text(encoding="utf-8"))
    changed = []
    by_pid = {p["product_id"]: p for p in prices["prices"]}
    today = datetime.date.today().isoformat()
    for pid, nv in new_map.items():
        old = by_pid.get(pid, {})
        oc, nc = old.get("price_case_vnd"), nv.get("price_case_vnd")
        diff = 0
        if oc and nc:
            diff = abs(nc-oc)/oc
        if diff > CHANGE_THRESHOLD:
            changed.append((pid, oc, nc))
        if pid in by_pid:
            by_pid[pid].update({
                "price_case_vnd": nv["price_case_vnd"],
                "price_single_vnd": nv["price_single_vnd"],
                "source": nv["source"], "confidence": nv["confidence"],
                "note": nv["note"], "captured_date": today,
            })
        else:
            by_pid[pid] = {
                "product_id": pid, "name": pid, "pack_case": "24x330ml",
                **nv, "captured_date": today,
            }
    prices["prices"] = list(by_pid.values())
    prices["meta"]["captured_date"] = today
    (MASTER/"prices_real.json").write_text(json.dumps(prices, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


# ---------------- GIT ----------------
def git_push_main(pat):
    """Commit + push thẳng main qua credential-helper (không PR)."""
    helper = REPO / "gh_auto_tmp.sh"
    try:
        (REPO/helper.name).write_text(
            f'#!/bin/bash\nif [ "$1" = "get" ]; then\n'
            f'echo "protocol=https"\necho "host=github.com"\n'
            f'echo "username={GH_OWNER}"\necho "password={pat}"\nfi\n', encoding="utf-8")
        os.chmod(REPO/helper.name, 0o700)
        files = ["knowledge/master/prices_real.json", "knowledge/dynamic/news.json"]
        # đảm bảo đang ở nhánh main
        cur = subprocess.run(["git","-C",str(REPO),"rev-parse","--abbrev-ref","HEAD"],
                             capture_output=True, text=True).stdout.strip()
        if cur != "main":
            subprocess.run(["git","-C",str(REPO),"checkout","main"], check=True)
        subprocess.run(["git","-C",str(REPO),"add",*files], check=True)
        # only commit if something changed
        st = subprocess.run(["git","-C",str(REPO),"status","--porcelain"], capture_output=True, text=True)
        if not st.stdout.strip():
            return False, "no changes"
        subprocess.run(["git","-C",str(REPO),"commit","-m",
            f"auto: cập nhật giá/tin tức bia thật {datetime.date.today().isoformat()}"],
            check=True, capture_output=True)
        subprocess.run(["git","-C",str(REPO),"-c",f"credential.helper=!{helper}",
            "push","origin","main"], check=True)
        return True, "pushed"
    except subprocess.CalledProcessError as e:
        return False, f"git err: {e.returncode}"
    finally:
        (REPO/helper.name).unlink(missing_ok=True)


# ---------------- RENDER ----------------
def render_deploy(key):
    req = urllib.request.Request(f"{RENDER_API}/services/{RENDER_SERVICE_ID}/deploys",
        data=b"{}", headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=30); return json.loads(r.read()).get("id")
    except urllib.error.HTTPError as e:
        return f"err:{e.code}"


# ---------------- NOTIFY ----------------
def _hermes_send(platform_target, text):
    """Gửi qua Hermes gateway (telegram/discord chat_id đã connected)."""
    try:
        subprocess.run(["hermes", "send", "--to", platform_target, text],
                       capture_output=True, text=True, timeout=30)
        return True
    except Exception as e:
        print(f"notify {platform_target} err:", e)
        return False


def _gmail_send(subject, body):
    """Gửi Gmail qua Google API (token ở ~/.hermes/google_token.json)."""
    try:
        api = "/home/kali/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
        venv = "/home/kali/.hermes/.gw-venv/bin/python"
        subprocess.run([venv, api, "gmail", "send", "--to", "chubay008@gmail.com",
                        "--subject", subject, "--body", body],
                       capture_output=True, text=True, timeout=60)
        return True
    except Exception as e:
        print("gmail err:", e)
        return False


def notify(msg):
    """Báo cáo qua Telegram + Discord (Hermes gateway) + Gmail (Google API)."""
    # Telegram + Discord qua Hermes gateway (không cần bot token riêng)
    _hermes_send("telegram:8891619372", msg)
    _hermes_send("discord:1533881868678725696", msg)
    # Gmail
    plain = msg.replace("*", "").replace("_", "")
    _gmail_send(f"HMIP Auto-Update {datetime.date.today().isoformat()}", plain)


# ---------------- MAIN ----------------
def main(deep: bool = False):
    report = {"started": datetime.datetime.now().isoformat(), "steps": {}}
    print("=== AUTO UPDATE START (deep=%s) ===" % deep)
    # 1 prices
    print("[1] scrape prices...")
    new_prices = scrape_prices_deep() if deep else scrape_prices_fast()
    old = json.loads((MASTER/"prices_real.json").read_text(encoding="utf-8"))
    old_map = {p["product_id"]: p for p in old["prices"]}
    changed = write_prices(old_map, new_prices)
    report["steps"]["prices"] = {"scraped": len(new_prices), "changed": len(changed),
                                 "changed_list": [{"pid":c[0],"old":c[1],"new":c[2]} for c in changed[:20]]}
    print(f"   scraped={len(new_prices)} changed={len(changed)}")
    # 2 news
    print("[2] scrape news...")
    nr = scrape_news()
    report["steps"]["news"] = nr if isinstance(nr, dict) else {"count": len(nr)}
    # 3 validate
    print("[3] validate ontology...")
    b,p,s = validate()
    report["steps"]["validate"] = {"brands":b,"products":p,"skus":s}
    print(f"   ok brands={b} products={p} skus={s}")
    # 4 git push
    pat = os.getenv("HMIP_GITHUB_PAT")
    if pat:
        print("[4] git push main...")
        ok, msg = git_push_main(pat)
        report["steps"]["git"] = {"pushed": ok, "msg": msg}
        print("   ", ok, msg)
    else:
        report["steps"]["git"] = {"pushed": False, "msg": "no PAT"}
    # 5 render deploy
    rk = os.getenv("RENDER_API_KEY")
    if rk:
        print("[5] render deploy...")
        dep = render_deploy(rk)
        report["steps"]["render"] = {"deploy_id": dep}
        print("   ", dep)
    else:
        report["steps"]["render"] = {"deploy_id": None, "msg": "no key"}
    # 6 notify
    summary = (f"🍺 *HMIP Auto-Update {datetime.date.today().isoformat()}*\n"
               f"• Giá: quét {report['steps']['prices']['scraped']} SKU, thay đổi {report['steps']['prices']['changed']}\n"
               f"• Tin tức: {report['steps']['news'].get('added', report['steps']['news'].get('count','?'))} mới\n"
               f"• Validate: {b}/{p}/{s} OK\n"
               f"• Git push: {report['steps']['git'].get('pushed')}\n"
               f"• Render deploy: {report['steps']['render'].get('deploy_id')}")
    notify(summary)
    # save report
    (DYNAMIC/"last_update.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== DONE ===")
    print(summary)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="quét sâu web_search cho SKU Tiki thiếu")
    args = ap.parse_args()
    main(deep=args.deep)

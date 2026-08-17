"""notifier.py — Đẩy alert giá sang kênh ngoài (Discord + Telegram).

Thiết kế:
- Đọc credential từ env (Render Dashboard / .env). Thiếu -> skip gracefully.
- Discord: bot token + channel ID (post qua discord.com/api/v10).
  Hỗ trợ DM trực tiếp tới user qua DISCORD_DM_USER_ID (tự tạo DM channel).
- Telegram: bot token (TELEGRAM_HMIP_MARKET_BOT) + chat_id.
- Chỉ gửi CRITICAL alert (tránh spam). Gọi từ events.detect_and_alert.
- Không sửa core/domains.
"""

from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger("hmip.notifier")

_DISCORD_API = "https://discord.com/api/v10"
_DISCORD_MSG = _DISCORD_API + "/channels/{channel_id}/messages"
_DISCORD_DM = _DISCORD_API + "/users/@me/channels"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# --- Rate limiting (chống spam) -------------------------------------------
# Cooldown per (sku|channel|region): sau khi notify 1 alert cho 1 cặp
# sku/kênh/vùng, bỏ qua mọi alert khác cho chính cặp đó trong cooldown
# này. Mặc định 6h (360') — đủ để bắt giá đổi thật sự, không phải noise
# dao động qua lại trong ngày. Override qua env.
#
# State BỀN VỮNG (PR #9): ngoài cache in-memory (_notify_state), mốc
# lần gửi cuối còn ghi vào bảng pi_notify_state (PI DB). Render free tier
# ngủ/restart → cache in-memory mất → đọc lại từ DB → cooldown vẫn sống
# (tránh re-notify toàn bộ alert mỗi lần restart). Cache in-memory chỉ
# dùng để tránh round-trip DB cho mỗi alert trong cùng process dài.
_notify_state: dict[str, float] = {}
# Per-sku cooldown state: key = sku_id|region_id (KHÔNG channel). Khi bật
# multi-channel (Tiki+Shopee+Lazada), nếu 1 SP đổi giá trên cả 3 kênh cùng
# lúc, chỉ kênh đầu notify; 2 kênh còn lại skip trong cửa sổ per-sku ngắn
# (HMIP_NOTIFY_SKU_COOLDOWN_MIN, mặc định 30') → chống spam gấp 3.
_sku_notify_state: dict[str, float] = {}
# path PI DB để ghi state bền vững. Khởi tạo lazy khi cần (tránh import
# cycle + cho phép test override path qua _set_state_db_path).
_state_db_path: str | None = None


def _set_state_db_path(path: str | None) -> None:
    """Override PI DB path cho state notify (test)."""
    global _state_db_path
    _state_db_path = path


def _state_path() -> str | None:
    return _state_db_path or os.getenv("HMIP_PI_DB_PATH") or None


def _cooldown_seconds() -> float:
    """Số giây giữa 2 lần notify cho cùng (sku,channel,region)."""
    try:
        return float(int(os.getenv("HMIP_NOTIFY_COOLDOWN_MIN", "360"))) * 60.0
    except (TypeError, ValueError):
        return 360.0 * 60.0


def _min_change_pct() -> float:
    """% thay đổi tối thiểu để notify (mặc định 5 — bỏ noise 1-5%)."""
    try:
        return float(os.getenv("HMIP_NOTIFY_MIN_PCT", "5"))
    except (TypeError, ValueError):
        return 5.0


def _notify_key(alert: dict) -> str:
    return "|".join(
        str(alert.get(k, ""))
        for k in ("sku_id", "channel_id", "region_id")
    )


def _sku_notify_key(alert: dict) -> str:
    """Key per-sku (bỏ channel): 'sku:' + sku_id|region_id. Cho anti-spam multi-channel.

    Prefix 'sku:' để phân biệt với per-channel key (sku|channel|region) trong
    bảng pi_notify_state chung (state_key là PK).
    """
    base = "|".join(str(alert.get(k, "")) for k in ("sku_id", "region_id"))
    return f"sku:{base}"


def _product_notify_key(alert: dict) -> str | None:
    """Key cross-hệ (cross-scope): 'prod:' + product_name.

    Dùng chung giữa hệ 1 (PI collect, notify_alert) và hệ 2 (scheduler scan,
    rate_limit). Khi 1 SP giá đổi, dù hệ nào gửi trước → ghi key này → hệ kia
    check thấy trong cửa sổ per-sku → skip → tránh DOUBLE NOTIFY (2 messages
    Telegram+Discord cho cùng 1 SP từ 2 hệ chạy song song).
    """
    pname = alert.get("product_name")
    if not pname:
        return None
    return f"prod:{pname}"


def _sku_cooldown_seconds() -> float:
    """Số giây giữa 2 lần notify cho cùng SP (bất kể kênh).

    Ngắn hơn cooldown per-channel (mặc định 30' vs 6h) để 1 SP đổi giá trên
    nhiều kênh (Tiki+Shopee+Lazada) cùng lúc chỉ notify 1 lần (kênh đầu).
    Set 0 để tắt layer per-sku (chỉ dùng per-channel).
    """
    try:
        return float(int(os.getenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "30"))) * 60.0
    except (TypeError, ValueError):
        return 30.0 * 60.0


def _load_sku_last_sent(key: str) -> float | None:
    """Đọc mốc notify cuối cho SP (per-sku, scope='pi-sku'). Cache first, then DB."""
    last = _sku_notify_state.get(key)
    if last is not None:
        return last
    try:
        from . import pi_store
        rec = pi_store.get_notify_state(key, path=_state_path())
        if rec and rec.get("last_sent_at"):
            import datetime as _dt
            try:
                ts = _dt.datetime.fromisoformat(rec["last_sent_at"]).timestamp()
                _sku_notify_state[key] = ts
                return ts
            except (ValueError, TypeError):
                return None
    except Exception:
        pass
    return None


def _load_sku_last_price(key: str) -> float | None:
    """Đọc last_price cho state_key cross-hệ/per-sku (scope='pi-sku')."""
    try:
        from . import pi_store
        rec = pi_store.get_notify_state(key, path=_state_path())
        if rec and rec.get("last_price") is not None:
            try:
                return float(rec["last_price"])
            except (TypeError, ValueError):
                return None
    except Exception:
        pass
    return None


def _cross_price_changed_significantly(old: float | None, new) -> bool:
    """Giá đổi ≥5% so với mốc cross-hệ → event mới (cho phép notify lại)."""
    if old is None or new is None:
        return False
    try:
        cur, last = float(new), float(old)
    except (TypeError, ValueError):
        return False
    if last <= 0:
        return True
    return abs(cur - last) / last * 100.0 >= 5.0


def _load_last_sent(key: str) -> float | None:
    """Đọc mốc lần gửi cuối cho key: cache in-memory first, rồi DB.

    Khi process restart (cache rỗng), đọc lại từ DB để cooldown sống qua
    restart (Render free tier ngủ 15' rồi spin-up lại).
    """
    last = _notify_state.get(key)
    if last is not None:
        return last
    # Cache miss → đọc DB (bền vững qua restart).
    try:
        from . import pi_store
        rec = pi_store.get_notify_state(key, path=_state_path())
        if rec and rec.get("last_sent_at"):
            import datetime as _dt
            try:
                ts = _dt.datetime.fromisoformat(rec["last_sent_at"]).timestamp()
                _notify_state[key] = ts  # populate cache
                return ts
            except (ValueError, TypeError):
                return None
    except Exception:
        pass
    return None


def _is_suppressed_by_cooldown(alert: dict) -> bool:
    """True nếu alert nên bỏ qua để chống spam.

    3 layer check (lớp đầu True → skip ngay, không check lớp sau):
    0. Cross-hệ (HMIP_NOTIFY_SKU_COOLDOWN_MIN): hệ nào gửi trước (PI collect
       HOẶC scheduler scan) → ghi mốc → hệ kia thấy trong cửa sổ → skip. Chống
       DOUBLE NOTIFY (cùng 1 SP, 2 hệ chạy song song gửi 2 messages).
    1. Per-sku (HMIP_NOTIFY_SKU_COOLDOWN_MIN, mặc định 30'): 1 SP đổi giá trên
       nhiều kênh (Tiki+Shopee+Lazada) cùng lúc → chỉ kênh đầu notify. Bỏ qua
       nếu SP đã notify gần đây BẤT KỂ kênh nào.
    2. Per-channel (HMIP_NOTIFY_COOLDOWN_MIN, mặc định 6h): cùng (sku,channel,
       region) đã notify gần đây → skip.
    """
    sku_window = _sku_cooldown_seconds()
    # Layer 0: cross-hệ (PI collect ↔ scheduler scan). Dùng chung cửa sổ per-sku.
    # Ngoại lệ: giá đổi đáng kể (≥5%) → event mới → cho phép (không skip).
    if sku_window > 0:
        prod_key = _product_notify_key(alert)
        if prod_key:
            prod_last = _load_sku_last_sent(prod_key)
            if prod_last is not None and (time.time() - prod_last) < sku_window:
                # Trong cửa sổ — check giá đổi đáng kể so với mốc cross.
                prod_price = _load_sku_last_price(prod_key)
                new_p = alert.get("new_price")
                if not _cross_price_changed_significantly(prod_price, new_p):
                    log.info("Notify skip (cross-hệ cooldown %.0fs): %s",
                             sku_window, prod_key)
                    return True
    # Layer 1: per-sku (chống spam multi-channel).
    if sku_window > 0:
        sku_key = _sku_notify_key(alert)
        if sku_key.strip("sku:").strip("|"):
            sku_last = _load_sku_last_sent(sku_key)
            if sku_last is not None and (time.time() - sku_last) < sku_window:
                log.info("Notify skip (per-sku cooldown %.0fs): %s",
                         sku_window, sku_key)
                return True
    # Layer 2: per-(sku,channel,region).
    key = _notify_key(alert)
    if not key.strip("|"):
        return False
    last = _load_last_sent(key)
    if last is None:
        return False
    if (time.time() - last) < _cooldown_seconds():
        log.info("Notify skip (per-channel cooldown): %s", key)
        return True
    return False


def _record_notify_sent(alert: dict) -> None:
    """Ghi mốc notify cho cả 3 layer: cross-hệ + per-(sku,channel,region) + per-sku."""
    key = _notify_key(alert)
    if not key.strip("|"):
        return
    now = time.time()
    _notify_state[key] = now
    # Ghi DB (bền vững qua restart). best-effort — không block notify.
    try:
        from . import pi_store
        price = alert.get("new_price")
        try:
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_f = None
        pi_store.set_notify_state(
            key, pi_store.NOTIFY_SCOPE_PI,
            last_price=price_f,
            last_decision=alert.get("event_type"),
            path=_state_path(),
        )
    except Exception as exc:
        log.debug("Notify state persist fail (non-fatal): %s", exc)
        price_f = None

    # Per-sku state (cho anti-spam multi-channel) + cross-hệ (cho đồng bộ với
    # scheduler scan). Cùng cửa sổ HMIP_NOTIFY_SKU_COOLDOWN_MIN.
    # prod:<name> ghi last_price để cross-scope check giá đổi đáng kể (≥5%).
    sku_window = _sku_cooldown_seconds()
    if sku_window > 0:
        for skey in (_sku_notify_key(alert), _product_notify_key(alert)):
            if not skey or (skey.startswith("sku:") and not skey.strip("sku:").strip("|")):
                continue
            _sku_notify_state[skey] = now
            is_prod = skey.startswith("prod:")
            try:
                from . import pi_store
                pi_store.set_notify_state(
                    skey, "pi-sku",
                    last_price=price_f if is_prod else None,
                    last_decision=alert.get("event_type"),
                    path=_state_path(),
                )
            except Exception as exc:
                log.debug("Per-sku state persist fail (non-fatal): %s", exc)


def _alert_change_pct(alert: dict) -> float | None:
    pct = alert.get("change_pct", alert.get("price_change_pct"))
    try:
        return abs(float(pct)) if pct is not None else None
    except (TypeError, ValueError):
        return None


def reset_notify_state() -> None:
    """Xoá state cooldown (cho test / chạy lại sạch).

    Xoá cache in-memory luôn. Chỉ xoá bảng DB khi đã set state path
    (tránh tạo file hmip_pi.db rác trong cwd khi test chưa cấu hình path).
    """
    _notify_state.clear()
    _sku_notify_state.clear()
    p = _state_path()
    if not p:
        return
    try:
        from . import pi_store
        pi_store.clear_notify_state(path=p)
    except Exception:
        pass

# Load .hermes/.env nếu env thiếu (chỉ cho local dev; Render set sẵn env).
def _maybe_load_env():
    """Luôn thử nạp .hermes/.env để bổ sung các key thiếu (Discord/Telegram chat)."""
    for cand in ("/home/kali/.hermes/.env", os.path.expanduser("~/.hermes/.env")):
        if not os.path.exists(cand):
            continue
        try:
            with open(cand, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass
        # Chỉ cần load 1 file tồn tại là đủ
        return


def _discord_configured() -> bool:
    """Discord sẵn sàng khi có bot token VÀ (channel ID HOẶC DM user ID)."""
    has_token = bool(os.getenv("DISCORD_BOT_TOKEN"))
    has_target = bool(os.getenv("DISCORD_HOME_CHANNEL") or os.getenv("DISCORD_DM_USER_ID"))
    return has_token and has_target


# Cache DM channel id để tránh tạo lại mỗi lần gửi (Discord trả cùng id cho 1 cặp).
_dm_channel_cache: str | None = None


def _resolve_discord_channel() -> str | None:
    """Trả channel_id để post. Ưu tiên DISCORD_HOME_CHANNEL; nếu không có,
    tạo DM channel với DISCORD_DM_USER_ID (bot phải share server với user)."""
    global _dm_channel_cache
    direct = os.getenv("DISCORD_HOME_CHANNEL")
    if direct:
        return direct
    if _dm_channel_cache:
        return _dm_channel_cache
    user_id = os.getenv("DISCORD_DM_USER_ID")
    if not user_id:
        return None
    token = os.getenv("DISCORD_BOT_TOKEN")
    try:
        r = requests.post(
            _DISCORD_DM,
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"recipient_id": user_id},
            timeout=15,
        )
        if r.status_code in (200, 201):
            _dm_channel_cache = r.json().get("id")
            return _dm_channel_cache
        log.warning("Discord DM create fail HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        log.warning("Discord DM create error: %s", exc)
    return None


def _telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_HMIP_MARKET_BOT") and os.getenv("TELEGRAM_CHAT_ID"))


def _format(alert: dict, pack_size: int = 24, unit_ml: int = 330) -> str:
    etype = alert.get("event_type", "PRICE")
    pname = alert.get("product_name") or alert.get("sku_id") or "?"
    chan = alert.get("channel_id", "?")
    reg = alert.get("region_id", "?")
    pct = alert.get("change_pct", alert.get("price_change_pct", "?"))
    # Quy đổi giá/lon sang thùng (×pack_size) và chai (≈lon cùng dung tích).
    def _fmt(v):
        return f"{float(v):,.0f}" if isinstance(v, (int, float)) else "—"

    old = alert.get("old_price")
    new = alert.get("new_price")
    old_s, new_s = _fmt(old), _fmt(new)
    new_box = _fmt(float(new) * pack_size) if isinstance(new, (int, float)) else "—"
    old_box = _fmt(float(old) * pack_size) if isinstance(old, (int, float)) else "—"
    unit_label = f"{unit_ml}ml" if unit_ml else ""
    return (
        f"🔔 **HMIP Price Alert** [{etype}]\n"
        f"• Sản phẩm: {pname}\n"
        f"• Kênh: {chan} | Vùng: {reg}\n"
        f"• Giá (lon): {old_s}₫ → {new_s}₫/lon ({pct}%)\n"
        f"• Giá thùng ({pack_size} lon): {old_box}₫ → {new_box}₫/thùng\n"
        f"• Giá chai ({unit_label}): ≈{new_s}₫/chai\n"
        f"• Thời gian: {alert.get('timestamp', '?')}"
    )


def send_discord(message: str) -> bool:
    _maybe_load_env()
    if not _discord_configured():
        log.info("Discord chưa cấu hình (thiếu DISCORD_BOT_TOKEN + target)")
        return False
    token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = _resolve_discord_channel()
    if not channel_id:
        log.warning("Discord: không lấy được channel_id (DM create fail?)")
        return False
    try:
        r = requests.post(
            _DISCORD_MSG.format(channel_id=channel_id),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            json={"content": message, "allowed_mentions": {"parse": []}},
            timeout=15,
        )
        if r.status_code not in (200, 201):
            log.warning("Discord send fail HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as exc:
        log.warning("Discord send error: %s", exc)
        return False


def send_telegram(message: str) -> bool:
    _maybe_load_env()
    if not _telegram_configured():
        log.info("Telegram chưa cấu hình (thiếu TELEGRAM_HMIP_MARKET_BOT/TELEGRAM_CHAT_ID)")
        return False
    token = os.getenv("TELEGRAM_HMIP_MARKET_BOT")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    try:
        r = requests.post(
            _TELEGRAM_API.format(token=token),
            json={"chat_id": chat, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        if r.status_code != 200:
            log.warning("Telegram send fail HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as exc:
        log.warning("Telegram send error: %s", exc)
        return False


def notify_alert(alert: dict) -> dict[str, bool]:
    """Gửi 1 alert tới các kênh đã cấu hình. Trả {discord, telegram}.

    Chống spam (3 lớp, áp dụng tại đây — điểm funnel duy nhất mọi caller
    đi qua, gồm collector + detect_events):
    1. Min-change: bỏ qua alert có |change_pct| < HMIP_NOTIFY_MIN_PCT
       (mặc định 5%) — không notify noise dao động nhỏ 1-5%.
    2. Cooldown per-sku: bỏ qua nếu SP đã notify trong HMIP_NOTIFY_SKU_COOLDOWN_MIN
       (mặc định 30') gần đây BẤT KỂ kênh nào — chống spam khi multi-channel
       (Tiki+Shopee+Lazada) cùng đổi giá 1 SP → chỉ kênh đầu notify.
    3. Cooldown per-(sku,channel,region): bỏ qua nếu cùng (sku,channel,region)
       đã notify trong HMIP_NOTIFY_COOLDOWN_MIN (mặc định 6h) gần đây — tránh
       gửi liên tục cùng 1 SP khi giá dao động qua lại trên 1 kênh.
    Alert bị bỏ qua vẫn trả {discord:False, telegram:False} (không gửi).
    """
    # Lớp 1: min-change filter.
    pct = _alert_change_pct(alert)
    if pct is not None and pct < _min_change_pct():
        log.info("Notify skip (change %.2f%% < min %.2f%%): %s",
                 pct, _min_change_pct(), _notify_key(alert))
        return {"discord": False, "telegram": False}

    # Lớp 2 + 3: cooldown filter (per-sku rồi per-channel).
    if _is_suppressed_by_cooldown(alert):
        log.info("Notify skip (cooldown): %s", _notify_key(alert))
        return {"discord": False, "telegram": False}

    msg = _format(alert, alert.get("pack_size", 24), alert.get("unit_ml", 330))
    result = {"discord": send_discord(msg), "telegram": send_telegram(msg)}
    # Chỉ ghi nhận cooldown khi ít nhất 1 kênh gửi thành công — nếu gửi
    # fail (mạng/token), alert sau vẫn được thử lại.
    if result["discord"] or result["telegram"]:
        _record_notify_sent(alert)
    return result


def notify_alerts(alerts: list[dict]) -> dict[str, int]:
    """Gửi nhiều alert (chỉ CRITICAL). Trả số lượng gửi thành công."""
    sent = {"discord": 0, "telegram": 0}
    for a in alerts:
        if (a.get("severity") or a.get("alert_level")) != "CRITICAL":
            continue
        res = notify_alert(a)
        sent["discord"] += int(res["discord"])
        sent["telegram"] += int(res["telegram"])
    return sent

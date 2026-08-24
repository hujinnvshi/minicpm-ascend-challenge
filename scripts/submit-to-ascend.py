#!/usr/bin/env python3
"""submit-to-ascend.py — 赛事提交一键脚本（sendmessage → login → check → OBS PUT → confirm）

用法:
  1) 发验证码:   python3 scripts/submit-to-ascend.py send
  2) 登录+提交:  python3 scripts/submit-to-ascend.py submit <验证码> <zip路径> ["描述"]

依赖: 无第三方库（urllib 标准库）；cookie 存 /tmp/ascend-cookies.txt。
账号: 18510911437（张宁，杭州闪捷信息科技）；赛道一 sub_track=llama_cpp_omni。
链路与坑位详见 docs/ops-handoff.md（2026-08-24 v6 实测）：
  - sendmessage/login 的 userID 用手机号（非 hex userID）
  - cookie 从 Set-Cookie 原始头提取 cail_session（cookiejar 提取失效）
  - CONFIRM 必须带 oss_key（upload_model_check 返回值）
  - OBS SigV4 必带 x-amz-content-sha256 头（否则 HTTP 400）
"""
import hashlib, hmac, json, sys, urllib.request, urllib.error
from datetime import datetime, timezone

API = "https://ascend.openbmb.cn/api"
COOKIE = "/tmp/ascend-cookies.txt"
PHONE = "18510911437"
USER_ID = "f795942961c3"  # 平台 hex userID（upload_model_check/upload_model 用）
CAIL_TAG = "2026"
RACE_ID = "0"
SUB_TRACK = "llama_cpp_omni"


def api_post(path, body, save_cookie=False):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Origin": "https://ascend.openbmb.cn"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        if save_cookie:
            setcookies = r.headers.get_all("Set-Cookie") or []
            if setcookies:
                with open(COOKIE, "w") as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for sc in setcookies:
                        name, _, value = sc.split(";")[0].partition("=")
                        f.write(f".openbmb.cn\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
                print(f"  cookie 已保存: {setcookies[0].split(';')[0]}")
            else:
                print("  !! 无 Set-Cookie（登录态可能未建立）")
        return json.loads(data)


def api_post_auth(path, body):
    with open(COOKIE) as f:
        ck = f.read().strip().replace("\n", "; ")
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Origin": "https://ascend.openbmb.cn", "Cookie": ck})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def sign_v4(ak, sk, token, bucket, endpoint, obj_key, body):
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    body_hash = hashlib.sha256(body).hexdigest()
    host = f"{bucket}.{endpoint.replace('https://', '')}"
    canonical_headers = (f"host:{host}\n"
                         f"x-amz-content-sha256:{body_hash}\n"
                         f"x-amz-date:{amz_date}\n"
                         f"x-amz-security-token:{token}\n")
    signed_headers = "host;x-amz-content-sha256;x-amz-date;x-amz-security-token"
    canonical_request = f"PUT\n/{obj_key}\n\n{canonical_headers}\n{signed_headers}\n{body_hash}"
    scope = f"{date_stamp}/cn-north-4/s3/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

    def hmac_sha256(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = hmac_sha256(("AWS4" + sk).encode(), date_stamp)
    k_region = hmac_sha256(k_date, "cn-north-4")
    k_service = hmac_sha256(k_region, "s3")
    k_signing = hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, SignedHeaders={signed_headers}, "
            f"Signature={signature}")
    return host, amz_date, body_hash, auth


def cmd_send():
    print("[send] 发送验证码 ...")
    r = api_post("/sendmessage", {"userID": PHONE, "type": "phone", "country_code": "+86"})
    print("  ", json.dumps(r, ensure_ascii=False)[:200])
    if r.get("resultcode") != "0000":
        sys.exit(1)
    print(f"  验证码已发到 {PHONE}，60s 冷却；收到后运行: python3 scripts/submit-to-ascend.py submit <验证码> <zip>")


def cmd_submit(code, zip_path, description):
    print("[1/4] login ...")
    r = api_post("/login", {"userID": PHONE, "code": code, "login_type": "phone",
                            "country_code": "+86", "cail_tag": CAIL_TAG}, save_cookie=True)
    print("  ", json.dumps(r, ensure_ascii=False)[:200])
    if r.get("resultcode") not in ("0000", None) and r.get("result") != "0000":
        print("LOGIN_FAILED"); sys.exit(1)

    print("[2/4] upload_model_check ...")
    r = api_post_auth("/upload_model_check", {"userID": USER_ID, "cail_tag": CAIL_TAG,
                                              "raceID": RACE_ID, "step": "0", "env": "production"})
    if r.get("result") != "0000":
        print("CHECK_FAILED:", json.dumps(r, ensure_ascii=False)[:300]); sys.exit(1)
    d = r["data"]
    print(f"  oss_key={d['oss_key']}")

    print("[3/4] OBS PUT ...")
    body = open(zip_path, "rb").read()
    host, amz_date, body_hash, auth = sign_v4(d["access_key_id"], d["access_key_secret"],
                                              d["security_token"], d["bucket"], d["endpoint"],
                                              d["oss_key"], body)
    req = urllib.request.Request(f"{d['endpoint']}/{d['oss_key']}", data=body, method="PUT", headers={
        "Host": host, "x-amz-content-sha256": body_hash, "x-amz-date": amz_date,
        "x-amz-security-token": d["security_token"], "Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            print(f"  OBS PUT → {resp.status} ({len(body)} bytes)")
    except urllib.error.HTTPError as e:
        print(f"  OBS PUT FAILED → {e.code}: {e.read()[:300]}"); sys.exit(1)

    print("[4/4] upload_model confirm ...")
    r2 = api_post_auth("/upload_model", {
        "userID": USER_ID, "cail_tag": CAIL_TAG, "raceID": RACE_ID, "step": "0", "env": "production",
        "description": description, "oss_key": d["oss_key"], "sub_track": SUB_TRACK, "demo_url": ""})
    print("  ", json.dumps(r2, ensure_ascii=False)[:400])
    if r2.get("result") == "0000" or r2.get("resultcode") == "0000":
        print("SUBMISSION_OK")
    else:
        print("SUBMISSION_CHECK_RESPONSE_ABOVE"); sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    if sys.argv[1] == "send":
        cmd_send()
    elif sys.argv[1] == "submit":
        if len(sys.argv) < 4:
            print("用法: submit <验证码> <zip路径> [描述]"); sys.exit(1)
        desc = sys.argv[4] if len(sys.argv) > 4 else f"submit {sys.argv[2]}"
        cmd_submit(sys.argv[2], sys.argv[3], desc)
    else:
        print(__doc__); sys.exit(1)

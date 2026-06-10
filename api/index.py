import os, logging, xml.etree.ElementTree as ET, json
from flask import Flask, request, jsonify
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

CORP_ID = os.environ.get("WECOM_CORP_ID", "")
AGENT_ID = os.environ.get("WECOM_AGENT_ID", "")
SECRET = os.environ.get("WECOM_SECRET", "")
TOKEN = os.environ.get("WECOM_TOKEN", "")
ENCODING_AES_KEY = os.environ.get("WECOM_AES_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

crypto = WeChatCrypto(TOKEN, ENCODING_AES_KEY, CORP_ID)
wc = WeChatClient(CORP_ID, SECRET)
ds = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
history = {}

@app.route("/callback", methods=["GET", "POST"])
def callback():
    if request.method == "GET":
        sig = request.args.get("msg_signature", "")
        ts = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        echostr = request.args.get("echostr", "")
        log.info(f"Verify: sig={sig[:20]}...")
        try:
            return crypto.check_signature(sig, ts, nonce, echostr)
        except InvalidSignatureException:
            log.error("Verify FAIL")
            return "fail", 403

    sig = request.args.get("msg_signature", "")
    ts = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")
    body = request.data.decode("utf-8")
    log.info(f"Msg: {body[:200]}")
    try:
        xml = crypto.decrypt_message(body, sig, ts, nonce)
    except InvalidSignatureException:
        return "fail", 403

    root = ET.fromstring(xml)
    tp = root.findtext("MsgType", "")
    uid = root.findtext("FromUserName", "")
    txt = root.findtext("Content", "")
    log.info(f"Type={tp} User={uid} Text={txt}")
    if tp != "text" or not txt:
        return ""

    if uid not in history:
        history[uid] = []
    h = history[uid]
    h.append({"role": "user", "content": txt})
    msgs = [{"role": "system", "content": "You are a friendly chat assistant. Reply in natural, concise Chinese like a real friend."}] + h[-20:]
    try:
        r = ds.chat.completions.create(model="deepseek-chat", messages=msgs, temperature=0.8, max_tokens=1000)
        reply = r.choices[0].message.content
        h.append({"role": "assistant", "content": reply})
        history[uid] = h[-20:]
        log.info(f"Reply: {reply[:80]}")
    except Exception as e:
        reply = f"Error: {e}"
        log.error(str(e))

    try:
        wc.message.send_text(AGENT_ID, uid, reply)
        log.info(f"Sent to {uid}")
    except Exception as e:
        log.error(f"Send failed: {e}")

    return ""

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

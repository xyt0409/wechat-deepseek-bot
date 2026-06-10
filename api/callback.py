from http.server import BaseHTTPRequestHandler
import os, json, logging, xml.etree.ElementTree as ET
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from openai import OpenAI
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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

def handler(event, context):
    """Vercel serverless handler"""
    path = event.get("path", "/")
    method = event.get("httpMethod", "GET")
    qs = event.get("queryStringParameters", {}) or {}
    body = event.get("body", "") or ""

    if path == "/callback":
        if method == "GET":
            sig = qs.get("msg_signature", "")
            ts = qs.get("timestamp", "")
            nonce = qs.get("nonce", "")
            echostr = qs.get("echostr", "")
            log.info(f"Verify: sig={sig[:20]}...")
            try:
                result = crypto.check_signature(sig, ts, nonce, echostr)
                return {"statusCode": 200, "body": result}
            except InvalidSignatureException:
                return {"statusCode": 403, "body": "fail"}

        if method == "POST":
            sig = qs.get("msg_signature", "")
            ts = qs.get("timestamp", "")
            nonce = qs.get("nonce", "")
            log.info(f"Msg received")
            try:
                xml = crypto.decrypt_message(body, sig, ts, nonce)
            except InvalidSignatureException:
                return {"statusCode": 403, "body": "fail"}

            root = ET.fromstring(xml)
            tp = root.findtext("MsgType", "")
            uid = root.findtext("FromUserName", "")
            txt = root.findtext("Content", "")
            log.info(f"Type={tp} User={uid} Text={txt}")
            if tp != "text" or not txt:
                return {"statusCode": 200, "body": ""}

            if uid not in history:
                history[uid] = []
            h = history[uid]
            h.append({"role": "user", "content": txt})
            msgs = [{"role": "system", "content": "You are a friendly chat assistant. Reply in natural, concise Chinese."}] + h[-20:]
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

            return {"statusCode": 200, "body": ""}

    if path == "/health":
        return {"statusCode": 200, "body": json.dumps({"status": "ok"})}

    return {"statusCode": 404, "body": "Not Found"}

# Vercel entry point
from http.server import BaseHTTPRequestHandler
from io import BytesIO
import urllib.parse

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle("GET")
    def do_POST(self):
        self._handle("POST")
    
    def _handle(self, method):
        parsed = urllib.parse.urlparse(self.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()} if parsed.query else {}
        body = ""
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
        
        event = {"path": parsed.path, "httpMethod": method, "queryStringParameters": qs, "body": body}
        result = globals()["handler"](event, None)
        
        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(result["body"].encode("utf-8"))

    def log_message(self, format, *args):
        log.info(f"{args}")

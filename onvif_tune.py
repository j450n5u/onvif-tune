#!/usr/bin/env python3
"""onvif-tune — read and set video encoder settings (codec, bitrate) on ONVIF
Media2 cameras from the command line. No vendor app, no dependencies.

Usage:
  onvif_tune.py <ip> show
  onvif_tune.py <ip> options <token>
  onvif_tune.py <ip> set <token> <H264|H265> <bitrateKbps>

Credentials come from ONVIF_USER / ONVIF_PASS environment variables
(or --user / --password flags). Auth is WS-UsernameToken digest, which is
what most cameras actually speak on /onvif/service.
"""
import sys, os, base64, hashlib, re, argparse
import datetime
import urllib.request


def security_header(user, password):
    nonce = os.urandom(16)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + password.encode()).digest()
    ).decode()
    return f"""<s:Header><wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
<wsse:UsernameToken><wsse:Username>{user}</wsse:Username>
<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</wsse:Nonce>
<wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header>"""


def call(url, user, password, body, timeout=15):
    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
{security_header(user, password)}<s:Body>{body}</s:Body></s:Envelope>"""
    req = urllib.request.Request(
        url,
        data=envelope.encode(),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def show(url, user, password):
    code, text = call(url, user, password, "<tr2:GetVideoEncoderConfigurations/>")
    found = False
    for m in re.finditer(r'<tr2:Configurations token="([^"]+)"[^>]*>(.*?)</tr2:Configurations>', text, re.S):
        found = True
        tok, blk = m.group(1), m.group(2)
        g = lambda p: (re.search(p, blk) and re.search(p, blk).group(1))
        enc, w, h = g(r"<tt:Encoding>([^<]+)"), g(r"<tt:Width>(\d+)"), g(r"<tt:Height>(\d+)")
        fps, br = g(r"<tt:FrameRateLimit>([\d.]+)"), g(r"<tt:BitrateLimit>(\d+)")
        gov, prof = g(r"<tt:GovLength>(\d+)"), g(r"<tt:Profile>([^<]+)")
        print(f"token={tok} enc={enc} {w}x{h} fps={fps} bitrate={br} gov={gov} profile={prof}")
    if not found:
        print(f"HTTP {code} — no encoder configurations in reply:")
        print(text[:1500])
        sys.exit(1)


def options(url, user, password, token):
    code, text = call(url, user, password,
        f"<tr2:GetVideoEncoderConfigurationOptions><tr2:ConfigurationToken>{token}</tr2:ConfigurationToken></tr2:GetVideoEncoderConfigurationOptions>")
    found = False
    for m in re.finditer(r"<tr2:Options[^>]*>(.*?)</tr2:Options>", text, re.S):
        found = True
        blk = m.group(1)
        enc = re.search(r"<tt:Encoding>([^<]+)</tt:Encoding>", blk)
        br = re.search(r"<tt:BitrateRange>.*?<tt:Min>(\d+)</tt:Min>.*?<tt:Max>(\d+)</tt:Max>", blk, re.S)
        print("option:", enc and enc.group(1), "bitrate", br and (br.group(1) + "-" + br.group(2)))
    if not found:
        print(f"HTTP {code} — no options in reply:")
        print(text[:1500])
        sys.exit(1)


def set_encoder(url, user, password, token, encoding, kbps):
    # Fetch current config first so resolution/fps/gov/quality survive the write —
    # SetVideoEncoderConfiguration replaces the whole block, not just the fields you send.
    code, text = call(url, user, password, "<tr2:GetVideoEncoderConfigurations/>")
    m = re.search(r'<tr2:Configurations token="' + re.escape(token) + r'"[^>]*>(.*?)</tr2:Configurations>', text, re.S)
    if not m:
        print(f"token '{token}' not found on camera (run 'show' first)")
        sys.exit(1)
    blk = m.group(1)
    g = lambda p, d=None: (re.search(p, blk, re.S).group(1) if re.search(p, blk, re.S) else d)
    w, h = g(r"<tt:Width>(\d+)"), g(r"<tt:Height>(\d+)")
    fps = g(r"<tt:FrameRateLimit>([\d.]+)")
    qual = g(r"<tt:Quality>([\d.]+)", "3")
    gov = g(r"<tt:GovLength>(\d+)", "50")
    cbr = g(r"<tt:ConstantBitRate>(\w+)", "false")
    mc = g(r"<tt:Multicast>(.*)</tt:Multicast>")
    mcx = f"<tt:Multicast>{mc}</tt:Multicast>" if mc else ""
    body = f"""<tr2:SetVideoEncoderConfiguration>
<tr2:Configuration token="{token}" GovLength="{gov}">
<tt:Name>VideoEncoder_{token}</tt:Name><tt:UseCount>1</tt:UseCount>
<tt:Encoding>{encoding}</tt:Encoding>
<tt:Resolution><tt:Width>{w}</tt:Width><tt:Height>{h}</tt:Height></tt:Resolution>
<tt:RateControl ConstantBitRate="{cbr}"><tt:FrameRateLimit>{fps}</tt:FrameRateLimit><tt:BitrateLimit>{kbps}</tt:BitrateLimit></tt:RateControl>
{mcx}<tt:Quality>{qual}</tt:Quality>
</tr2:Configuration></tr2:SetVideoEncoderConfiguration>"""
    code, text = call(url, user, password, body)
    if "Fault" in text:
        print("FAULT", code, re.sub(r"\s+", " ", text)[:800])
        sys.exit(1)
    # Read back to prove the camera actually took it.
    code, text = call(url, user, password, "<tr2:GetVideoEncoderConfigurations/>")
    m = re.search(r'<tr2:Configurations token="' + re.escape(token) + r'"[^>]*>(.*?)</tr2:Configurations>', text, re.S)
    blk = m.group(1)
    enc = re.search(r"<tt:Encoding>([^<]+)</tt:Encoding>", blk).group(1)
    br = re.search(r"<tt:BitrateLimit>(\d+)</tt:BitrateLimit>", blk).group(1)
    print(f"OK enc={enc} bitrate={br}")


def main():
    ap = argparse.ArgumentParser(description="Tune ONVIF Media2 camera encoders from the CLI.")
    ap.add_argument("ip", help="camera IP or host[:port]")
    ap.add_argument("command", choices=["show", "options", "set"])
    ap.add_argument("args", nargs="*", help="options: <token> | set: <token> <H264|H265> <bitrateKbps>")
    ap.add_argument("--user", default=os.environ.get("ONVIF_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("ONVIF_PASS"))
    a = ap.parse_args()
    if not a.password:
        ap.error("set ONVIF_PASS or pass --password")
    url = f"http://{a.ip if ':' in a.ip else a.ip + ':80'}/onvif/service"
    if a.command == "show":
        show(url, a.user, a.password)
    elif a.command == "options":
        if len(a.args) != 1:
            ap.error("options needs <token>")
        options(url, a.user, a.password, a.args[0])
    else:
        if len(a.args) != 3:
            ap.error("set needs <token> <H264|H265> <bitrateKbps>")
        set_encoder(url, a.user, a.password, a.args[0], a.args[1], a.args[2])


if __name__ == "__main__":
    main()

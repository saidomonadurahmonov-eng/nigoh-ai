"""Ofis/do'kon tarmog'idagi kameralarni qidiradi.

Kameralar ulangan WiFi/tarmoqqa ulangan kompyuterda ishga tushiring:
    .venv\\Scripts\\python tools\\kamera_qidir.py

Ikki usulda qidiradi: ONVIF e'lon (kameralar o'zini tanishtiradi) va
554-port (RTSP eshigi) ochiqligini tekshirish. Hech narsaga ulanmaydi,
parol talab qilmaydi — faqat "kim bor?" deb so'raydi.
"""
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor

PROBE = f'''<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header><w:MessageID>uuid:{uuid.uuid4()}</w:MessageID>
<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>'''


def onvif_qidir(timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(timeout)
    topildi = set()
    try:
        s.sendto(PROBE.encode(), ("239.255.255.250", 3702))
        while True:
            _, addr = s.recvfrom(65535)
            topildi.add(addr[0])
    except socket.timeout:
        pass
    except OSError:
        pass
    finally:
        s.close()
    return topildi


def lokal_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def port_ochiqmi(ip, port=554, timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    finally:
        s.close()


if __name__ == "__main__":
    print("ONVIF qidiruv (3 soniya)...")
    onvif = onvif_qidir()
    me = lokal_ip()
    baza = ".".join(me.split(".")[:3])
    print(f"Sizning IP: {me}. {baza}.1-254 oralig'ida 554-port tekshirilmoqda...")
    ips = [f"{baza}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(64) as ex:
        ochiq = [ip for ip, ok in zip(ips, ex.map(port_ochiqmi, ips)) if ok]
    hammasi = sorted(set(ochiq) | onvif,
                     key=lambda x: tuple(int(p) for p in x.split(".")))
    if not hammasi:
        print("Kamera topilmadi. Kameralar boshqa tarmoqda (masalan NVR ning "
              "orqasidagi POE portlarda) bo'lishi mumkin - unda NVR IP sini izlang.")
    for ip in hammasi:
        belgi = []
        if ip in onvif:
            belgi.append("ONVIF kamera")
        if ip in ochiq:
            belgi.append("RTSP 554 ochiq")
        print(f"  {ip}   ({', '.join(belgi)})")
    print()
    print("Sinash uchun manzillar (PAROL o'rniga kamera/NVR parolini qo'ying):")
    print("  Hikvision kamera:  rtsp://admin:PAROL@IP:554/Streaming/Channels/102")
    print("  Hikvision NVR:     kanal N uchun N02 (2-kanal: 202, 3-kanal: 302)")
    print("  Dahua:             rtsp://admin:PAROL@IP:554/cam/realmonitor?channel=1&subtype=1")

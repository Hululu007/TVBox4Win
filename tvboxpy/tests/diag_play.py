# -*- coding: utf-8 -*-
"""无头诊断：量子资源 → 详情 → 播放地址 → requests 探测 → mpv 播放抓日志"""
import sys, os, time
sys.path.insert(0, r'D:\code\tvbox2exe\tvboxpy')
os.chdir(r'D:\code\tvbox2exe\tvboxpy')

from tvboxosc import data_api, apiconfig

done = []
apiconfig.api_config.load('https://cyao2q.github.io/files/m.json',
                          lambda: done.append(1), lambda e: print('err', e))
for _ in range(60):
    if done:
        break
    time.sleep(0.5)

bean = apiconfig.api_config.get('量子资源')
print('bean:', bean, flush=True)
vods, _, _ = data_api.get_vods(bean, None, 1)
print('vods:', len(vods), flush=True)
target = None
for v in vods:
    if '斗破' in (v[1] or ''):
        target = v
        break
if not target:
    target = vods[0]
print('target:', target[1], target[0], flush=True)

info = data_api.get_detail(bean, target[0])
print('flags:', [f[0] for f in info['series_flags']], flush=True)
flag, names = info['series_flags'][0]
urls = info['series_urls'][0]
print('ep0:', names[0], urls[0], flush=True)

real, hdr = data_api.get_play_url(bean, flag, urls[0])
print('real:', real, flush=True)
print('hdr:', hdr, flush=True)

import requests
try:
    r = requests.get(real, headers=hdr or {}, stream=True, timeout=10)
    print('HTTP', r.status_code, r.headers.get('content-type'),
          r.headers.get('content-length'), flush=True)
    r.close()
except Exception as e:
    print('requests failed:', e, flush=True)

# mpv 播放测试（带日志回调）
import mpv
logs = []
player = mpv.MPV(log_handler=lambda l: logs.append(l),
                 loglevel='debug', wid=None, osc='yes',
                 force_window='immediate', keep_open='yes')
if hdr:
    player['http-header-fields'] = [f'{k}: {v}' for k, v in hdr.items()]
player.command('loadfile', real)
for i in range(30):
    time.sleep(1)
    try:
        print('%02ds pos=%.1f dur=%.1f idle=%s eof=%s pause=%s' % (
            i, player.playback_time or 0, player.duration or 0,
            player.idle_active, player.eof_reached, player.pause), flush=True)
    except Exception as e:
        print('%02ds status err: %s' % (i, e), flush=True)
    if (player.playback_time or 0) > 2:
        print('>>> PLAYING OK', flush=True)
        break
print('---- mpv log (warn+) ----', flush=True)
for l in logs:
    if l.get('level') in ('warn', 'error', 'fatal'):
        print(l.get('level'), l.get('prefix'), l.get('text'), flush=True)
player.terminate()

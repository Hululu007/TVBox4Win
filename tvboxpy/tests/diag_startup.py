# -*- coding: utf-8 -*-
"""起播耗时诊断：URL解析 / loadfile→首帧 分段计时，对比 mpv 配置"""
import sys, time, os
sys.path.insert(0, r'D:\code\tvbox2exe\tvboxpy')
os.environ['PATH'] = (r'D:\code\tvbox2exe\tvboxpy\third_party\mpv'
                      + os.pathsep + os.environ.get('PATH', ''))
import mpv

from tvboxosc import data_api, apiconfig

done = []
apiconfig.api_config.load('https://cyao2q.github.io/files/m.json',
                          lambda: done.append(1))
for _ in range(60):
    if done:
        break
    time.sleep(0.5)

bean = apiconfig.api_config.get('量子资源')
vods, _, _ = data_api.get_vods(bean, None, 1)
vid, name = vods[0][0], vods[0][1]
info = data_api.get_detail(bean, vid)
flag, ep_url = info['series_flags'][0][0], info['series_urls'][0][0]
print('vod:', name, 'flag:', flag, flush=True)

t0 = time.time()
real, hdr = data_api.get_play_url(bean, flag, ep_url)
print('resolve: %.2fs ->' % (time.time() - t0), real[:80], flush=True)

HDRS = [f'{k}: {v}' for k, v in (hdr or {}).items()]


def measure(tag, **kw):
    m = mpv.MPV(vo='null', audio='no', osc='no', **kw)
    if HDRS:
        m['http-header-fields'] = HDRS
    t = time.time()
    m.command('loadfile', real)
    ok = False
    while time.time() - t < 30:
        try:
            if not m.core_idle and (m.playback_time or 0) > 0:
                ok = True
                break
        except Exception:
            break
        time.sleep(0.1)
    print('%s: %s %.2fs' % (tag, 'OK' if ok else 'TIMEOUT',
                            time.time() - t), flush=True)
    m.terminate()
    time.sleep(1)


measure('baseline(默认)')
measure('cache(当前线上配置)', cache='yes', demuxer_max_bytes='48MiB',
        demuxer_max_back_bytes='8MiB', network_timeout=8)
measure('lowlatency(+小缓冲)', cache='yes', demuxer_max_bytes='48MiB',
        demuxer_max_back_bytes='8MiB', network_timeout=8,
        demuxer_readahead_secs='0.5', cache_pause_initial='no',
        demuxer_lavf_analyzeduration='2.0', demuxer_lavf_probesize='500k')

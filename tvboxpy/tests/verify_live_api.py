# -*- coding: utf-8 -*-
"""验证「配置地址」双输入弹窗（点播 + 直播）与直播源保存逻辑

不依赖鼠标：直接驱动 Page 方法 + 截图核对视觉，最后清理测试写入的 hawk 值。
产物：dist/v1_settings.png / dist/v2_api_dialog.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import tkinter as tk
from PIL import ImageGrab

from tvboxosc import hawk
from tvboxosc.app import App
from tvboxosc.ui_setting import Page as SettingPage

OUT = os.path.join(ROOT, 'dist')
os.makedirs(OUT, exist_ok=True)

SAMPLE = os.path.join(OUT, '_live_test.txt')
with open(SAMPLE, 'w', encoding='utf-8') as f:
    f.write("央视频道,#genre#\nCCTV1,http://a.example/1.m3u8$源1\n卫视,#genre#\n"
            "湖南卫视,http://b.example/hn.m3u8\n")

app = App()
ctx = {}


def shot(name):
    app.update()
    ImageGrab.grab().save(os.path.join(OUT, name + '.png'))
    print('shot', name, flush=True)


def step_settings():
    page = app.switch(SettingPage)
    ctx['page'] = page
    app.after(600, lambda: (shot('v1_settings'), step_dialog()))


def step_dialog():
    page = ctx['page']
    print('设置卡片:', list(page._vars.keys()), flush=True)
    print('直播地址卡片值:', page._vars['直播地址'].get(), flush=True)
    page._edit_api()
    win = [w for w in page.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    ctx['win'] = win
    # 收集弹窗里的 Entry（应为 2 个：点播 / 直播）
    def entries(w):
        out = []
        for c in w.winfo_children():
            if isinstance(c, tk.Entry):
                out.append(c)
            out += entries(c)
        return out
    ents = entries(win)
    ctx['ents'] = ents
    print('弹窗输入框数量:', len(ents), flush=True)
    print('点播输入框:', repr(ents[0].get()), flush=True)
    print('直播输入框:', repr(ents[1].get()), flush=True)
    app.after(500, lambda: (shot('v2_api_dialog'), step_save()))


def step_save():
    page = ctx['page']
    ctx['win'].destroy()
    page._save_live(SAMPLE)
    app.update()
    print('hawk live_api_url:', hawk.get(hawk.LIVE_API_URL), flush=True)
    print('hawk live_api_history:', hawk.get(hawk.LIVE_API_HISTORY), flush=True)
    print('状态栏:', page.status.cget('text'), flush=True)


def finish():
    # 校验解析结果
    from tvboxosc.ui_live import read_live_source, parse_live_source
    name, chs = parse_live_source(read_live_source(SAMPLE), SAMPLE)
    print('解析:', name, len(chs), '个频道', flush=True)
    # 清理测试写入
    hawk.delete(hawk.LIVE_API_URL)
    hawk.delete(hawk.LIVE_API_HISTORY)
    os.remove(SAMPLE)
    app.destroy()


app.after(400, step_settings)
app.after(4200, finish)
app.mainloop()
print('DONE', flush=True)

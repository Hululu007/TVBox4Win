/* Spider bridge: 在 Node 里跑 drpy/CatVod JS 爬虫，stdio JSON-RPC 与 Python 通信
 * 用法: node bridge.js <drpy.js> <ext_site.js> <runtime_dir>
 * 协议: 每行一个 JSON {"id":n,"method":"init|home|homeVod|category|detail|search|play","args":[...]}
 * 响应: {"id":n,"ok":true,"result":...} 或 {"id":n,"ok":false,"error":"..."}
 */
const fs = require('fs');
const path = require('path');

const [, , drpyPath, extPath, runtimeDir] = process.argv;

// ---------- 宿主原生函数（对应 CatVod QuickJS 环境的 Java natives） ----------
const { spawnSync } = require('child_process');

function _curl(url, options) {
    options = options || {};
    const args = ['-s', '-L', '--compressed', '-m', '20', '-i'];
    if (options.headers) {
        for (const [k, v] of Object.entries(options.headers))
            args.push('-H', `${k}: ${v}`);
    }
    const method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET') args.push('-X', method);
    if (options.body) args.push('--data-binary', String(options.body));
    args.push(url);
    const r = spawnSync('curl', args, { encoding: 'buffer', maxBuffer: 32 << 20 });
    const out = r.stdout ? r.stdout : Buffer.alloc(0);
    // 重定向链会产生多段 header 块，循环剥到最后的 body
    let rest = out, head = '';
    for (;;) {
        const sep = rest.indexOf('\r\n\r\n') >= 0 ? '\r\n\r\n' : '\n\n';
        const cut = rest.indexOf(sep);
        if (cut < 0) break;
        head = rest.slice(0, cut).toString('utf-8');
        const bodyPart = rest.slice(cut + sep.length);
        if (/^HTTP\/[\d.]+\s+\d+/.test(bodyPart.toString('utf-8', 0, 20))) { rest = bodyPart; continue; }
        rest = bodyPart;
        break;
    }
    let body = rest;
    const status = parseInt((head.match(/HTTP\/[\d.]+\s+(\d+)/) || [])[1] || '0');
    // dechunk
    // 仅当 body 确实是 chunked 原始格式（首行 hex 长度）才 dechunk
    const firstLine = body.slice(0, body.indexOf('\r\n') >= 0 ? body.indexOf('\r\n') : 0).toString('ascii');
    if (/transfer-encoding:\s*chunked/i.test(head) && /^[0-9a-fA-F]{1,8}\r?$/.test(firstLine) && firstLine) {
        const out2 = Buffer.alloc(body.length);
        let i = 0, o = 0;
        while (i < body.length) {
            const nl = body.indexOf('\r\n', i);
            if (nl < 0) break;
            const size = parseInt(body.slice(i, nl).toString('ascii').split(';')[0], 16);
            if (!size) break;
            body.copy(out2, o, nl + 2, nl + 2 + size);
            o += size;
            i = nl + 2 + size + 2;
        }
        body = out2.slice(0, o);
    }
    return { status, headers: head, body };
}

globalThis.request = function (url, options) {
    url = globalThis._rewriteUrl(url);
    const r = _curl(url, options);
    if (r.status >= 300 && r.status < 400) { // 跟随少量重定向
        const loc = (r.headers.match(/location:\s*(\S+)/i) || [])[1];
        if (loc) return globalThis.request(loc, options);
    }
    return r.body.toString('utf-8');
};

globalThis.req = function (url, options) {
    url = globalThis._rewriteUrl(url);
    const r = _curl(url, options);
    _origConsoleError('[req]', r.status, url, JSON.stringify(r.body.toString('utf-8').slice(0, 120)));
    const text = r.body.toString('utf-8');
    return {
        content: text,
        headers: r.headers,
        statusCode: r.status,
        json() { try { return JSON.parse(text); } catch { return null; } },
    };
};

const _origConsoleError = console.error.bind(console);
globalThis.log = function (...a) { _origConsoleError('[js]', ...a); };
globalThis.print = globalThis.log;
// 爬虫代码的 console 输出全部走 stderr，避免污染 stdio JSON-RPC
console.log = globalThis.log;
console.info = globalThis.log;
console.warn = globalThis.log;
console.error = globalThis.log;

// 被墙/失效源自动改写
const _URL_REWRITES = [
    [/^https?:\/\/gitcode\.net\/qq_32394351\/dr_py\/-\/raw\/master\//,
     'https://gh-proxy.com/https://raw.githubusercontent.com/hjdhnx/dr_py/main/'],
    [/^https?:\/\/ghproxy\.com\//, 'https://gh-proxy.com/'],
];

globalThis._rewriteUrl = function (url) {
    for (const [re, to] of _URL_REWRITES) if (re.test(url)) return url.replace(re, to);
    return url;
};

globalThis.local = {
    _m: {},
    get(k, d) { return k in this._m ? this._m[k] : d; },
    set(k, v) { this._m[k] = v; },
    put(k, v) { this._m[k] = v; },
    delete(k) { delete this._m[k]; },
    clearAll() { this._m = {}; },
};

globalThis.urljoin = function (base, rel) {
    try { return new URL(rel, base).href; } catch { return rel; }
};

// dr_py 宿主内置的简易拼接（python 版 urljoin2：路径直接相接，绝对 url 原样返回）
globalThis.urljoin2 = function (base, rel) {
    rel = rel || '';
    if (/^https?:\/\//.test(rel)) return rel;
    try { return new URL(rel, base).href; } catch { return (base || '').replace(/\/$/, '') + '/' + rel; }
};

// dr_py 宿主内置：URL 清洗（去掉 query 和 hash）
globalThis.urlDeal = function (url) {
    url = String(url || '').trim();
    return url.split('#')[0].split('?')[0];
};

globalThis.gup = function (url, key) {
    try { return new URL(url).searchParams.get(key) || ''; } catch { return ''; }
};

// cheerio 版 pdfh/pdfa（猫影视选择器子集：body&&.class&&a&&href/Text）
globalThis.pdfa = function (html, parse) {
    try {
        const $ = cheerio.load(typeof html === 'string' ? html : html.html ? html.html() : String(html));
        const parts = parse.split('&&');
        const last = parts.pop();
        let sel = '';
        for (const p of parts) sel += (sel ? ' ' : '') + p;
        const m = last.match(/^(.*?)(?:[:,]\s*(\w+))?$/);
        let target = 'text', tagSel = last;
        if (/^(Text|text|html|Html)$/.test(last)) { target = last.toLowerCase(); tagSel = ''; }
        else if (m && m[2] && /^(text|html)$/i.test(m[2])) { target = m[2].toLowerCase(); tagSel = m[1]; }
        else if (parts.length && last) { tagSel = last; target = null; }
        // 目标若为属性名（href/src/...）
        let out = [];
        $(sel || 'body').find(tagSel || '*').add(sel ? $(sel).filter(tagSel || '*') : $(tagSel)).each((i, el) => {
            out.push($.html(el));
        });
        if (!out.length && tagSel) {
            $(sel + ' ' + tagSel).each((i, el) => out.push($.html(el)));
        }
        return out;
    } catch (e) { log('pdfa error', e.message); return []; }
};

globalThis.pdfh = function (html, parse) {
    try {
        const $ = cheerio.load(typeof html === 'string' ? html : String(html));
        const parts = parse.split('&&');
        let target = 'text';
        let last = parts.pop();
        if (/^(Text|text)$/.test(last)) { target = 'text'; last = null; }
        else if (/^(html|Html)$/.test(last)) { target = 'html'; last = null; }
        else if (parts.length && /^(href|src|style|content|value|data-[a-z-]+|alt|title)$/i.test(last)) {
            target = last; last = null;
        }
        let sel = parts.map(p => p).join(' ');
        let el = last ? $(sel).find(last).first() : $(sel).first();
        if (!el.length && last) el = $(sel + ' ' + last).first();
        if (!el.length) el = $(sel).first();
        if (!el.length) return '';
        if (target === 'text') return el.text().trim();
        if (target === 'html') return el.html() || '';
        return el.attr(target) || '';
    } catch (e) { log('pdfh error', e.message); return ''; }
};

globalThis.pd = function (html, parse, uri) {
    let ret = pdfh(html, parse);
    if (/^https?:/.test(ret)) return ret;
    return urljoin(uri || MY_URL || '', ret);
};

// drpy 依赖的 Python 风格 String 扩展
if (!String.prototype.rstrip) {
    String.prototype.rstrip = function (chars) {
        let s = this.toString(), i = s.length;
        if (!chars) chars = /\s/;
        while (i > 0 && (chars instanceof RegExp ? chars.test(s[i-1]) : chars.includes(s[i-1]))) i--;
        return s.slice(0, i);
    };
    String.prototype.lstrip = function (chars) {
        let s = this.toString(), i = 0;
        if (!chars) chars = /\s/;
        while (i < s.length && (chars instanceof RegExp ? chars.test(s[i]) : chars.includes(s[i]))) i++;
        return s.slice(i);
    };
    String.prototype.strip = function (chars) { return this.lstrip(chars).rstrip(chars); };
}

// ---------- 预处理：内联 import / 降级 ESM ----------
function loadClean(p, isModule) {
    let src = fs.readFileSync(p, 'utf-8');
    // ES module 关键字降级为普通脚本
    src = src.replace(/^\s*export\s+function\s+/gm, 'function ')
             .replace(/^\s*export\s+(const|let|var)\s+/gm, '$1 ')
             .replace(/^\s*import\s+[^;]+;?\s*$/gm, '');
    // export{a as x, b as y};  →  globalThis.__mod_x = {x:a, y:b}
    src = src.replace(/export\s*\{([^}]+)\}\s*;?/g, (_, names) => {
        const pairs = names.split(',').map(s => s.trim()).filter(Boolean)
            .map(pair => {
                const m = pair.match(/^(\S+)(?:\s+as\s+(\S+))?$/);
                return m ? `${m[2] || m[1]}:${m[1]}` : null;
            }).filter(Boolean).join(',');
        return `globalThis.__CHEERIO_MOD__={${pairs}};`;
    });
    return src;
}

const utilJs = loadClean(path.join(runtimeDir, 'util.js'));
const cheerioJs = loadClean(path.join(runtimeDir, 'cheerio.min.js'));
const cryptoJs = loadClean(path.join(runtimeDir, 'crypto-js.js'));
const drpyJs = loadClean(drpyPath);
const extJs = loadClean(extPath);

// cheerio/crypto 是 UMD，会把 this 指向 module → 给个干净的 this
globalThis.window = globalThis;
globalThis.assets = { // 少数 js 直接调用 assets()
    get: () => { throw new Error('assets not supported'); },
};

// 站点 js 重新声明 rule 会与 drpy.js 冲突 → 改为赋值（var rule 已被 drpy 提升）
const extClean = extJs.replace(/^(var|let|const)\s+rule\s*=/m, 'rule =');
// drpy 的 let muban 与 eval 内容里的 var muban 冲突 → 改 var
const drpyClean = drpyJs.replace(/let\s+muban\s*=\s*eval\(globalThis\.mubanJs\)/,
                                  'var muban = eval(globalThis.mubanJs)');
// cheerio/crypto/util 各自独立作用域；drpy + 站点 js 必须同域（共享 rule 变量）
const combined = [
    '(function(){', utilJs, '})();',
    '(function(){', cheerioJs, '})();',
    '(function(){', cryptoJs, '})();',
    'var cheerio = globalThis.__CHEERIO_MOD__ && globalThis.__CHEERIO_MOD__.default || globalThis.cheerio;',
    '(function(){', drpyClean, extClean,
    '\n;__SPIDER__ = (typeof __JS_SPIDER__ !== "undefined") ? __JS_SPIDER__ : null;',
    '})();',
].join('\n');

let __SPIDER__ = null;
try {
    __SPIDER__ = (function () {
        // 非 strict：让爬虫代码里未声明的赋值落到 globalThis
        const module = { exports: {} };  // UMD 探测用
        eval(combined);
        return globalThis.__JS_SPIDER__ || null;
    })();
} catch (e) {
    console.log(JSON.stringify({ id: 0, ok: false, error: 'load: ' + e.message }));
    process.exit(1);
}

if (!__SPIDER__) {
    console.log(JSON.stringify({ id: 0, ok: false, error: 'no __JS_SPIDER__ after load' }));
    process.exit(1);
}

// ---------- stdio JSON-RPC 循环 ----------
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });

function respond(obj) {
    process.stdout.write(JSON.stringify(obj) + '\n');
}

rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    const { id, method, args = [] } = msg;
    try {
        const fn = __SPIDER__[method];
        if (!fn) throw new Error('no method: ' + method);
        const result = fn(...args);
        const out = (result && typeof result.then === 'function')
            ? result.then(r => respond({ id, ok: true, result: r }),
                          e => respond({ id, ok: false, error: String(e && e.message || e) }))
            : respond({ id, ok: true, result });
    } catch (e) {
        if (e && e.stack) log('rpc error stack:\n' + e.stack);
        respond({ id, ok: false, error: String(e && e.message || e) });
    }
});

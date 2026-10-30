/* tvbox2exe — TVBox core replicated as a native Windows EXE.
 * C11 + Win32 + libmpv. Loads a TVBox interface config (sites with type 0/1),
 * browses catalogs, searches, and plays via mpv. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mpv/client.h"
#include "http.h"
#include "tvbox.h"

#pragma comment(lib, "comctl32.lib")

/* Default interface config — replace with your own TVBox config URL,
 * or drop a local tvbox.json next to the exe. */
#define DEFAULT_CONFIG_URL "https://ghfast.top/https://raw.githubusercontent.com/" \
                           "jadehh/TVSpider/main/js/配置.json"

#define IDC_LIST_SITES  1001
#define IDC_LIST_MAIN   1002
#define IDC_EDIT_SEARCH 1003
#define IDC_BTN_SEARCH  1004
#define IDC_BTN_BACK    1005
#define IDC_VIDEO       1006

typedef enum { ST_SITES, ST_CLASSES, ST_VIDEOS, ST_EPISODES } State;

static HWND g_hwnd, g_lb_sites, g_main, g_edit, g_video;
static mpv_handle *g_mpv;
static SiteList g_sites;
static VodList g_items;        /* classes / videos / episodes */
static int g_site = -1;        /* current site index */
static char g_class_id[64];    /* selected class */
static char g_vod_id[64];      /* selected video */
static State g_state = ST_SITES;
static int g_playing = 0;

/* ---------- helpers ---------- */

static wchar_t *u8w(const char *s)
{
    if (!s) return NULL;
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    wchar_t *w = malloc(n * sizeof(wchar_t));
    MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n);
    return w;
}

static char *wu8(const wchar_t *w)
{
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    char *s = malloc(n);
    WideCharToMultiByte(CP_UTF8, 0, w, -1, s, n, NULL, NULL);
    return s;
}

static void set_status(const char *msg)
{
    wchar_t *w = u8w(msg);
    SetWindowTextW(g_hwnd, w);
    free(w);
}

static char *exe_dir_file(const char *name)
{
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char *slash = strrchr(path, '\\');
    if (slash) *slash = 0;
    char *out = malloc(MAX_PATH * 2);
    snprintf(out, MAX_PATH * 2, "%s\\%s", path, name);
    return out;
}

static char *url_encode(const char *s)
{
    static const char hex[] = "0123456789ABCDEF";
    size_t n = strlen(s);
    char *out = malloc(n * 3 + 1), *o = out;
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || strchr("-_.~", c))
            *o++ = c;
        else {
            *o++ = '%'; *o++ = hex[c >> 4]; *o++ = hex[c & 15];
        }
    }
    *o = 0;
    return out;
}

static void main_list_reset(void)
{
    tv_vodlist_free(&g_items);
    SendMessageW(g_main, LB_RESETCONTENT, 0, 0);
}

static void main_list_add(const char *name)
{
    wchar_t *w = u8w(name);
    SendMessageW(g_main, LB_ADDSTRING, 0, (LPARAM)w);
    free(w);
}

/* ---------- config ---------- */

static int load_config(void)
{
    char *cfgpath = exe_dir_file("tvbox.json");
    char *text = NULL;
    HANDLE f = CreateFileA(cfgpath, GENERIC_READ, FILE_SHARE_READ, NULL,
                           OPEN_EXISTING, 0, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD size = GetFileSize(f, NULL), read = 0;
        text = malloc(size + 1);
        ReadFile(f, text, size, &read, NULL);
        text[read] = 0;
        CloseHandle(f);
    } else {
        set_status("正在下载接口配置...");
        text = http_get(DEFAULT_CONFIG_URL);
        if (text) { /* cache it */ 
            HANDLE nf = CreateFileA(cfgpath, GENERIC_WRITE, 0, NULL,
                                    CREATE_ALWAYS, 0, NULL);
            if (nf != INVALID_HANDLE_VALUE) {
                DWORD w = 0; WriteFile(nf, text, (DWORD)strlen(text), &w, NULL);
                CloseHandle(nf);
            }
        }
    }
    free(cfgpath);
    if (!text) return 0;
    int ok = tv_sites_parse(&g_sites, text);
    free(text);
    return ok;
}

/* ---------- navigation / actions ---------- */

static void goto_sites(void)
{
    g_state = ST_SITES;
    main_list_reset();
    SendMessageW(g_lb_sites, LB_SETCURSEL, g_site, 0);
    set_status("选择一个源 (双击左侧站点)");
}

static void load_classes(void)
{
    char q[128];
    snprintf(q, sizeof q, "ac=class");
    char *url = tv_site_url(&g_sites.items[g_site], q);
    set_status("加载分类...");
    char *body = http_get(url);
    free(url);
    main_list_reset();
    if (body && tv_classes_parse(&g_items, body) > 0) {
        for (int i = 0; i < g_items.count; i++) main_list_add(g_items.items[i].name);
        g_state = ST_CLASSES;
        set_status("选择分类");
    } else set_status("加载分类失败");
    free(body);
}

static void load_videos(const char *query)
{
    char *url = tv_site_url(&g_sites.items[g_site], query);
    set_status("加载列表...");
    char *body = http_get(url);
    free(url);
    main_list_reset();
    if (body && tv_vods_parse(&g_items, body) > 0) {
        for (int i = 0; i < g_items.count; i++) main_list_add(g_items.items[i].name);
        g_state = ST_VIDEOS;
        set_status("双击影片查看剧集");
    } else set_status("无结果");
    free(body);
}

static void load_episodes(const char *vod_id)
{
    char q[96];
    snprintf(q, sizeof q, "ac=detail&ids=%s", vod_id);
    char *url = tv_site_url(&g_sites.items[g_site], q);
    set_status("加载详情...");
    char *body = http_get(url);
    free(url);
    main_list_reset();
    if (body && tv_detail_parse(body, NULL, &g_items) > 0) {
        for (int i = 0; i < g_items.count; i++) main_list_add(g_items.items[i].name);
        snprintf(g_vod_id, sizeof g_vod_id, "%s", vod_id);
        g_state = ST_EPISODES;
        set_status("双击剧集播放");
    } else set_status("无剧集");
    free(body);
}

static void play(const char *play_url)
{
    if (!g_mpv) return;
    wchar_t *w = u8w(play_url);
    const char *cmd[] = {"loadfile", play_url, NULL};
    mpv_command_async(g_mpv, 0, cmd);
    set_status("正在播放");
    g_playing = 1;
    ShowWindow(g_video, SW_SHOW);
    InvalidateRect(g_hwnd, NULL, TRUE);
    (void)w;
}

static void stop_play(void)
{
    if (g_mpv && g_playing) {
        const char *cmd[] = {"stop", NULL};
        mpv_command_async(g_mpv, 0, cmd);
        g_playing = 0;
    }
    ShowWindow(g_video, SW_HIDE);
}

static void go_back(void)
{
    switch (g_state) {
    case ST_EPISODES:
        if (g_playing) { stop_play(); load_episodes(g_vod_id); }
        else load_classes();
        break;
    case ST_VIDEOS: load_classes(); break;
    case ST_CLASSES: goto_sites(); break;
    default: break;
    }
}

static void do_search(void)
{
    int len = GetWindowTextLengthW(g_edit);
    if (len <= 0) return;
    wchar_t *wb = malloc((len + 1) * sizeof(wchar_t));
    GetWindowTextW(g_edit, wb, len + 1);
    char *kw = wu8(wb);
    free(wb);
    char *enc = url_encode(kw);
    free(kw);
    char q[1024];
    snprintf(q, sizeof q, "ac=detail&wd=%s", enc);
    free(enc);
    stop_play();
    load_videos(q);
}

/* ---------- WndProc ---------- */

static void on_main_dclick(void)
{
    int sel = (int)SendMessageW(g_main, LB_GETCURSEL, 0, 0);
    if (sel < 0 || sel >= g_items.count) return;
    switch (g_state) {
    case ST_CLASSES:
        snprintf(g_class_id, sizeof g_class_id, "%s", g_items.items[sel].id);
        {
            char q[160];
            snprintf(q, sizeof q, "ac=detail&t=%s", g_class_id);
            load_videos(q);
        }
        break;
    case ST_VIDEOS:
        load_episodes(g_items.items[sel].id);
        break;
    case ST_EPISODES:
        play(g_items.items[sel].id);
        break;
    default: break;
    }
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_CREATE: {
        CreateWindowW(L"BUTTON", L"返回", WS_CHILD | WS_VISIBLE,
            8, 6, 64, 26, hwnd, (HMENU)IDC_BTN_BACK, NULL, NULL);
        CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_LEFT,
            80, 8, 220, 24, hwnd, (HMENU)IDC_EDIT_SEARCH, NULL, NULL);
        CreateWindowW(L"BUTTON", L"搜索", WS_CHILD | WS_VISIBLE,
            308, 6, 64, 26, hwnd, (HMENU)IDC_BTN_SEARCH, NULL, NULL);
        g_lb_sites = CreateWindowW(L"LISTBOX", L"",
            WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_BORDER | LBS_NOTIFY,
            0, 40, 220, 100, hwnd, (HMENU)IDC_LIST_SITES, NULL, NULL);
        g_main = CreateWindowW(L"LISTBOX", L"",
            WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_BORDER | LBS_NOTIFY,
            224, 40, 300, 100, hwnd, (HMENU)IDC_LIST_MAIN, NULL, NULL);
        g_video = CreateWindowW(L"STATIC", L"", WS_CHILD | WS_CLIPSIBLINGS,
            0, 40, 100, 100, hwnd, (HMENU)IDC_VIDEO, NULL, NULL);
        return 0;
    }
    case WM_SIZE: {
        int w = LOWORD(lp), h = HIWORD(lp);
        if (!w || !h) return 0;
        MoveWindow(g_lb_sites, 0, 40, 220, h - 40, TRUE);
        MoveWindow(g_main, 224, 40, w - 224, h - 40, TRUE);
        MoveWindow(g_video, 224, 40, w - 224, h - 40, TRUE);
        return 0;
    }
    case WM_COMMAND: {
        int id = LOWORD(wp), code = HIWORD(wp);
        if (id == IDC_BTN_SEARCH) do_search();
        else if (id == IDC_BTN_BACK) go_back();
        else if (id == IDC_LIST_SITES && code == LBN_DBLCLK) {
            int sel = (int)SendMessageW(g_lb_sites, LB_GETCURSEL, 0, 0);
            if (sel >= 0 && sel < g_sites.count) {
                g_site = sel;
                stop_play();
                load_classes();
            }
        }
        else if (id == IDC_LIST_MAIN && code == LBN_DBLCLK) on_main_dclick();
        return 0;
    }
    case WM_GETMINMAXINFO: {
        MINMAXINFO *mmi = (MINMAXINFO *)lp;
        mmi->ptMinTrackSize.x = 640; mmi->ptMinTrackSize.y = 420;
        return 0;
    }
    case WM_DESTROY:
        if (g_mpv) { mpv_terminate_destroy(g_mpv); g_mpv = NULL; }
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

/* ---------- mpv ---------- */

static int mpv_init(HWND video_hwnd)
{
    g_mpv = mpv_create();
    if (!g_mpv) return 0;
    char wid[32];
    snprintf(wid, sizeof wid, "%lld", (long long)(intptr_t)video_hwnd);
    mpv_set_option_string(g_mpv, "wid", wid);
    mpv_set_option_string(g_mpv, "force-window", "no");
    mpv_set_option_string(g_mpv, "osc", "yes");
    if (mpv_initialize(g_mpv) < 0) { mpv_terminate_destroy(g_mpv); g_mpv = NULL; return 0; }
    return 1;
}

/* ---------- main ---------- */

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE prev, PWSTR cmdline, int show)
{
    (void)prev; (void)cmdline;
    INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_LISTVIEW_CLASSES };
    InitCommonControlsEx(&icc);

    WNDCLASSW wc = {0};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hIcon = LoadIcon(NULL, IDI_APPLICATION);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"tvbox2exe";
    RegisterClassW(&wc);

    g_hwnd = CreateWindowW(wc.lpszClassName, L"TVBox (tvbox2exe)",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 1024, 640,
        NULL, NULL, hInst, NULL);
    ShowWindow(g_hwnd, show);
    UpdateWindow(g_hwnd);

    /* fill site list */
    if (!load_config() || g_sites.count == 0) {
        MessageBoxW(g_hwnd,
            L"接口配置加载失败。\n\n"
            L"请在 exe 同目录放置 tvbox.json（TVBox 接口配置），"
            L"或检查网络后重试。",
            L"TVBox", MB_ICONERROR);
    } else {
        for (int i = 0; i < g_sites.count; i++) {
            wchar_t *w = u8w(g_sites.items[i].name);
            SendMessageW(g_lb_sites, LB_ADDSTRING, 0, (LPARAM)w);
            free(w);
        }
        set_status("双击左侧站点加载");
    }

    mpv_init(g_video);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}

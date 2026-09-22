/* Fixed, relocatable CPython GUI entry point. No shell, child process or CRT. */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0602
#include <windows.h>

#define CAPACITY 32768
static WCHAR executable[CAPACITY], root[CAPACITY], candidate[CAPACITY];
static char marker[4097];
typedef int (__cdecl *PythonMain)(int, wchar_t **);
typedef const char *(__cdecl *PythonVersion)(void);

static int fail(void) {
    MessageBoxW(NULL, L"Prompt Enhancer could not start its packaged runtime. Repair or reinstall the application.",
                L"Prompt Enhancer", MB_OK | MB_ICONERROR);
    return 1;
}

static BOOL no_arguments(void) {
    const WCHAR *text = GetCommandLineW();
    if (!text || !*text) return FALSE;
    if (*text == L'"') {
        ++text;
        while (*text && *text != L'"') ++text;
        if (*text != L'"') return FALSE;
        ++text;
    } else {
        while (*text && *text != L' ' && *text != L'\t') ++text;
    }
    while (*text == L' ' || *text == L'\t') ++text;
    return *text == 0;
}

static BOOL sibling(const WCHAR *name) {
    DWORD length = (DWORD)lstrlenW(root), suffix = (DWORD)lstrlenW(name);
    if (length + suffix + 2 >= CAPACITY) return FALSE;
    lstrcpyW(candidate, root);
    candidate[length] = L'\\';
    lstrcpyW(candidate + length + 1, name);
    return TRUE;
}

static BOOL ordinary_ancestors(void) {
    DWORD length = (DWORD)lstrlenW(root), index;
    /* Only a normal absolute drive path; no UNC/device-path loading. */
    if (length < 3 || root[1] != L':' || root[2] != L'\\') return FALSE;
    lstrcpyW(candidate, root);
    for (index = length; index >= 3; --index) {
        if (index != length && candidate[index] != L'\\') continue;
        WCHAR saved = candidate[index];
        candidate[index] = 0;
        DWORD attributes = GetFileAttributesW(candidate);
        candidate[index] = saved;
        if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)
                || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return FALSE;
    }
    return TRUE;
}

static HANDLE pin_file(const WCHAR *name, DWORD maximum) {
    BY_HANDLE_FILE_INFORMATION info;
    if (!sibling(name)) return INVALID_HANDLE_VALUE;
    HANDLE file = CreateFileW(candidate, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                              FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (file == INVALID_HANDLE_VALUE) return file;
    if (!GetFileInformationByHandle(file, &info)
            || (info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))
            || info.nNumberOfLinks != 1 || info.nFileSizeHigh || !info.nFileSizeLow
            || info.nFileSizeLow > maximum) {
        CloseHandle(file);
        return INVALID_HANDLE_VALUE;
    }
    return file;
}

static BOOL isolated_marker(HANDLE file) {
    DWORD count, start = 0, active = 0, index;
    if (!ReadFile(file, marker, 4097, &count, NULL) || !count || count > 4096) return FALSE;
    for (index = 0; index <= count; ++index) {
        if (index < count && marker[index] != '\n') {
            if (!marker[index] || (unsigned char)marker[index] > 127) return FALSE;
            continue;
        }
        DWORD end = index, cursor;
        while (start < end && (marker[start] == ' ' || marker[start] == '\t' || marker[start] == '\r')) ++start;
        while (end > start && (marker[end-1] == ' ' || marker[end-1] == '\t' || marker[end-1] == '\r')) --end;
        if (start < end && marker[start] != '#') {
            const char *expected = active == 0 ? "python313.zip" : ".";
            if (active >= 2) return FALSE;
            for (cursor = start; cursor < end; ++cursor) {
                if (!*expected || marker[cursor] != *expected++) return FALSE;
            }
            if (*expected) return FALSE;
            ++active;
        }
        start = index + 1;
    }
    return active == 2;
}

void launcher_entry(void) {
    HANDLE pth = INVALID_HANDLE_VALUE, dll_pin = INVALID_HANDLE_VALUE;
    HMODULE python = NULL;
    DLL_DIRECTORY_COOKIE search = NULL;
    int result = 1;
    DWORD length, index;
    if (!no_arguments()) { ExitProcess(2); }
    length = GetModuleFileNameW(NULL, executable, CAPACITY);
    if (!length || length >= CAPACITY) { ExitProcess(fail()); }
    lstrcpyW(root, executable);
    for (index = length; index && root[index] != L'\\'; --index) {}
    if (!index) { ExitProcess(fail()); }
    root[index] = 0;
    if (!ordinary_ancestors()) goto failed;
    pth = pin_file(L"python313._pth", 4096);
    if (pth == INVALID_HANDLE_VALUE || !isolated_marker(pth)) goto failed;
    dll_pin = pin_file(L"python313.dll", 64 * 1024 * 1024);
    if (dll_pin == INVALID_HANDLE_VALUE) goto failed;
    /* Exclude the working directory and PATH from subsequent DLL resolution. */
    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)) goto failed;
    search = AddDllDirectory(root);
    if (!search || !sibling(L"python313.dll")) goto failed;
    python = LoadLibraryExW(candidate, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!python) goto failed;
    PythonMain run = (PythonMain)GetProcAddress(python, "Py_Main");
    PythonVersion version = (PythonVersion)GetProcAddress(python, "Py_GetVersion");
    if (!run || !version) goto failed;
    const char *actual = version(), *expected = "3.13.";
    while (*expected) { if (*actual++ != *expected++) goto failed; }
    DWORD digits = 0;
    while (*actual >= '0' && *actual <= '9' && digits < 3) { ++actual; ++digits; }
    if (!digits || *actual != ' ') goto failed;
#ifdef METRICS_ENTRY
    static wchar_t code[] = L"try:\n from prompt_enhancer.desktop_overlay import desktop_main as entry\nexcept Exception:\n raise SystemExit(70)\nraise SystemExit(entry())";
#else
    static wchar_t code[] = L"try:\n from prompt_enhancer.desktop_overlay import agent_desktop_main as entry\nexcept Exception:\n raise SystemExit(70)\nraise SystemExit(entry())";
#endif
    wchar_t *arguments[] = {executable, L"-I", L"-B", L"-c", code};
    result = run(5, arguments);
    /* Existing entry points already display their own safe failure notice. */
    if (result == 70) result = fail();
    goto cleanup;
failed:
    result = fail();
cleanup:
    /* Py_Main owns one complete initialization/finalization cycle. */
    /* Native/managed background threads may retain CPython pointers even after
       Py_Main finalizes. Process exit, not premature FreeLibrary, owns teardown. */
    if (search) RemoveDllDirectory(search);
    if (dll_pin != INVALID_HANDLE_VALUE) CloseHandle(dll_pin);
    if (pth != INVALID_HANDLE_VALUE) CloseHandle(pth);
    ExitProcess((UINT)result);
}

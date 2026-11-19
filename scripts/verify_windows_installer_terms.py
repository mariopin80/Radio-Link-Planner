"""Exercise consent in the compiled Inno Setup installer on Windows."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

APP_NAME = "PU2PTU - Radio Link Planner"
LANGUAGES = {
    "english": ("I have read and agree", "I do not agree", "Next", "1. Permitted uses"),
    "brazilianportuguese": ("Li e concordo", "Não concordo", "Avançar", "1. Usos permitidos"),
    "spanish": ("He leído y acepto", "No acepto", "Siguiente", "1. Usos permitidos"),
    "french": ("J’ai lu et j’accepte", "Je n’accepte pas", "Suivant", "1. Utilisations autorisées"),
    "german": ("Ich habe die Nutzungsbedingungen gelesen", "Ich akzeptiere", "Weiter", "1. Erlaubte Nutzung"),
}

WM_GETTEXT = 0x000D
BM_CLICK = 0x00F5
SMTO_ABORTIFHUNG = 0x0002
user32 = ctypes.WinDLL("user32", use_last_error=True)
WindowCallback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WindowCallback, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, WindowCallback, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowEnabled.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]


def visible_windows(parent: int | None = None) -> list[int]:
    windows = []

    @WindowCallback
    def collect(window, _):
        if user32.IsWindowVisible(window):
            windows.append(window)
        return True

    if parent is None:
        user32.EnumWindows(collect, 0)
    else:
        user32.EnumChildWindows(parent, collect, 0)
    return windows


def message(window: int, message_id: int, wparam: int = 0, lparam: int = 0) -> bool:
    result = ctypes.c_size_t()
    return bool(user32.SendMessageTimeoutW(
        window, message_id, wparam, lparam, SMTO_ABORTIFHUNG, 1_000, ctypes.byref(result),
    ))


def caption(window: int) -> str:
    buffer = ctypes.create_unicode_buffer(8_192)
    message(window, WM_GETTEXT, len(buffer), ctypes.addressof(buffer))
    return buffer.value.replace("&", "").strip()


def find_license_page(accept_text: str, refuse_text: str, next_text: str):
    deadline = time.monotonic() + 35
    title = ctypes.create_unicode_buffer(256)
    while time.monotonic() < deadline:
        for window in visible_windows():
            user32.GetWindowTextW(window, title, len(title))
            if APP_NAME not in title.value:
                continue
            controls = {caption(child): child for child in visible_windows(window)}
            accept = next((hwnd for text, hwnd in controls.items() if text.startswith(accept_text)), None)
            refuse = next((hwnd for text, hwnd in controls.items() if text.startswith(refuse_text)), None)
            forward = next((hwnd for text, hwnd in controls.items() if text.startswith(next_text)), None)
            if accept and refuse and forward:
                return accept, refuse, forward, controls.keys()
        time.sleep(0.25)
    raise AssertionError(f"The installer did not display the terms and choices for {accept_text!r}.")


def check_interactive(installer: Path, language: str) -> None:
    accept_text, refuse_text, next_text, section = LANGUAGES[language]
    process = subprocess.Popen([str(installer), "/SP-", f"/LANG={language}"])
    try:
        accept, refuse, forward, captions = find_license_page(accept_text, refuse_text, next_text)
        assert any(section in text for text in captions), f"Missing terms in {language}"
        assert not user32.IsWindowEnabled(forward), f"Acceptance was preselected in {language}"
        assert message(accept, BM_CLICK) and user32.IsWindowEnabled(forward), f"Acceptance failed in {language}"
        assert message(refuse, BM_CLICK) and not user32.IsWindowEnabled(forward), f"Refusal failed in {language}"
    finally:
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            process.wait(timeout=15)


def check_clean_install(installer: Path) -> None:
    quiet = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    terms = Path(__file__).resolve().parents[1] / "legal"
    with tempfile.TemporaryDirectory(prefix="rlp-terms-") as temporary:
        destination = Path(temporary) / "install"
        arguments = [str(installer), *quiet, "/SP-", f"/DIR={destination}"]
        denied = subprocess.run(arguments, check=False, timeout=45)
        assert denied.returncode != 0 and not destination.exists(), "Silent install started without consent"
        subprocess.run([*arguments, "/ACCEPTTERMS=1"], check=True, timeout=120)
        try:
            for source in terms.glob("EVALUATION-TERMS.*.txt"):
                assert (destination / "licenses" / source.name).read_bytes() == source.read_bytes()
            assert (destination / "RadioLinkPlanner.exe").is_file()
        finally:
            uninstaller = next(destination.glob("unins*.exe"))
            subprocess.run([str(uninstaller), *quiet], check=True, timeout=120)


if __name__ == "__main__":
    installer = Path(sys.argv[1]).resolve(strict=True)
    for language in LANGUAGES:
        check_interactive(installer, language)
    check_clean_install(installer)
    print("Installer terms, acceptance, refusal and clean installation verified.")

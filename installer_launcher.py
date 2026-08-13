from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk

from sales_control import __version__ as APP_VERSION


APP_NAME = "Vendas PRO"
APP_EXE = "ControleDeVendas.exe"
ROLLBACK_EXE = "ControleDeVendas.rollback.exe"
FAILED_EXE = "ControleDeVendas.failed.exe"
ROLLBACK_STATE = "rollback.json"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VendasPRO"


def bundled_file(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def install_dir() -> Path:
    override = os.getenv("VENDAS_PRO_INSTALL_DIR")
    if override:
        return Path(override)
    return Path(os.getenv("LOCALAPPDATA", Path.home())) / "Programs" / "Vendas PRO"


def data_dir() -> Path:
    override = os.getenv("VENDAS_PRO_DATA_DIR")
    if override:
        return Path(override)
    return Path(os.getenv("LOCALAPPDATA", Path.home())) / "ControleDeVendas"


def run_powershell(script: str):
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def shortcut_paths():
    desktop = Path(os.getenv("USERPROFILE", Path.home())) / "Desktop" / "Vendas PRO.lnk"
    start_menu = Path(os.getenv("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Vendas PRO.lnk"
    return desktop, start_menu


def create_shortcut(shortcut: Path, target: Path):
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    safe_shortcut = str(shortcut).replace("'", "''")
    safe_target = str(target).replace("'", "''")
    script = (
        "$w=New-Object -ComObject WScript.Shell;"
        f"$s=$w.CreateShortcut('{safe_shortcut}');"
        f"$s.TargetPath='{safe_target}';"
        f"$s.WorkingDirectory='{str(target.parent).replace("'", "''")}';"
        f"$s.IconLocation='{safe_target},0';$s.Save()"
    )
    run_powershell(script)


def stop_running_app():
    if os.getenv("VENDAS_PRO_SKIP_STOP"):
        return
    subprocess.run(
        ["taskkill.exe", "/IM", APP_EXE, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(1)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_uninstaller(target_dir: Path, setup_copy: Path):
    if os.getenv("VENDAS_PRO_INSTALL_DIR"):
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, f"{APP_NAME} - Controle de Vendas")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Vendas L de S")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target_dir))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(target_dir / APP_EXE))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{setup_copy}" /UNINSTALL')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def perform_install(progress=None, launch=True):
    source = bundled_file(APP_EXE)
    if not source.exists():
        raise RuntimeError("O instalador não contém o aplicativo.")
    target_dir = install_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
    if progress:
        progress(15, "Fechando a versão anterior...")
    stop_running_app()
    if progress:
        progress(40, "Instalando o aplicativo...")
    destination = target_dir / APP_EXE
    temporary = target_dir / f"{APP_EXE}.novo"
    rollback = target_dir / ROLLBACK_EXE
    rollback_temporary = target_dir / f"{ROLLBACK_EXE}.novo"
    setup_copy = target_dir / "VendasPRO-Instalador.exe"
    had_previous = destination.is_file()
    replaced = False
    previous_hash = None
    try:
        if had_previous:
            previous_hash = file_sha256(destination)
            shutil.copy2(destination, rollback_temporary)
            if file_sha256(rollback_temporary) != previous_hash:
                raise RuntimeError("Não foi possível preservar a versão anterior.")
            os.replace(rollback_temporary, rollback)

        source_hash = file_sha256(source)
        shutil.copy2(source, temporary)
        if file_sha256(temporary) != source_hash:
            raise RuntimeError("A cópia do aplicativo não passou na verificação de integridade.")
        os.replace(temporary, destination)
        replaced = True

        if Path(sys.executable).resolve() != setup_copy.resolve():
            setup_temporary = target_dir / "VendasPRO-Instalador.novo.exe"
            shutil.copy2(sys.executable, setup_temporary)
            os.replace(setup_temporary, setup_copy)
        if progress:
            progress(70, "Criando atalhos...")
        if not os.getenv("VENDAS_PRO_SKIP_SHORTCUTS"):
            for shortcut in shortcut_paths():
                create_shortcut(shortcut, destination)
        register_uninstaller(target_dir, setup_copy)
        if had_previous:
            state = {
                "previous_sha256": previous_hash,
                "installed_sha256": source_hash,
                "installed_version": APP_VERSION,
                "data_directory": str(data_dir()),
            }
            (target_dir / ROLLBACK_STATE).write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception:
        temporary.unlink(missing_ok=True)
        rollback_temporary.unlink(missing_ok=True)
        if had_previous and rollback.is_file() and replaced:
            shutil.copy2(rollback, destination)
        elif not had_previous and replaced:
            destination.unlink(missing_ok=True)
        raise
    if progress:
        progress(100, "Instalação concluída.")
    if launch:
        subprocess.Popen([str(destination)], cwd=target_dir, close_fds=True)
    return destination


def perform_rollback(silent=False, launch=True):
    target_dir = install_dir()
    destination = target_dir / APP_EXE
    rollback = target_dir / ROLLBACK_EXE
    failed = target_dir / FAILED_EXE
    if not rollback.is_file():
        raise RuntimeError("Não há uma versão anterior disponível para recuperação.")
    if not silent and not messagebox.askyesno(
        "Restaurar versão anterior",
        "Deseja substituir a versão atual pela cópia anterior? Seus dados serão preservados.",
    ):
        return False
    stop_running_app()
    current_temporary = target_dir / f"{FAILED_EXE}.novo"
    try:
        if destination.is_file():
            shutil.copy2(destination, current_temporary)
        os.replace(rollback, destination)
        if current_temporary.is_file():
            os.replace(current_temporary, failed)
        (target_dir / ROLLBACK_STATE).unlink(missing_ok=True)
    except Exception:
        if current_temporary.is_file() and not destination.is_file():
            os.replace(current_temporary, destination)
        raise
    if launch:
        subprocess.Popen([str(destination)], cwd=target_dir, close_fds=True)
    return True


def perform_uninstall(silent=False):
    stop_running_app()
    target_dir = install_dir()
    if not silent and not messagebox.askyesno(
        "Desinstalar Vendas PRO",
        "Deseja remover o aplicativo? Seus clientes, produtos e vendas serão preservados.",
    ):
        return False
    if not os.getenv("VENDAS_PRO_SKIP_SHORTCUTS"):
        for shortcut in shortcut_paths():
            shortcut.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
    except OSError:
        pass
    cleanup = target_dir.parent / "remover-vendas-pro.cmd"
    cleanup.write_text(
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 > nul\r\n"
        f'rmdir /s /q "{target_dir}"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii",
    )
    subprocess.Popen(["cmd.exe", "/c", str(cleanup)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


class InstallerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Instalar {APP_NAME}")
        self.geometry("560x330")
        self.resizable(False, False)
        self.configure(bg="#EDF2F7")
        self.eval("tk::PlaceWindow . center")
        header = tk.Frame(self, bg="#10243E", height=105)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="VENDAS PRO", bg="#10243E", fg="white", font=("Segoe UI", 24, "bold")).pack(anchor="w", padx=30, pady=(20, 0))
        tk.Label(header, text=f"Instalador oficial - versão {APP_VERSION}", bg="#10243E", fg="#9CC8E8", font=("Segoe UI", 10)).pack(anchor="w", padx=32)
        body = tk.Frame(self, bg="white", padx=30, pady=24)
        body.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(body, text="Instalar o Controle de Vendas neste computador", bg="white", fg="#10243E", font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(body, text="Os dados existentes serão mantidos durante instalações e atualizações.", bg="white", fg="#68798A", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 18))
        self.status = tk.Label(body, text="Pronto para instalar.", bg="white", fg="#68798A", font=("Segoe UI", 9))
        self.status.pack(anchor="w")
        self.bar = ttk.Progressbar(body, maximum=100, mode="determinate")
        self.bar.pack(fill="x", pady=(6, 16))
        self.install_button = ttk.Button(body, text="INSTALAR", command=self.install)
        self.install_button.pack(side="right")
        ttk.Button(body, text="Cancelar", command=self.destroy).pack(side="right", padx=8)

    def update_progress(self, value, text):
        self.bar["value"] = value
        self.status.config(text=text)
        self.update_idletasks()

    def install(self):
        self.install_button.config(state="disabled")
        try:
            destination = perform_install(self.update_progress, launch=True)
            messagebox.showinfo("Vendas PRO", f"Aplicativo instalado com sucesso em:\n{destination}")
            self.destroy()
        except Exception as exc:
            self.install_button.config(state="normal")
            messagebox.showerror("Falha na instalação", str(exc))


def main():
    parser = argparse.ArgumentParser(add_help=False, prefix_chars="-/")
    parser.add_argument("/UNINSTALL", action="store_true")
    parser.add_argument("/ROLLBACK", action="store_true")
    parser.add_argument("/VERYSILENT", action="store_true")
    parser.add_argument("/NOLAUNCH", action="store_true")
    args, _unknown = parser.parse_known_args()
    if args.ROLLBACK:
        root = tk.Tk()
        root.withdraw()
        try:
            perform_rollback(args.VERYSILENT, launch=not args.NOLAUNCH)
        except Exception as exc:
            if not args.VERYSILENT:
                messagebox.showerror("Recuperação", str(exc))
        root.destroy()
    elif args.UNINSTALL:
        root = tk.Tk()
        root.withdraw()
        perform_uninstall(args.VERYSILENT)
        root.destroy()
    elif args.VERYSILENT:
        perform_install(launch=not args.NOLAUNCH)
    else:
        InstallerWindow().mainloop()


if __name__ == "__main__":
    main()

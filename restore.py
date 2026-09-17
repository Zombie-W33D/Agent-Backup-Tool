#!/usr/bin/env python3
"""
Agent-Backup-Tool: restore a .env from a Hermes agent backup repo.

Provides two interfaces:
  1. tkinter GUI (graphical, mouse-driven)
  2. CLI fallback (terminal-driven)

Both can decrypt a .env.gpg from a backup repo using GPG symmetric
encryption and write the plaintext .env to a target directory.

Usage:
    python3 restore.py gui                  # launch tkinter GUI
    python3 restore.py cli --repo /path    # CLI mode
    python3 restore.py decrypt --gpg-file .env.gpg --out .env --passphrase-file pass.txt
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# GPG helpers
# ---------------------------------------------------------------------------

def gpg_decrypt(gpg_file: Path, out_file: Path, passphrase_file: Path = None,
                passphrase: str = None) -> Path:
    """
    Decrypt a .env.gpg file to a plaintext .env.

    Args:
        gpg_file: Path to the .env.gpg file
        out_file: Where to write the decrypted .env
        passphrase_file: Path to a file containing the passphrase
        passphrase: Passphrase string (alternative to passphrase_file)

    Returns:
        Path to the decrypted file
    """
    # Ensure output directory exists
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["gpg", "--decrypt", "--batch", "--yes", "--output", str(out_file)]

    if passphrase_file:
        cmd.extend(["--passphrase-file", str(passphrase_file)])
    elif passphrase:
        # Use a temporary file for the passphrase
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pass", delete=False)
        tmp.write(passphrase)
        tmp.close()
        cmd.extend(["--passphrase-file", tmp.name])
        tmp_path = tmp.name
    else:
        tmp_path = None

    cmd.append(str(gpg_file))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"GPG decrypt failed: {result.stderr.strip()}")
        return out_file
    finally:
        if passphrase and tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def gpg_encrypt(plain_file: Path, out_file: Path, passphrase_file: Path = None,
                passphrase: str = None) -> Path:
    """Encrypt a plaintext .env to .env.gpg."""
    cmd = ["gpg", "--symmetric", "--batch", "--yes", "--output", str(out_file)]

    if passphrase_file:
        cmd.extend(["--passphrase-file", str(passphrase_file)])
    elif passphrase:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pass", delete=False)
        tmp.write(passphrase)
        tmp.close()
        cmd.extend(["--passphrase-file", tmp.name])
        tmp_path = tmp.name
    else:
        tmp_path = None

    cmd.append(str(plain_file))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"GPG encrypt failed: {result.stderr.strip()}")
        return out_file
    finally:
        if passphrase and tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def find_gpg_file(repo_dir: Path) -> Path:
    """Find .env.gpg in a backup repo."""
    candidates = [
        repo_dir / ".env.gpg",
        repo_dir / "backup" / ".env.gpg",
        repo_dir / "agent-backup" / ".env.gpg",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Search recursively
    for gpg in repo_dir.rglob(".env.gpg"):
        return gpg
    raise FileNotFoundError(f"No .env.gpg found in {repo_dir}")


def find_manifest(repo_dir: Path) -> dict:
    """Find and parse backup-manifest.json."""
    for candidate in [repo_dir / "backup-manifest.json",
                      repo_dir / "manifest.json",
                      repo_dir / "backup" / "backup-manifest.json"]:
        if candidate.exists():
            return json.loads(candidate.read_text())
    # Search
    for mf in repo_dir.rglob("backup-manifest.json"):
        return json.loads(mf.read_text())
    return {}


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def cli_main(args):
    """Run the CLI restore flow."""
    repo = Path(args.repo) if args.repo else None
    gpg_file = Path(args.gpg_file) if args.gpg_file else None
    out_file = Path(args.out) if args.out else None
    passphrase = args.passphrase
    passphrase_file = Path(args.passphrase_file) if args.passphrase_file else None

    # Determine .env.gpg location
    if gpg_file:
        if not gpg_file.exists():
            print(f"ERROR: .env.gpg not found: {gpg_file}", file=sys.stderr)
            sys.exit(1)
    elif repo:
        try:
            gpg_file = find_gpg_file(repo)
            print(f"Found .env.gpg: {gpg_file}")
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: Specify --repo or --gpg-file", file=sys.stderr)
        sys.exit(1)

    # Determine output location
    if out_file:
        out_file = Path(out_file)
    elif repo:
        out_file = repo / ".env"
    else:
        out_file = Path(".env")

    # Determine passphrase
    if not passphrase and not passphrase_file:
        # Try to read from a well-known location
        for pf in [Path.home() / ".backup-passphrase",
                    Path("/tmp/backup_pass.txt"),
                    Path(os.getcwd()) / ".backup-passphrase"]:
            if pf.exists():
                passphrase_file = pf
                print(f"Using passphrase file: {pf}")
                break

    if not passphrase and not passphrase_file:
        print("ERROR: No passphrase provided. Use --passphrase or --passphrase-file.",
              file=sys.stderr)
        print("  Tip: export BACKUP_PASSPHRASE=your_passphrase", file=sys.stderr)
        sys.exit(1)

    # Create temp passphrase file if needed
    tmp_pass = None
    if passphrase and not passphrase_file:
        tmp_pass = tempfile.NamedTemporaryFile(mode="w", suffix=".pass", delete=False)
        tmp_pass.write(passphrase)
        tmp_pass.close()
        passphrase_file = Path(tmp_pass.name)

    try:
        print(f"Decrypting {gpg_file} -> {out_file} ...")
        decrypted = gpg_decrypt(gpg_file, out_file, passphrase_file=passphrase_file)
        print(f"SUCCESS: Decrypted .env written to {decrypted}")
        print(f"  Size: {decrypted.stat().st_size} bytes")
        # Show a sanitized preview (first 3 lines, secrets redacted)
        lines = decrypted.read_text().splitlines()[:5]
        for line in lines:
            if line.startswith("#") or not line.strip():
                print(f"  | {line}")
            else:
                # Truncate secret values
                if "=" in line:
                    key, val = line.split("=", 1)
                    masked = val[:4] + "*" * max(4, len(val) - 4)
                    print(f"  | {key}=******")
    finally:
        if tmp_pass and os.path.exists(tmp_pass.name):
            os.unlink(tmp_pass.name)


# ---------------------------------------------------------------------------
# tkinter GUI
# ---------------------------------------------------------------------------

def gui_main():
    """Launch the tkinter GUI."""
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox, scrolledtext
    except ImportError:
        print("ERROR: tkinter not available. Use CLI mode: python3 restore.py cli --repo /path",
              file=sys.stderr)
        sys.exit(1)

    # Try importing rich for nice console output in CLI tabs
    try:
        from rich.console import Console
        from rich.panel import Panel
        RICH_AVAILABLE = True
    except ImportError:
        RICH_AVAILABLE = False

    class RestoreApp:
        def __init__(self, root):
            self.root = root
            self.root.title("Agent-Backup-Tool — .env Restore")
            self.root.geometry("720x580")
            self.root.minsize(500, 400)

            # Style
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TButton", padding=6)
            style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))

            self._build_ui()

        def _build_ui(self):
            # Header
            header = ttk.Label(self.root, text="Agent-Backup-Tool", style="Header.TLabel")
            header.pack(pady=(12, 4))

            sub = ttk.Label(self.root, text="Decrypt and restore .env from a Hermes agent backup repo",
                            foreground="gray")
            sub.pack(pady=(0, 12))

            # Main frame
            main = ttk.Frame(self.root, padding=12)
            main.pack(fill="both", expand=True)

            # --- Source section ---
            src_frame = ttk.LabelFrame(main, text="Backup Source", padding=10)
            src_frame.pack(fill="x", pady=(0, 8))

            ttk.Label(src_frame, text="Backup repo / .env.gpg path:").grid(
                row=0, column=0, sticky="w", pady=(0, 4))

            self.repo_path = tk.StringVar()
            self.repo_entry = ttk.Entry(src_frame, textvariable=self.repo_path, width=60)
            self.repo_entry.grid(row=1, column=0, sticky="ew", pady=(0, 4))
            src_frame.columnconfigure(0, weight=1)

            ttk.Button(src_frame, text="Browse...", command=self._browse_repo).grid(
                row=1, column=1, padx=(6, 0), sticky="e")

            ttk.Button(src_frame, text="Find .env.gpg", command=self._find_gpg).grid(
                row=2, column=0, columnspan=2, pady=(4, 0), sticky="w")

            # --- Passphrase section ---
            pass_frame = ttk.LabelFrame(main, text="Decryption Passphrase", padding=10)
            pass_frame.pack(fill="x", pady=(0, 8))

            ttk.Label(pass_frame, text="Passphrase source:").grid(
                row=0, column=0, sticky="w", pady=(0, 4))

            self.pass_mode = tk.StringVar(value="file")
            ttk.Radiobutton(pass_frame, text="File", variable=self.pass_mode,
                            value="file", command=self._on_pass_mode).grid(
                                row=1, column=0, sticky="w")
            ttk.Radiobutton(pass_frame, text="Direct entry", variable=self.pass_mode,
                            value="direct", command=self._on_pass_mode).grid(
                                row=1, column=1, padx=(12, 0), sticky="w")

            self.pass_file_path = tk.StringVar()
            self.pass_file_entry = ttk.Entry(pass_frame, textvariable=self.pass_file_path,
                                              width=50, state="readonly")
            self.pass_file_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
            pass_frame.columnconfigure(0, weight=1)

            ttk.Button(pass_frame, text="Browse...", command=self._browse_pass_file,
                       state="normal").grid(row=2, column=2, padx=(6, 0), sticky="e")

            self.pass_direct = tk.StringVar()
            self.pass_direct_entry = ttk.Entry(pass_frame, textvariable=self.pass_direct,
                                               show="*", width=50, state="disabled")
            self.pass_direct_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))

            ttk.Button(pass_frame, text="Browse...", command=self._browse_pass_file_direct,
                       state="disabled").grid(row=3, column=2, padx=(6, 0), sticky="e")

            # --- Output section ---
            out_frame = ttk.LabelFrame(main, text="Output", padding=10)
            out_frame.pack(fill="x", pady=(0, 8))

            ttk.Label(out_frame, text="Restore .env to:").grid(
                row=0, column=0, sticky="w", pady=(0, 4))

            self.out_path = tk.StringVar(value=str(Path.home() / ".hermes" / "profiles" / "aria"))
            self.out_entry = ttk.Entry(out_frame, textvariable=self.out_path, width=60)
            self.out_entry.grid(row=1, column=0, sticky="ew", pady=(0, 4))
            out_frame.columnconfigure(0, weight=1)

            ttk.Button(out_frame, text="Browse...", command=self._browse_out).grid(
                row=1, column=1, padx=(6, 0), sticky="e")

            ttk.Button(out_frame, text="Profile default (aria)",
                       command=self._set_aria_default).grid(
                           row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

            # --- Action buttons ---
            btn_frame = ttk.Frame(main)
            btn_frame.pack(fill="x", pady=(8, 4))

            self.restore_btn = ttk.Button(btn_frame, text="🔓 Restore .env",
                                           command=self._do_restore)
            self.restore_btn.pack(side="left", padx=(0, 8))

            ttk.Button(btn_frame, text="Clear", command=self._clear).pack(side="left")

            # --- Log / output ---
            log_frame = ttk.LabelFrame(main, text="Log", padding=8)
            log_frame.pack(fill="both", expand=True)

            self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled",
                                                       font=("Consolas", 10))
            self.log_text.pack(fill="both", expand=True)

            # Status bar
            self.status_var = tk.StringVar(value="Ready")
            status = ttk.Label(self.root, textvariable=self.status_var,
                               relief="sunken", anchor="w", padding=4)
            status.pack(fill="x", side="bottom")

        def _on_pass_mode(self):
            mode = self.pass_mode.get()
            if mode == "file":
                self.pass_file_entry.config(state="readonly")
                self.pass_direct_entry.config(state="disabled")
            else:
                self.pass_file_entry.config(state="disabled")
                self.pass_direct_entry.config(state="normal")

        def _browse_repo(self):
            path = filedialog.askdirectory(title="Select Backup Repo Directory")
            if path:
                self.repo_path.set(path)

        def _browse_pass_file(self):
            path = filedialog.askopenfilename(title="Select Passphrase File",
                                               filetypes=[("Text files", "*.txt *.pass"), ("All files", "*")])
            if path:
                self.pass_file_path.set(path)

        def _browse_pass_file_direct(self):
            path = filedialog.askopenfilename(title="Select Passphrase File",
                                               filetypes=[("Text files", "*.txt *.pass"), ("All files", "*")])
            if path:
                # For direct mode, we read the file and show its content as the passphrase
                try:
                    content = Path(path).read_text().strip()
                    self.pass_direct.set(content)
                    self.pass_file_path.set(path)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not read passphrase file: {e}")

        def _browse_out(self):
            path = filedialog.askdirectory(title="Select Output Directory")
            if path:
                self.out_path.set(path)

        def _set_aria_default(self):
            self.out_path.set(str(Path.home() / ".hermes" / "profiles" / "aria"))

        def _find_gpg(self):
            repo = self.repo_path.get().strip()
            if not repo:
                messagebox.showwarning("Warning", "Select a backup repo first.")
                return
            try:
                gpg = find_gpg_file(Path(repo))
                self.repo_path.set(str(gpg.parent))
                self._log(f"Found .env.gpg: {gpg}")
                self.status_var.set(f"Found .env.gpg in {gpg.parent}")
            except FileNotFoundError as e:
                messagebox.showerror("Error", str(e))
                self._log(f"ERROR: {e}")

        def _log(self, msg):
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        def _clear(self):
            self.repo_path.set("")
            self.pass_file_path.set("")
            self.pass_direct.set("")
            self.out_path.set(str(Path.home() / ".hermes" / "profiles" / "aria"))
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.config(state="disabled")
            self.status_var.set("Ready")

        def _do_restore(self):
            repo_str = self.repo_path.get().strip()
            pass_mode = self.pass_mode.get()
            out_str = self.out_path.get().strip()

            if not repo_str:
                messagebox.showwarning("Warning", "Please select a backup source.")
                return

            repo = Path(repo_str)
            out_dir = Path(out_str)

            # Determine .env.gpg
            try:
                gpg_file = find_gpg_file(repo)
            except FileNotFoundError as e:
                messagebox.showerror("Error", str(e))
                self._log(f"ERROR: {e}")
                return

            # Determine passphrase
            passphrase = None
            passphrase_file = None

            if pass_mode == "file":
                pf = self.pass_file_path.get().strip()
                if not pf:
                    messagebox.showwarning("Warning", "Select a passphrase file.")
                    return
                if not Path(pf).exists():
                    messagebox.showerror("Error", f"Passphrase file not found: {pf}")
                    return
                passphrase_file = Path(pf)
            else:
                pd = self.pass_direct.get().strip()
                if not pd:
                    messagebox.showwarning("Warning", "Enter a passphrase.")
                    return
                passphrase = pd

            # Ensure output directory exists
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / ".env"

            self.restore_btn.config(state="disabled")
            self._log(f"Decrypting {gpg_file.name} ...")
            self.status_var.set("Decrypting...")

            try:
                # Use a thread to keep GUI responsive
                import threading

                def _restore():
                    try:
                        decrypted = gpg_decrypt(gpg_file, out_file,
                                                passphrase_file=passphrase_file,
                                                passphrase=passphrase)
                        self.root.after(0, lambda: self._restore_success(decrypted))
                    except Exception as e:
                        self.root.after(0, lambda: self._restore_failure(e))

                threading.Thread(target=_restore, daemon=True).start()
            except Exception as e:
                self.restore_btn.config(state="normal")
                messagebox.showerror("Error", f"Failed to start restore: {e}")
                self._log(f"ERROR: {e}")

        def _restore_success(self, decrypted: Path):
            self.restore_btn.config(state="normal")
            size = decrypted.stat().st_size
            self._log(f"✓ SUCCESS: {decrypted} ({size} bytes)")
            self.status_var.set(f"Restored .env ({size} bytes)")

            # Verify
            if decrypted.exists() and decrypted.stat().st_size > 0:
                lines = decrypted.read_text().splitlines()
                key_count = sum(1 for l in lines if l.strip() and not l.startswith("#") and "=" in l)
                self._log(f"  Contains {key_count} configuration keys")
                messagebox.showinfo("Restore Complete",
                                    f".env restored to:\n{decrypted}\n\n"
                                    f"Size: {size} bytes\n"
                                    f"Keys found: {key_count}")
            else:
                messagebox.showwarning("Warning", "Decrypted file is empty or missing.")

        def _restore_failure(self, error: Exception):
            self.restore_btn.config(state="normal")
            self._log(f"✗ FAILED: {error}")
            self.status_var.set("Restore failed")
            messagebox.showerror("Restore Failed", str(error))

    root = tk.Tk()
    app = RestoreApp(root)
    root.mainloop()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agent-Backup-Tool: decrypt and restore .env from a Hermes agent backup repo."
    )
    sub = parser.add_subparsers(dest="mode", help="Interface mode")

    # --- GUI ---
    gui_parser = sub.add_parser("gui", help="Launch tkinter GUI")

    # --- CLI ---
    cli_parser = sub.add_parser("cli", help="Command-line restore")
    cli_parser.add_argument("--repo", "-r", help="Path to backup repo directory")
    cli_parser.add_argument("--gpg-file", "-g", help="Path to .env.gpg file directly")
    cli_parser.add_argument("--out", "-o", help="Output path for decrypted .env "
                            "(default: <repo>/.env or ./env)")
    cli_parser.add_argument("--passphrase", "-p", help="Decryption passphrase string")
    cli_parser.add_argument("--passphrase-file", "-f", help="Path to file containing passphrase")

    args = parser.parse_args()

    if args.mode == "gui" or (not args.mode and sys.stdin.isatty()):
        # Default to GUI if no args and terminal is interactive
        gui_main()
    elif args.mode == "cli":
        cli_main(args)
    elif args.mode is None:
        # No args and non-interactive — show help
        parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

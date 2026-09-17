# Agent-Backup-Tool

A human-facing restore tool for Hermes agent backups.

Decrypts and restores a `.env` file from a backup repo created by the
[Agent-Backup-Skill](https://github.com/Zombie-W33D/Agent-Backup-Skill).

## What it does

- Finds `.env.gpg` in a backup repo (or accepts a direct path)
- Decrypts it with GPG symmetric encryption using a passphrase
- Writes the plaintext `.env` to a target directory
- Optionally verifies the restored file (key count, size)

## Interfaces

### tkinter GUI (default)

```bash
python3 restore.py gui
```

Launches a graphical window where you can:
- Browse for the backup repo directory
- Select a passphrase file or type the passphrase directly
- Choose the output directory (with a one-click "Profile default (aria)" button)
- Click "Restore .env" to decrypt and restore
- See a live log of the operation

### CLI fallback

```bash
# Restore from a backup repo (finds .env.gpg automatically)
python3 restore.py cli --repo /path/to/backup-repo

# Restore from a specific .env.gpg file
python3 restore.py cli --gpg-file .env.gpg --out /target/.env

# With passphrase
python3 restore.py cli --repo /path/to/backup-repo --passphrase "$BACKUP_PASSPHRASE"
python3 restore.py cli --repo /path/to/backup-repo --passphrase-file /path/to/pass.txt

# Environment variable
export BACKUP_PASSPHRASE="your-passphrase"
python3 restore.py cli --repo /path/to/backup-repo
```

## Requirements

- Python 3.11+
- `tkinter` (for GUI mode — usually bundled with Python)
- `gpg` (GnuPG 2.4+)
- `rich` (optional — for nicer CLI output)

## GPG encryption compatibility

The tool decrypts `.env.gpg` files created by `gpg --symmetric --batch --passphrase-file`.
This is the same method used by the Agent-Backup-Skill backup script.

To decrypt a backup's `.env.gpg`:

```bash
gpg --decrypt --batch --yes --passphrase-file pass.txt --output .env .env.gpg
```

## Target directory

By default, the tool restores `.env` to:
- The backup repo directory (CLI mode, when no --out specified)
- ~/.hermes/profiles/aria/ (GUI "Profile default" button)

You can point it at any profile directory.

## Pairing with Agent-Backup-Skill

```
Agent-Backup-Skill (automated)          Agent-Backup-Tool (human)
─────────────────────────────────       ───────────────────────────
Discovers active profile                GUI + CLI for manual restore
encrypts .env with gpg                  decrypts .env.gpg with gpg
commits + pushes to GitHub              restores .env to target profile
for agent use                           for human oversight / recovery
```

The skill is for automated, profile-scoped backups. The tool is for
human-driven recovery — when you need to restore a `.env` from a backup
repo without running the full backup pipeline.

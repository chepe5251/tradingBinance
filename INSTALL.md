# Installation Guide

Step-by-step setup for **Windows**, **macOS**, and **Linux**.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Windows](#windows)
- [macOS](#macos)
- [Linux (Ubuntu / Debian)](#linux-ubuntu--debian)
- [Linux (Arch / Manjaro)](#linux-arch--manjaro)
- [Post-Installation Setup](#post-installation-setup)
- [Verify the Installation](#verify-the-installation)
- [Running the Bot](#running-the-bot)
- [Keeping the Bot Running 24/7](#keeping-the-bot-running-247)
- [Updating](#updating)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Minimum version | Notes |
|-------------|----------------|-------|
| Python | 3.10 | 3.11+ recommended |
| pip | 23+ | Bundled with Python |
| Git | Any | For cloning the repo |
| Binance account | — | Testnet or live Futures account |
| Internet connection | — | Stable connection required |

---

## Windows

### 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest **Python 3.11+** installer.
2. Run the installer.
   - **Check** "Add python.exe to PATH".
   - Click **Install Now**.
3. Verify:

```powershell
python --version
pip --version
```

### 2 — Install Git

1. Go to [git-scm.com](https://git-scm.com/download/win) and download Git for Windows.
2. Run the installer with default options.
3. Verify:

```powershell
git --version
```

### 3 — Clone the Repository

Open **PowerShell** or **Command Prompt**:

```powershell
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance
```

### 4 — Create a Virtual Environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

You should see `(.venv)` at the start of your prompt.

### 5 — Install Dependencies

```powershell
pip install -r requirements.txt
```

### 6 — Configure Environment

```powershell
copy .env.example .env
notepad .env
```

Fill in your Binance API credentials and save.

---

## macOS

### 1 — Install Python

**Option A — Official installer (recommended for beginners)**

Download from [python.org/downloads](https://www.python.org/downloads/macos/) and run the `.pkg` installer.

**Option B — Homebrew**

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.11
```

Verify:

```bash
python3 --version
pip3 --version
```

### 2 — Install Git

Git is included with Xcode Command Line Tools:

```bash
xcode-select --install
```

Or via Homebrew:

```bash
brew install git
```

### 3 — Clone the Repository

```bash
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance
```

### 4 — Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of your prompt.

### 5 — Install Dependencies

```bash
pip install -r requirements.txt
```

### 6 — Configure Environment

```bash
cp .env.example .env
nano .env        # or: open -e .env  (TextEdit)
```

Fill in your Binance API credentials and save.

---

## Linux (Ubuntu / Debian)

### 1 — Install Python and Git

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git -y
```

Verify:

```bash
python3 --version
pip3 --version
git --version
```

> If `python3 --version` returns 3.9 or lower, install a newer version:
> ```bash
> sudo apt install python3.11 python3.11-venv -y
> ```

### 2 — Clone the Repository

```bash
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance
```

### 3 — Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4 — Install Dependencies

```bash
pip install -r requirements.txt
```

### 5 — Configure Environment

```bash
cp .env.example .env
nano .env
```

---

## Linux (Arch / Manjaro)

### 1 — Install Python and Git

```bash
sudo pacman -Syu python python-pip git --noconfirm
```

### 2 — Clone, Virtual Environment, and Install

```bash
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

---

## Post-Installation Setup

### Configure `.env`

Open `.env` in any text editor and fill in the required fields:

```env
# Required — your Binance API credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Recommended for first run — use testnet and paper trading
BINANCE_TESTNET=true
USE_PAPER_TRADING=true
PAPER_START_BALANCE=25
```

### Binance API Key Setup

1. Log in to [Binance](https://www.binance.com) (or [testnet](https://testnet.binancefuture.com) for testing).
2. Go to **Account → API Management**.
3. Create a new API key with **only** these permissions enabled:
   - Enable Futures Trading
   - Read Info
4. **Disable** Spot, Margin, and Withdrawal permissions.
5. Enable **IP restriction** and whitelist your machine's IP.
6. Copy the API Key and Secret into your `.env` file.

### Telegram Alerts (optional)

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts to get your `BOT_TOKEN`.
3. Start a conversation with your new bot.
4. Get your `CHAT_ID` by messaging **@userinfobot**.
5. Add both values to `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=987654321
```

---

## Verify the Installation

Run the test script to confirm the API connection and minimum order placement work correctly:

```bash
# Make sure the virtual environment is active
python test_trade.py
```

Expected output: no exceptions, a test order placed and immediately cancelled on testnet.

---

## Running the Bot

```bash
# Activate the virtual environment (if not already active)
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Start
python main.py
```

Logs appear in the console and in `logs/trades.log`.

To stop: press `Ctrl+C`.

---

## Keeping the Bot Running 24/7

### Linux — systemd service

Create the service file:

```bash
sudo nano /etc/systemd/system/tradingbot.service
```

Paste (adjust paths to match your installation):

```ini
[Unit]
Description=Binance Futures Scalping Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/tradingBinance
ExecStart=/home/YOUR_USER/tradingBinance/.venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tradingbot
sudo systemctl start tradingbot

# Check status
sudo systemctl status tradingbot

# View live logs
sudo journalctl -u tradingbot -f
```

### Linux / macOS — tmux (simple alternative)

```bash
# Install tmux if needed
# Ubuntu: sudo apt install tmux
# macOS:  brew install tmux

tmux new -s bot
source .venv/bin/activate
python main.py

# Detach: Ctrl+B then D
# Reattach later: tmux attach -t bot
```

### Windows — Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task**.
2. Set trigger to **At startup**.
3. Action: **Start a program**.
   - Program: `C:\path\to\tradingBinance\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\path\to\tradingBinance`
4. Check **Run whether user is logged on or not**.

---

## Updating

```bash
# Pull latest changes
git pull origin main

# Re-install dependencies if requirements.txt changed
pip install -r requirements.txt

# Restart the bot
```

If using systemd:

```bash
sudo systemctl restart tradingbot
```

---

## Uninstalling

```bash
# Remove the project directory
# Windows (PowerShell):
Remove-Item -Recurse -Force tradingBinance

# macOS / Linux:
rm -rf tradingBinance
```

If you created a systemd service:

```bash
sudo systemctl stop tradingbot
sudo systemctl disable tradingbot
sudo rm /etc/systemd/system/tradingbot.service
sudo systemctl daemon-reload
```

---

## Troubleshooting

### `python: command not found`

- **Windows**: re-run the Python installer and check "Add to PATH".
- **macOS / Linux**: use `python3` instead of `python`.

### `ModuleNotFoundError`

The virtual environment is not active or dependencies were not installed.

```bash
# Activate venv, then reinstall
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### `APIError: -2015` (Invalid API key)

- Confirm `BINANCE_API_KEY` and `BINANCE_API_SECRET` in `.env` have no extra spaces.
- Verify the key has Futures trading permission enabled.
- If `BINANCE_TESTNET=true`, confirm the key was generated on the **testnet** site.

### `RuntimeError: Missing BINANCE_API_KEY`

Your `.env` file is missing or in the wrong directory. It must be in the same folder as `main.py`.

```bash
ls -la .env       # Should exist
cp .env.example .env
nano .env
```

### WebSocket keeps restarting

- Verify your internet connection is stable.
- The bot handles transient disconnections automatically — warnings in the log are normal.
- Persistent failures may indicate Binance WebSocket maintenance; check [status.binance.com](https://status.binance.com).

### Telegram alerts not arriving

- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in `.env`.
- Send `/start` to your bot in Telegram before the first run.
- Check that the bot is not blocked in Telegram.

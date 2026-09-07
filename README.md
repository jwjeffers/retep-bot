# 🤖 Retep — Discord Chat Bot

Retep is a Discord bot that absorbs the personality, slang, and chat mannerisms of your server's message history. It uses a **Markov chain** text generator (not an LLM) to produce messages that sound like a blend of everyone in the server — chaotic, authentic, and occasionally brilliant.

## Features

### 💬 Text Generation
- **Order-3 Markov chain** with order-2 fallback for coherent text
- **Best-of-20 candidate selection** with quality scoring (natural endings, length, variety)
- **Context-aware seeding** — when asked a question, Retep finds relevant starting points using bigram matching and keyword relevance scoring
- **Multi-sentence responses** — bell curve distribution: usually 1 sentence, sometimes 2, rarely 3
- **Verbatim copy detection** — never reproduces an exact message from chat history
- **Logarithmic recency weighting** — recent messages get up to +15% more influence, oldest get -15%

### 📅 Scheduled Messages
- **1 unprompted message per day** (configurable) during active hours
- **Time-of-day awareness** — auto-detects when the server is most active from chat history
- **Bell-curve scheduling** — messages cluster around peak activity hours
- **Reply threading** — 40% chance to reply to a recent message instead of posting standalone
- **Pride month** — 20% chance in June to send pride month messages

### 😎 Reactions & Engagement
- **Emoji reactions** — ~8% chance to react to messages with server-appropriate emoji
- **Bell-curve emoji count** — usually 1 reaction, sometimes 2-3
- **Frequency-weighted emoji pool** — uses emoji that the server actually uses, weighted by popularity
- **GIF posting** — 0.5% chance to post a random GIF from chat history (last year only)
- **Reaction feedback loop** — when users react to Retep's messages, those messages get boosted in the Markov chain, shaping future responses

### 🎮 Commands

| Command | Description |
|---|---|
| `/ask <question>` | Ask Retep a question — responds using context-aware Markov generation |
| `/teams <players>` | Split players into two 5v5 League of Legends teams with random roles and Markov-generated team names |
| `/readlist add\|remove\|show` | Manage which channels Retep learns from (admin only) |
| `/chatlist add\|remove\|show` | Manage which channels Retep can speak in (admin only) |
| `/sync` | Manually trigger chat history sync and Markov chain rebuild (admin only) |
| `/retep` | Show bot status: read/chat channels, message count, and today's schedule |

### 🔄 Sync & Data
- **Startup sync** — fetches latest 1,000 messages per read channel on boot
- **Midnight auto-sync** — nightly full sync up to configured history depth
- **Live ingestion** — new messages are stored in real-time as they're posted
- **Bot filtering** — ignores its own messages, other bots, and users with the "Jarvis" role
- **Punctuation normalization** — ensures consistent sentence endings in training data

## Architecture

```
retep-bot/
├── bot.py                  # Entry point — loads cogs, initializes DB
├── cogs/
│   ├── admin.py            # /readlist, /chatlist, /retep, /sync commands
│   ├── chat.py             # @mention replies, /ask, /teams
│   ├── random_talk.py      # Scheduled messages, emoji reactions, GIF posting
│   └── sync.py             # Message/reaction history ingestion
├── core/
│   ├── config.py           # Environment config loader
│   ├── database.py         # SQLite storage (messages, channels, boosts, emoji)
│   ├── markov.py           # Markov chain engine with recency weighting
│   └── scheduler.py        # Bell-curve daily message scheduler
├── .env.example            # Environment variable template
├── requirements.txt        # Python dependencies
├── setup_server.sh         # Oracle Cloud / Linux deployment script
├── start_bot.bat           # Windows startup script
└── start_bot.vbs           # Windows silent launcher
```

## Setup

### Prerequisites
- Python 3.9+
- A Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))

### Installation

```bash
git clone https://github.com/jwjeffers/retep-bot.git
cd retep-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required:
- `DISCORD_TOKEN` — your bot's token

Optional:
- `BOT_NAME` — bot personality name (default: `Retep`)
- `MESSAGES_PER_DAY` — unprompted messages per day (default: `1`)
- `ACTIVE_HOURS_START` / `ACTIVE_HOURS_END` — fallback active hours (default: `10`-`23`)
- `HISTORY_DEPTH` — max messages per channel during full sync (default: `10000`)
- `DB_PATH` — database file path (default: `retep.db`)

### Running

```bash
python bot.py
```

### First-Time Setup

1. Invite the bot to your server with `applications.commands` and `bot` scopes
2. Use `/readlist add` to tell Retep which channels to learn from
3. Use `/chatlist add` to tell Retep which channels it can speak in
4. Use `/sync` to import chat history and build the Markov chain
5. Retep will start posting and responding!

## Deployment (Oracle Cloud Free Tier)

For 24/7 hosting without keeping your PC on, run the setup script on an Oracle Cloud VM:

```bash
curl -O https://raw.githubusercontent.com/jwjeffers/retep-bot/main/setup_server.sh
bash setup_server.sh
```

This installs dependencies, clones the repo, and sets up a systemd service with auto-restart. See the script for details.

## License

MIT

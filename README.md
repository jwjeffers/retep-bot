# 🤖 Retep — Discord Markov Chain Personality Bot

Retep is a Discord bot that learns from your server's chat history and generates messages that sound like your community. It uses an order-3 Markov chain with intelligent scoring to create coherent, funny, and eerily familiar messages.

## Features

### 💬 Chat Generation
- **Markov chain** built from your server's message history (order-3 with order-2 fallback)
- **Best-of-20 candidate selection** with scoring for natural sentence endings
- **Verbatim copy detection** — never parrots back an exact message from history
- **Incomplete ending penalty** — avoids cutting off mid-sentence
- **Capitalization fix** and **leading conjunction stripping** for cleaner output
- **Seed matching** — `/ask` responses are contextually relevant to the question

### 📅 Scheduled Messages
- **3 random messages per day** (configurable)
- **Bell curve timing** centered on your server's active hours (auto-detected)
- **Bell curve word count** matching your server's actual message length distribution
- **Reply threading** — 40% chance to reply to the last message in the channel

### 😂 Emoji Reactions
- **8% chance** to react to messages in chat channels
- **Frequency-weighted selection** from your server's most-used emoji (last 3 months)
- Tracks both **message text emoji** and **reaction emoji** for accurate weighting

### 🔄 Auto-Sync
- **Midnight sync** — automatically fetches new messages every night
- **Live ingestion** — learns from new messages in real-time
- **Startup sync** — grabs the latest 1,000 messages per channel on boot
- **Reaction tracking** — collects emoji reaction data during sync
- **Punctuation normalization** — adds periods to messages that lack ending punctuation

### 🛡️ Admin Controls
- `/add-read` / `/remove-read` — manage which channels the bot learns from
- `/add-chat` / `/remove-chat` — manage which channels the bot can talk in
- `/channels` — view current channel configuration
- `/sync` — manually trigger a full history sync
- `/ask <question>` — ask the bot a question directly

## Architecture

```
bot.py              # Entry point, cog loader
├── cogs/
│   ├── chat.py         # @mention responses, /ask command
│   ├── random_talk.py  # Scheduled messages, emoji reactions, reply threading
│   ├── sync.py         # Message/reaction sync, midnight auto-sync, live ingestion
│   └── admin.py        # Channel config commands
├── core/
│   ├── markov.py       # Order-3 Markov chain with order-2 fallback, scoring, dedup
│   ├── database.py     # SQLite via aiosqlite — messages, reactions, channel config
│   ├── scheduler.py    # Daily message scheduling with bell curve timing
│   ├── config.py       # Environment variable loader
│   ├── personality.py  # Personality system (legacy, from LLM mode)
│   └── llm.py          # OpenAI integration (legacy, replaced by Markov)
└── requirements.txt
```

## Setup

### 1. Create a Discord Bot
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application → Bot tab → create bot
3. Copy the bot token
4. Enable **Message Content Intent** under Privileged Gateway Intents
5. Invite the bot with `manage_guild` permission

### 2. Install
```bash
git clone https://github.com/jwjeffers/retep-bot.git
cd retep-bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your Discord bot token
```

### 3. Run
```bash
python bot.py
```

### 4. Configure Channels
In Discord, use these commands:
```
/add-read #channel-name    # Bot will learn from this channel
/add-chat #channel-name    # Bot will talk in this channel
/sync                      # Fetch message history
```

## How It Works

### Markov Chain
The bot builds a **transition probability table** from chat messages. For every 3-word sequence it sees, it records what word comes next. To generate text:
1. Pick a random sentence starter (first 3 words of a message)
2. Look up the 3-word state in the table → get possible next words
3. Pick a random next word, slide the window forward, repeat
4. If order-3 has no transitions, **fall back to order-2** context
5. Stop at natural sentence endings (punctuation, emoji) with 70% probability

### Scoring System
Each generation produces **20 candidates**. Each is scored:
- **+4** for natural ending (`.!?` or emoji)
- **+3** for Discord-style ending (`lol`, `lmao`, `tbh`, etc.)
- **-5** for incomplete ending (`the`, `a`, `and`, `is`, etc.)
- **+2** for medium length (5-20 words)
- **+1** for unique word ratio (variety)

### DiscordKit Import
You can import chat history from [DiscordKit](https://discordkit.com/) JSON exports for channels the bot doesn't have access to. Place JSON files in the project directory and run the import script.

## Requirements
- Python 3.11+
- discord.py 2.x
- aiosqlite
- python-dotenv
- audioop-lts (for Python 3.13+)

## License
MIT

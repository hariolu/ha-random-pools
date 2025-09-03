# 🎲 Home Assistant Random Pools

Custom integration for Home Assistant that provides **randomized lines 📝 and media 🔊 sensors** from user-defined files and folders.  
Perfect if you want your automations or bots to respond with random phrases, play diverse notification sounds, or give your smart home a playful personality 🐾.

---

## ✨ Features
- 📄 **Lines**: load pools from `.txt` files (one phrase per line).  
- 🎶 **Media**: load pools from folders with any audio/video files (`.mp3`, `.ogg`, `.wav`, …).  
- 🎲 Each pool is exposed as a `sensor` that always provides one entry.  
- 🔄 Shuffle & reload pools on demand, no HA restart needed.  
- 🛡 Safe **fallbacks** (`fallback_text` / `fallback_url`) if a pool is empty.  
- 🚫 **No-repeat** mode with adjustable history (`no_repeat=N`).  
- 📑 **Queue mode**: cycle sequentially instead of random.  
- 🧹 Normalize text (BOM, Unicode, CRLF).  
- 🧩 Autodiscover `.txt` files and media folders if you don’t list them explicitly.  
- 🎛 Filters: `include` / `exclude` glob patterns.  
- 🌐 Flexible URL serving: `serve_from: component | www | media`.  
- 📏 Configurable limits (`max_lines`, `max_chars`).  
- 🛠 Bulk services: `pools.shuffle_all` / `pools.reload_all`.  

---

## 🛠 Example Use Cases
- 🤖 **Random bot replies** — pick a different line for Telegram/Discord.  
- 🗣 **Dynamic TTS** — random greeting before announcing the weather.  
- 🚨 **Sound notifications** — random alert sound when motion is detected.  
- 🚀 **Startup events** — playful phrase or media when HA boots.  
- 🎮 **Game-like UX** — rotate through queues of sounds or text lines.  

---

## 📂 Example Configuration

### Minimal auto-discovery
```yaml
sensor:
  - platform: pools
    lines_directory: www/pools/lines
    media_directory: www/pools/media
    serve_from: www
```
→ creates one sensor per `.txt` file and per media subfolder.

---

### Manual pools
```yaml
sensor:
  - platform: pools
    lines_directory: www/cvbot_mind/text
    lines_pools:
      - file: hello.txt
        name: Hello Lines
        entity_suffix: pools_lines_hello

    media_directory: www/cvbot_mind/media
    media_pools:
      - folder: alerts
        name: Alert Sounds
        entity_suffix: pools_media_alerts

    selection_mode: random    # random | queue
    no_repeat: 3
    fallback_text: "N/A"
    fallback_url: ""
    serve_from: www
    include: ["*.mp3", "*.ogg"]
    exclude: ["*old*.mp3"]
    lines_extensions: [".txt"]
    media_extensions: [".mp3", ".ogg", ".wav", ".flac"]
    max_lines: 512
    max_chars: 512
```

---

## ⚙️ Services
- 🔀 `pools.shuffle` — reshuffle one or more sensors.  
- ♻️ `pools.reload` — reload pools from disk.  
- 🧹 `pools.reset_stats` — clear counters/history.  
- 🔀 `pools.shuffle_all` — reshuffle every pool.  
- ♻️ `pools.reload_all` — reload every pool.  

---

## 📜 License
Released under the **MIT License**.  
Feel free to use, modify, and share — just keep the credit 🌟.

# 🎲 Home Assistant Random Pools

Custom integration for Home Assistant that provides **randomized text 📝 and sound 🔊 sensors** from user-defined folders.  
Perfect if you want your automations or bots to respond with random phrases, play different notification sounds, or give your smart home a playful personality 🐾.

---

## ✨ Features
- 📄 Load text pools from `.txt` files (one phrase per line).  
- 🎶 Load sound pools from folders with audio files (`.mp3`, `.ogg`).  
- 🎲 Each pool is exposed as a `sensor` that always provides one random entry.  
- 🔄 Shuffle & reload without restarting Home Assistant.  
- ⚙️ Safe fallbacks if a pool is empty.  

---

## 🛠 Example Use Cases
- 🤖 **Random bot replies** — send different phrases in Telegram/Discord automations.  
- 🗣 **Dynamic TTS** — pick a random greeting line before announcing the weather.  
- 🚨 **Sound notifications** — choose a random alert sound when motion is detected.  
- 🚀 **Startup events** — play a random "system online" phrase or sound.  

---

## 📂 Example Configuration

### Example 1: Text Pool
Put a file `hello.txt` in `/config/www/pools/text/`:

```
Hello there!
Welcome back home.
Howdy partner 🐾
```

This creates a sensor:  

```
sensor.pools_text_hello
```

→ which randomly returns one of the lines.

---

### Example 2: Sound Pool
Create a folder `/config/www/pools/sounds/woof/` with `.mp3` files.  

This creates a sensor:  

```
sensor.pools_sound_woof
```

→ which returns a random file path, ready for media players.

---

### Example 3: Automation with Telegram

```yaml
alias: Send random hello in Telegram
trigger:
  - platform: event
    event_type: telegram_command
    event_data:
      command: /hello
action:
  - service: telegram_bot.send_message
    data:
      message: "{{ states('sensor.pools_text_hello') }}"
```

---

## ⚙️ Commands
- 🔀 `pools.shuffle` — reshuffle one or more sensors.  
- ♻️ `pools.reload` — reload pools from disk.  

---

## 📜 License
Released under the **MIT License**.  
Feel free to use, modify, and share — just keep the credit 🌟.

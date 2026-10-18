# Kumite

An offline Tekken 8 sparring partner that learns your habits during a set, exploits them at the difficulty you choose, and coaches you out of them with text and voice.

Built at LA Hacks 2026.

| Folder | What | Owner |
|---|---|---|
| `game/` | Memory reader, bot, learning system, brain API | Sahil |
| `app/` | Desktop app: overlay, coach, learning panel, voice | Chloe |
| `replay/` | Replay analysis and coach service | Garrett |
| `analytics/` | Stats, learning metrics, storage, observability | Eric |
| `contracts/` | Shared schemas and API definitions | everyone |
| `characters/` | Per-character move and game-plan data | Garrett |
| `tools/mock/` | Mock services for development without the game | Eric |

Offline modes only. The game is read with read-only memory access; nothing is written to or injected into the game process.

## Credits

Memory layout research informed by Irony (tomislav-ivankovic). Frame data from TekkenDocs (RBNorway) and Wavu Wiki. Laya by Convai Innovations (Apache 2.0). Jev by TypeSafe. River for online learning.

Kazuya combo routes and punishers in `game/combos_kazuya.json` come from Applay's Tekken 8 Library.


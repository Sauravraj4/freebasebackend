# OnlineFF

`onlineff.html` is the multiplayer Three.js game. `server.py` serves the game and its matchmaking, presence, position, and player damage API from one web service. It uses SQLite for temporary match sessions; no records are required to play.

## Run locally

```bash
python server.py
```

Open `http://localhost:8000/`. To play together on a local network, share the host computer's network address and port 8000.

## Deploy on Render

Create a **Web Service** for this GitHub repository and use:

- **Root Directory:** leave blank
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python server.py`

The server binds to Render's `PORT` environment variable and `/` opens the multiplayer game. Share the service's `onrender.com` URL with players. The game synchronizes human positions and player versus player damage; open lobby slots are local browser bots.

SQLite data is temporary on Render's default filesystem and can reset after a restart or redeploy. That is fine for live play because sessions are recreated as players join. Inactive players are removed after 35 seconds. This is a small prototype without accounts or production security hardening.

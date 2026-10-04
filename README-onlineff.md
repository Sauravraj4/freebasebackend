# OnlineFF

`onlineff.html` uses a small Python HTTP server and SQLite database for online matchmaking. No MongoDB or third-party Python packages are needed.

## Start the server

1. Install Python 3 if it is not already installed.
2. Open a terminal in this folder and run `python server.py`.
3. Open `http://localhost:8000/onlineff.html` in your browser.
4. Share the server computer's network address and port `8000` with friends on the same network. For example: `http://192.168.1.20:8000/onlineff.html`.

Each match has 60 slots. Human players share their positions and health; open slots are represented as bots. The server stores player sessions in `onlineff.sqlite3` and removes inactive sessions after 35 seconds.

To let friends join over the public internet, this server must be hosted on an internet accessible machine and served through HTTPS. The included server is a development prototype; it has no account system or production security hardening. Bot AI and bot eliminations currently run locally in each browser, so only human player positions and player versus player damage are synchronized between clients.

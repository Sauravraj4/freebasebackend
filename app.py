from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/save-score", methods=["POST"])
def save_score():
    data = request.get_json(silent=True) or {}
    player_name = str(data.get("name", "Player"))[:40]
    kills = data.get("kills", 0)
    try:
        kills = max(0, int(kills))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Kills must be a whole number."}), 400

    print(f"Received score: {player_name} got {kills} kills")
    return jsonify({"success": True, "message": "Score saved successfully!"})


if __name__ == "__main__":
    app.run(debug=True)

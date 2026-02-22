from flask import Flask
import threading
import os
import time

app = Flask(__name__)


@app.route("/health")
def health():
    return "OK", 200


def run_bot_thread():
    # import locally to avoid circular import at module import time
    try:
        from bot import main as start_bot
    except Exception as e:
        print(f"[HATA] bot import edilemedi: {e}")
        return

    try:
        print("[INFO] Bot thread başlatılıyor...")
        start_bot()
    except Exception as e:
        print(f"[HATA] Bot çalışırken hata: {e}")


if __name__ == "__main__":
    # start the bot in a background thread so the Flask web process can serve health checks
    t = threading.Thread(target=run_bot_thread, daemon=True)
    t.start()

    # keep main process alive and serve health endpoint
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
from flask import Flask, jsonify
import os
import threading

app = Flask(__name__)


@app.route("/")
def index():
    return "OK", 200


@app.route("/health")
def health():
    return jsonify(status="ok"), 200


def _start_bot_thread():
    try:
        import bot

        def _run():
            try:
                bot.main()
            except Exception as e:
                print("[BOT THREAD ERROR]", e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
    except Exception as e:
        print("[ERROR] Failed to import/start bot:", e)


# Start bot background thread when module is imported.
# Render will import this module for the web service; use a single worker.
_start_bot_thread()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import flask
from flask import request
import os
from bot import ImageProcessingBot  # Assuming this is your handler class

app = flask.Flask(__name__)
app.url_map.strict_slashes = False  # Accept /TOKEN and /TOKEN/ the same

# Load config from env
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
BOT_APP_URL = os.environ['BOT_APP_URL']
YOLO_SERVER_URL = os.environ['YOLO_SERVER_URL']

# INIT BOT HERE — before any route
bot = ImageProcessingBot(TELEGRAM_BOT_TOKEN, BOT_APP_URL, yolo_server_url=YOLO_SERVER_URL)

@app.route('/', methods=['GET'])
def index():
    return 'Ok'

@app.route('/health', methods=['GET'])
def health():
    return 'ok', 200

# Route without trailing AND with trailing slash
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
@app.route(f'/{TELEGRAM_BOT_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8443)

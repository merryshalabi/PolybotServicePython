import flask
from flask import request
import os
from bot import ImageProcessingBot  # Assuming this is your handler class

app = flask.Flask(__name__)
app.url_map.strict_slashes = False  # Accept /TOKEN and /TOKEN/ the same

# Load config from env
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
BOT_APP_URL = os.environ['BOT_APP_URL']

# INIT BOT HERE — before any route
bot = ImageProcessingBot(TELEGRAM_BOT_TOKEN, BOT_APP_URL)

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

@app.route('/predictions/<prediction_id>', methods=['POST'])
def receive_prediction(prediction_id):
    data = request.json
    chat_id = data.get("chat_id")
    labels = data.get("labels", [])

    if not chat_id:
        return "Missing chat_id", 400

    # Try to get image number from bot's map
    image_number = None
    if hasattr(bot, "prediction_number_map") and prediction_id in bot.prediction_number_map:
        chat_id, image_number = bot.prediction_number_map[prediction_id]

    if image_number is not None:
        header = f"Detection result for Image {image_number}:"
    else:
        header = f"Detection result:"

    detected_objects = ", ".join(labels) if labels else "Nothing detected"
    bot.send_text(chat_id, f"{header} {detected_objects}")
    return "Received", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)

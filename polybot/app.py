
import flask
from flask import request
import os
from bot import Bot, QuoteBot, ImageProcessingBot

import os


app = flask.Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
BOT_APP_URL = os.environ['BOT_APP_URL']
YOLO_SERVER_URL = os.environ['YOLO_SERVER_URL']


@app.route('/', methods=['GET'])
def index():
    return 'Ok'


@app.route(f'/{TELEGRAM_BOT_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'



if __name__ == "__main__":
   bot = ImageProcessingBot(TELEGRAM_BOT_TOKEN, BOT_APP_URL, yolo_server_url=YOLO_SERVER_URL)
   app.run(host='0.0.0.0', port=8443)

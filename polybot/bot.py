import requests
import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
from polybot.img_proc import Img


class Bot:

    def __init__(self, token, telegram_chat_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)

        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # set the webhook URL
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class QuoteBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        if msg["text"] != 'Please don\'t quote me':
            self.send_text_with_quote(msg['chat']['id'], msg["text"], quoted_msg_id=msg["message_id"])


class ImageProcessingBot(Bot):
    def __init__(self, token, telegram_chat_url,yolo_server_url):
        super().__init__(token, telegram_chat_url)
        self.media_groups = {}
        self.new_users = set()
        self.processed_media_groups = set()
        self.valid_filters = [
            'concat','concat horizontal', 'concat vertical', 'blur', 'contour',
            'rotate', 'segment', 'salt and pepper', 'rotate2',
            'brighten', 'darken', 'invert','detect'
        ]
        self.yolo_server_url = yolo_server_url


    def is_yolo_server_healthy(self):

        if not self.yolo_server_url:
            logger.error("YOLO_SERVER_URL is not set in environment variables.")
            return False

        health_url = f"{self.yolo_server_url}/health"
        try:
            response = requests.get(health_url)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except requests.RequestException:
            return False


    def detect_objects_in_image(self, image_path):
        if not self.yolo_server_url:
            return {"error": "YOLO server URL is not set in environment variables."}

        detect_url = f"{self.yolo_server_url}/predict"

        if not self.is_yolo_server_healthy():
            return {"error": "Yolo server is currently unavailable. Please try again later."}

        with open(image_path, "rb") as image_file:
            response = requests.post(detect_url, files={"file": image_file})
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": "Failed to detect objects in the image"}


    def handle_message(self, msg):
        """Bot Main message handler for image processing"""
        logger.info(f'Incoming message: {msg}')

        try:
            user_id = msg['from']['id']
            if not hasattr(self, 'new_users'):
                self.new_users = set()

            if user_id not in self.new_users:
                self.new_users.add(user_id)
                if 'photo' not in msg:
                    self.send_text(msg['chat']['id'], "Hi! How can I help you?")
                    return

            if 'photo' not in msg:
                self.send_text(msg['chat']['id'], "Please send a photo with a caption to apply a filter")
                return


            caption = msg.get('caption', '')
            caption =  caption.lower()
            media_group_id = msg.get('media_group_id')

            if caption and caption not in self.valid_filters:
                self.send_text(msg['chat']['id'],f"Unknown filter '{caption}'. Please use one of: Blur, Contour, Rotate, Rotate2, Segment, Salt and pepper, Concat, Concat Horizontal, Concat Vertical, Brighten, Darken, Invert, Detect.")
                return

            if caption == "detect":
                path = self.download_user_photo(msg)
                detection_result = self.detect_objects_in_image(path)

                if "error" in detection_result:
                    self.send_text(msg['chat']['id'], detection_result["error"])
                else:
                    detected_objects = ", ".join(detection_result.get("labels", []))
                    self.send_text(msg['chat']['id'], f"Detected objects: {detected_objects}")
                return


            if not caption and not media_group_id:
                self.send_text(msg['chat']['id'], "Please send a filter name as a caption")
                return

            if media_group_id:
                if caption and caption not in ['concat', 'concat horizontal', 'concat vertical']:
                    if media_group_id not in self.media_groups:
                        self.media_groups[media_group_id] = {
                            "caption": caption,
                            "messages": [msg]
                        }
                        self.send_text(msg['chat']['id'], f"The filter '{caption}' does not support multiple images.")
                    else:
                        self.media_groups[media_group_id]["messages"].append(msg)
                    return

                if media_group_id not in self.media_groups:
                    self.media_groups[media_group_id] = {
                        "caption": caption,
                        "messages": [msg]
                    }
                    return

                else:
                    stored_caption = self.media_groups[media_group_id]["caption"]
                    if not stored_caption.startswith('concat'):
                        return

                    if len(self.media_groups[media_group_id]["messages"]) >= 2:
                        self.send_text(msg['chat']['id'], "Only two images are allowed for concat filter")
                        return

                    self.media_groups[media_group_id]["messages"].append(msg)
                    if len(self.media_groups[media_group_id]["messages"]) == 2:
                        data = self.media_groups.pop(media_group_id)
                        msgs = data["messages"]
                        stored_caption = data["caption"]
                        path1 = self.download_user_photo({'photo': [msgs[0]['photo'][-1]], 'chat': msgs[0]['chat']})
                        img1 = Img(path1)
                        path2 = self.download_user_photo({'photo': [msgs[1]['photo'][-1]], 'chat': msgs[1]['chat']})
                        img2 = Img(path2)

                        if stored_caption in ['concat', 'concat horizontal']:
                            img1.concat(img2)
                        else:
                            img1.concat(img2, direction='vertical')

                        new_path = img1.save_img()
                        self.send_photo(msg['chat']['id'], new_path)

                        return

            path = self.download_user_photo(msg)
            img = Img(path)

            if caption == 'blur':
                img.blur()
            elif caption == 'contour':
                img.contour()
            elif caption == 'rotate':
                img.rotate()
            elif caption == 'rotate2':
                img.rotate2()
            elif caption == 'segment':
                img.segment()
            elif caption == 'salt and pepper':
                img.salt_n_pepper()
            elif caption == 'brighten':
                img.brighten()
            elif caption == 'darken':
                img.darken()
            elif caption == 'invert':
                img.invert()
            elif caption.startswith('concat'):
                self.send_text(msg['chat']['id'], "Only two images are allowed for concat filter")
                return


            new_path = img.save_img()
            self.send_photo(msg['chat']['id'], new_path)

        except Exception as e:
            logger.error(f"Error while handling message : {e}")
            self.send_text(msg['chat']['id'], "Something went wrong please try again")

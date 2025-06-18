import json
from datetime import datetime

import requests
import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
from polybot.img_proc import Img
import boto3
from botocore.exceptions import NoCredentialsError
import uuid



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
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)

        # Generate a unique filename using UUID
        ext = os.path.splitext(file_info.file_path)[1] or ".jpg"
        unique_filename = f"{uuid.uuid4()}{ext}"
        folder_name = "photos"
        os.makedirs(folder_name, exist_ok=True)
        full_path = os.path.join(folder_name, unique_filename)

        with open(full_path, 'wb') as photo:
            photo.write(data)

        return full_path

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
    def __init__(self, token, telegram_chat_url):
        super().__init__(token, telegram_chat_url)
        self.media_groups = {}
        self.image_counter = {}
        self.prediction_number_map = {}
        self.new_users = set()
        self.processed_media_groups = set()
        self.valid_filters = [
            'concat','concat horizontal', 'concat vertical', 'blur', 'contour',
            'rotate', 'segment', 'salt and pepper', 'rotate2',
            'brighten', 'darken', 'invert','detect'
        ]
        self.s3_bucket_name = os.environ.get("S3_BUCKET_NAME")
        self.s3_client = boto3.client("s3", region_name="eu-west-2")
        self.sqs_client = boto3.client("sqs", region_name="eu-west-2")
        self.sqs_queue_url = os.environ.get("SQS_QUEUE_URL")

        logger.info(f"Loaded S3_BUCKET_NAME from env: {self.s3_bucket_name}")

    def send_to_sqs(self, prediction_id, chat_id, image_name, image_number=None):
        message = {
            "prediction_id": prediction_id,
            "chat_id": chat_id,
            "image_s3_url": f"https://{self.s3_bucket_name}.s3.eu-west-2.amazonaws.com/{image_name}",
            "timestamp": datetime.utcnow().isoformat()
        }

        if image_number is not None:
            message["image_number"] = image_number

        response = self.sqs_client.send_message(
            QueueUrl=self.sqs_queue_url,
            MessageBody=json.dumps(message)
        )
        logger.success(f"✅ Sent prediction {prediction_id} (image {image_number}) to SQS.")
        return response

    def upload_to_s3(self, file_path):
        try:
            if not self.s3_bucket_name:
                logger.error("S3_BUCKET_NAME not defined; cannot upload")
                return None

            image_name = os.path.basename(file_path)
            logger.info(f"Attempting to upload {file_path} as {image_name} to bucket {self.s3_bucket_name}")
            self.s3_client.upload_file(file_path, self.s3_bucket_name, image_name)
            logger.success(f" Uploaded {image_name} to S3 bucket {self.s3_bucket_name}")
            return image_name

        except NoCredentialsError:
            logger.error("AWS credentials not found.")
            logger.info(f"Attempting to upload {file_path} to bucket {self.s3_bucket_name}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during upload to S3: {e}")
            logger.info(f"Attempting to upload {file_path} to bucket {self.s3_bucket_name}")
            return None


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
                    self.send_text(msg['chat']['id'], "Hiii! How can I help you?")
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
                image_name = self.upload_to_s3(path)
                if not image_name:
                    self.send_text(msg['chat']['id'], "Failed to upload image to cloud.")
                    return

                chat_id = msg['chat']['id']
                prediction_id = str(uuid.uuid4())

                # Increment and track image number per user
                if chat_id not in self.image_counter:
                    self.image_counter[chat_id] = 1
                else:
                    self.image_counter[chat_id] += 1

                image_number = self.image_counter[chat_id]
                self.prediction_number_map[prediction_id] = (chat_id, image_number)

                # Notify the user
                self.send_text(chat_id, f"🕐 Image {image_number} received. You'll get results soon.")

                self.send_to_sqs(prediction_id, chat_id, image_name, image_number=image_number)

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
            # Upload filtered image to S3
            uploaded_name = self.upload_to_s3(new_path)
            if not uploaded_name:
                self.send_text(msg['chat']['id'], "Failed to upload filtered image to cloud.")
                return

            self.send_photo(msg['chat']['id'], new_path)


        except Exception as e:
            logger.error(f"Error while handling message : {e}")
            self.send_text(msg['chat']['id'], "Something went wrong please try again")
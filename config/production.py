import os, json 
import boto3
from botocore.exceptions import ClientError
from .base import Config
from flask import url_for


class ProductionConfig(Config):

    REDIRECT_URI = os.getenv('HVP_APP_CALLBACK_URL')
    MAIN_URI = os.getenv("HVP_APP_URL")
    DEBUG_DUE_SURVEY = False 

    def __init__(self):
        secret_name = os.getenv("AWS_SECRETS_NAME")
        region_name = os.getenv("AWS_REGION")
        profile_name = os.environ.get("AWS_LOGIN_PROFILE_NAME")
        self.load_secrets(secret_name, region_name, profile_name)

    def load_secrets(self, secret_name, region_name, profile_name):
        session = boto3.Session(profile_name=profile_name)
        client = session.client("secretsmanager", region_name=region_name)
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(get_secret_value_response['SecretString'])

        self.COGNITO_DOMAIN = secret.get('HVP_APP_COGNITO_URL')
        self.CLIENT_SECRET = secret.get('HVP_APP_CLIENT_SECRET')
        self.PUBLIC_KEY_URL = secret.get('HVP_APP_TOKEN_VERIFY_URL')
        self.CLIENT_ID = secret.get('HVP_APP_CLIENT_ID')

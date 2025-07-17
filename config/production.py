import os, json 
from config.base import Config
from utils.aws_session import get_boto3_session


class ProductionConfig(Config):

    REDIRECT_URI = os.getenv('HVP_STUDY_APP_CALLBACK_URL')
    MAIN_URI = os.getenv("HVP_STUDY_APP_URL")
    DEBUG_DUE_SURVEY = False 

    def __init__(self):
        secret_name = os.getenv("AWS_SECRETS_NAME")
        region_name = os.getenv("AWS_REGION")
        self.load_secrets(secret_name, region_name)

    def load_secrets(self, secret_name, region_name):
        session = get_boto3_session()
        client = session.client("secretsmanager", region_name=region_name)
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(get_secret_value_response['SecretString'])

        self.COGNITO_DOMAIN = secret.get('HVP_APP_COGNITO_URL')
        self.CLIENT_SECRET = secret.get('HVP_APP_CLIENT_SECRET')
        self.PUBLIC_KEY_URL = secret.get('HVP_APP_TOKEN_VERIFY_URL')
        self.CLIENT_ID = secret.get('HVP_APP_CLIENT_ID')

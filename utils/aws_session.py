import os
import boto3

def get_boto3_session():
    env = os.getenv("FLASK_ENV", "production")

    if env == "production":
        return boto3.Session() 
    else: 
        profile = os.getenv("AWS_LOGIN_PROFILE_NAME")
        if not profile:
            raise ValueError("AWS_LOGIN_PROFILE_NAME environment variable is not set.")
        return boto3.Session(profile_name=profile)
    
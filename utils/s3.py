import json
from random import random
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timezone
from utils.aws_session import get_boto3_session
import logging
from hvp.core.participant import Participant
from hvp.core.question import Question
from typing import List
log = logging.getLogger(__name__)

BUCKET_NAME_SURVEYS = "human-values-project-surveys"
BUCKET_NAME_RESPONSES = "human-values-project-responses"
session = get_boto3_session()
s3 = session.client("s3", region_name="us-east-2")
dynamodb = session.resource("dynamodb", region_name="us-east-2")
SURVEY_TABLE = dynamodb.Table("hvp-survey-registry")
PARTICIPANT_TABLE = dynamodb.Table("hvp-participants")

def response_key(question_id, answer_set_id):
    return f"{question_id}/{answer_set_id}"

def response_path(participant_id: str, question_type: str, question_id: str, answer_set_id: str) -> str:
    return f"responses/{participant_id}/{question_type}/{response_key(question_id, answer_set_id)}/answer.json"

def response_exists_in_s3(participant_id, question_type, question_id, answer_set_id):
    key = response_path(participant_id, question_type, question_id, answer_set_id)
    try:
        # check if file exists in S3 
        resp = s3.list_objects_v2(Bucket=BUCKET_NAME_RESPONSES, Prefix=key)
        if 'Contents' not in resp or len(resp['Contents']) == 0:
            return False 
        else:
            return True 
        
        # resp = s3.head_object(Bucket=BUCKET_NAME_RESPONSES, Key=key)
    except Exception as e:
        raise e 

def save_response_to_s3(participant_id, question_type, question_id, answer_set_id, answer_value):
    key = response_path(participant_id, question_type, question_id, answer_set_id)
    payload = {
        "participant_id": participant_id,
        "question_id": question_id,
        "answer_set_id": answer_set_id,
        "answer_value": answer_value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    s3.put_object(
        Bucket=BUCKET_NAME_RESPONSES,
        Key=key,
        Body=json.dumps(payload),
        ContentType='application/json'
    )

def upload_json_to_s3(data: dict, key: str, bucket_name: str):
    response = s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(data),
        ContentType='application/json'
    )
    return response

def list_response_keys(prefix: str) -> list[str]:
    result = s3.list_objects_v2(Bucket=BUCKET_NAME_RESPONSES, Prefix=prefix)
    return [item['Key'] for item in result.get('Contents', []) if item['Key'].endswith(".json")]



def upload_survey(data: dict, key:str):
    return upload_json_to_s3(data=data, key=key, bucket_name=BUCKET_NAME_SURVEYS)

def upload_response(data: dict, key:str):
    return upload_json_to_s3(data=data, key=key, bucket_name=BUCKET_NAME_RESPONSES)

def download_json_from_s3(key: str, bucket_name: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=key)
        raw = obj['Body'].read().decode('utf-8')
        content = json.loads(raw)
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                log.error(f"String in S3 is not valid JSON: {key}")
                return None
        if isinstance(content, dict):
            return content
        else:
            log.error(f"Expected JSON dict, got {type(content)}: {key}")
            return None
    except s3.exceptions.NoSuchKey:
        log.error(f"Key not found in S3: {key}")
        return None
    except json.JSONDecodeError as e:
        log.error(f"JSON decode error for key {key}: {e}")
        return None
    



def download_survey(key: str) -> dict:
    return download_json_from_s3(key=key, bucket_name=BUCKET_NAME_SURVEYS)

def download_response(key: str) -> dict:
    return download_json_from_s3(key=key, bucket_name=BUCKET_NAME_RESPONSES)


def register_survey_metadata(participant_id, survey_id, filename):
    try: 
        new_itm = {
            "participant_id": participant_id,
            "survey_id": survey_id,
            "filename": filename,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        response = SURVEY_TABLE.put_item(Item=new_itm)
        return new_itm
    except Exception as e: 
        raise e



# def mark_survey_complete(participant_id, survey_id):
#     now = datetime.now(timezone.utc).isoformat()
    
#     response = SURVEY_TABLE.update_item(
#         Key={
#             "participant_id": participant_id,
#         },
#         ConditionExpression=Attr('survey_id').eq(survey_id),
#         UpdateExpression="SET #s = :status, updated_at = :updated",
#         ExpressionAttributeNames={
#             "#s": "status"
#         },
#         ExpressionAttributeValues={
#             ":status": "completed",
#             ":updated": now
#         },
#         ReturnValues="UPDATED_NEW"
#     )
#     return response




# def get_survey_metadata_for_participant(participant_id):
#     try:
#         response = SURVEY_TABLE.query(
#             KeyConditionExpression=Key("participant_id").eq(participant_id)
#         )
#         return response.get("Items", [])
#     except Exception as e:
#         log.error(f"[DynamoDB] Error querying surveys: {e}")
#         return None
    
# ----- PARTICIPANT ----- # 

def save_participant_demographics(participant_id: str, age: int, gender: str, race_ethnicity: str, profession: str, provider_type: str = None):
    item = {
        "identifier": participant_id,
        "age": int(age),
        "gender": gender,
        "race_ethnicity": race_ethnicity,
        "profession": profession,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    response = PARTICIPANT_TABLE.put_item(Item=item)
    return response

def get_participant_demographics(participant_id: str) -> dict | None:

    try:
        response = PARTICIPANT_TABLE.query(
            KeyConditionExpression=Key("identifier").eq(participant_id)
        )
        item = response.get("Items", None)
        return item[0] if item else None 
    
    except Exception as e:
        log.error(f"[DynamoDB] Error retrieving participant {participant_id}: {e}")
        return None
    


# ----- SES ------- 
def dispatch_email_notification(recipient_email, link):
    ses = session.client("ses", region_name="us-east-2")
    response = ses.send_email(
        Source="raheel_sayeed@hms.harvard.edu",
        Destination={"ToAddresses": [recipient_email]},
        Message={
            "Subject": {"Data": "Your survey is ready!"},
            "Body": {
                "Text": {
                    "Data": (
                        "Thank you for enrolling in the Clinical Decision Dynamics Study, part of the Human Values Project of Harvard Medical School.\n\n"
                        f"Please begin your survey here: {link}\n\n"
                        "We appreciate your contribution."
                    )
                }
            }
        }
    )
    return response


def save_flag_to_s3(participant_id, question_type, question_id, answer_set_id, comment):
    session = get_boto3_session()
    s3 = session.client('s3')

    payload = {
        "participant_id": participant_id,
        "question_id": question_id,
        "answer_set_id": answer_set_id,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    key = f"flags/{participant_id}/{question_type}/{question_id}/{answer_set_id}/flag.json"
    s3.put_object(
        Bucket=BUCKET_NAME_RESPONSES,
        Key=key,
        Body=json.dumps(payload),
        ContentType="application/json"
    )

    logging.info(f"[Flag] Saved flag for {participant_id} on {question_id}/{answer_set_id}")
    
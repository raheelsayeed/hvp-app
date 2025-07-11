import argparse
import json
import hashlib
import boto3
import os
from botocore.exceptions import ClientError
from hvp.core.question import Question

# DynamoDB table name
profile = os.getenv("AWS_LOGIN_PROFILE_NAME")
session = boto3.Session(profile_name=profile)
dynamodb = session.resource("dynamodb", region_name="us-east-2")

TABLE_NAME = "hvp-questions"
table = dynamodb.Table(TABLE_NAME)

def hash_text(text: str) -> str:
    """Generate a SHA-256 hash of the input text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

def upload_questions(filepath: str):
    with open(filepath, "r") as f:
        questions = json.load(f)

    for question in questions:

        new_q = Question(**question)


        question_text = question.get("text")
        question_instruction = question.get("instruct_human")
        question_canonical_identifier = question.get("canonical_identifier")
        if not question_text:
            print("Skipping question without text")
            continue

        question_id = hash_text(question_text + question_instruction + question_canonical_identifier)
        question["identifier"] = question_id

        try:
            table.put_item(
                Item=question,
                ConditionExpression="attribute_not_exists(identifier)"
            )
            print(f"✅ Uploaded: {question_id}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                print(f"⚠️ Duplicate skipped: {question_id}")
            else:
                print(f"❌ Error uploading {question_id}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Upload questions to DynamoDB")
    parser.add_argument("--questions", required=True, help="Path to JSON file with questions")
    args = parser.parse_args()
    upload_questions(args.questions)

if __name__ == "__main__":
    main()

from hvp.core.question import Question
from hvp.core.participant import Participant
from typing import Callable, Dict, List, Optional, Any
from utils.aws_session import get_boto3_session
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
import random
import logging


client = get_boto3_session()
dynamodb = client.resource("dynamodb", region_name="us-east-2")
QUESTIONS_TABLE = dynamodb.Table("hvp-questions")
HVP_PARTICIPANTS_REGISTRY_TABLE = dynamodb.Table("hvp-survey-registry")


def get_question_identifiers(question_type: Optional[str]) -> List[str]:

    """
    Retrieve all question identifiers from the DynamoDB table.
    
    If a type is specified, filter questions by that type.
    
    :param type: Optional QuestionType to filter questions.
    :return: List of Question objects with identifiers and types.
    """
    logging.debug(f"Retrieving questions from DynamoDB with type: {question_type}")
    scan_kwargs = {
        'ProjectionExpression': 'identifier'
    }
    if question_type:
        scan_kwargs['FilterExpression'] = '#type = :qtype'
        scan_kwargs['ExpressionAttributeNames'] = {'#type': 'type'}
        scan_kwargs['ExpressionAttributeValues'] = {':qtype': question_type}

    response = QUESTIONS_TABLE.scan(**scan_kwargs)
    identifiers = [item['identifier'] for item in response.get('Items', [])]
    
    logging.debug(f"Retrieved {len(identifiers)} questions from DynamoDB with type {question_type}")

    return identifiers




def get_question_by_id(question_id: str) -> Optional[Question]:
    """
    Retrieve a question by its identifier from the DynamoDB table.
    
    :param question_id: The identifier of the question.
    :return: Question object if found, None otherwise.
    """
    try:
        response = QUESTIONS_TABLE.get_item(Key={'identifier': question_id})
        item = response.get('Item')
        
        if item:
            logging.debug(f"Found question with ID: {question_id}")
            return Question(**item)
        else:
            logging.warning(f"Question with ID {question_id} not found.")
            return None
    except Exception as e:
        logging.error(f"Error retrieving question with ID {question_id}: {e}")
        return None 
    


def check_question_response_exists(participant_id: str, question_id: str) -> bool:
    """
    Check if a response exists for a given participant and question ID.
    
    :param participant_id: The identifier of the participant.
    :param question_id: The identifier of the question.
    :return: True if a response exists, False otherwise.
    """

    question = get_question_by_id(question_id)
    if not question:
        logging.error(f"Question with ID {question_id} does not exist.")
        return False, None
    

    from utils.s3 import response_exists_in_s3 
    for answer_set in question.answers:
        if answer_set.identifier:
            if response_exists_in_s3(participant_id, question_id, answer_set.identifier):
                logging.info(f"Response exists for participant {participant_id}, question {question_id}, answer set {answer_set.identifier}.")
                continue 
            else:
                logging.debug(f"No response found for participant {participant_id}, question {question_id}, answer set {answer_set.identifier}.")
                return False, question
            
    return True, question


_NEXT_QUESTION_HANDLERS: Dict[str, Callable] = {}

def register_next_handler(question_type: str):
    def deco(fn: Callable):
        _NEXT_QUESTION_HANDLERS[question_type] = fn
        return fn
    return deco

# ── 2) Dispatcher ──────────────────────────────────────────────────────────
def get_next_question(
    participant: Participant,
    progress_registry: dict,
    questions_metadata: dict,
    question_type: str,
) -> Optional[Question]:
    handler = _NEXT_QUESTION_HANDLERS.get(question_type)
    answered_ids = set(progress_registry.get("answered_questions", {}).get(question_type, None))
    if not handler:
        raise ValueError(f"No next-question handler for type={question_type!r}")
    return handler(participant, progress_registry, questions_metadata, answered_ids)


@register_next_handler("TRIAGE")
def _next_triage(
    participant: Participant,
    progress_registry: dict,
    questions_metadata: dict,
    answered_question_ids: Optional[List[str]]
) -> Optional[Question]:
    filter_expression = Attr('type').eq('TRIAGE') & Attr('version').eq('2') 
    if answered_question_ids and len(answered_question_ids) > 0:
        filter_expression = filter_expression & ~Attr("identifier").is_in(answered_question_ids)
    response = QUESTIONS_TABLE.scan(
                        ProjectionExpression="identifier",
                        FilterExpression=(filter_expression)
                    )   
    all_questions = response.get("Items", [])
    if len(all_questions) == 0:
        return None 
    next_q = random.choice(all_questions)
    if next_q:
        next_q = get_question_by_id(next_q['identifier'])
        return next_q 
    else: 
        return None


@register_next_handler("TRIAGEDEMO")
def _next_triage2(
    participant: Participant,
    progress_registry: dict,
    questions_metadata: dict,
    answered_question_ids: Optional[List[str]]
) -> Optional[Question]:
    filter_expression = Attr('type').eq('TRIAGEDEMO') & Attr('version').eq('demo') 
    if answered_question_ids and len(answered_question_ids) > 0:
        filter_expression = filter_expression & ~Attr("identifier").is_in(answered_question_ids)
    response = QUESTIONS_TABLE.scan(
                        ProjectionExpression="identifier",
                        FilterExpression=(filter_expression)
                    )   
    all_questions = response.get("Items", [])
    if len(all_questions) == 0:
        return None 
    
    next_q = random.choice(all_questions)
    if next_q:
        next_q = get_question_by_id(next_q['identifier'])
        return next_q 
    else: 
        return None


@register_next_handler("MANAGEMENT")
def _next_management_question(
    participant: Participant,
    progress_registry: dict,
    questions_metadata: dict,
    answered_question_ids: Optional[List[str]]
) -> Optional[Question]:
    
    max = questions_metadata.get('MAX')
    num_answered = len(answered_question_ids) if answered_question_ids else 0 

    if num_answered >= max:
        return None
    
    # get all questions
    completed_cases_numbers = []
    if num_answered > 0:
        response = QUESTIONS_TABLE.scan(
            ProjectionExpression="identifier, metadata",
            FilterExpression=(Attr("identifier").is_in(answered_question_ids))
        )
        completed_qs = response.get("Items", [])
        completed_cases_numbers = [q['metadata']['case'] for q in completed_qs]



    filter_expression = Attr('type').eq('MANAGEMENT') & Attr('version').eq('2') 
    if len(completed_cases_numbers) > 0: 
        filter_expression = filter_expression & ~Attr('identifier').is_in(answered_question_ids) & ~Attr('metadata.case').is_in(completed_cases_numbers)
    response = QUESTIONS_TABLE.scan(
                        ProjectionExpression="identifier",
                        FilterExpression=(filter_expression)
                    )

    all_questions = response.get("Items", [])
    if len(all_questions) == 0: 
        return None 
    next_q = random.choice(all_questions)
    next_q = get_question_by_id(next_q['identifier'])
    return next_q




def increment_question_progress(participant_id: str, question_type: str, count: int = 1, question_id: str = None) -> int:
    try:
        response = HVP_PARTICIPANTS_REGISTRY_TABLE.update_item(
            Key={"participant_id": participant_id},
            UpdateExpression="SET progress.#qt = if_not_exists(progress.#qt, :zero) + :inc",
            ExpressionAttributeNames={"#qt": question_type},
            ExpressionAttributeValues={
                ":inc": count,
                ":zero": 0
            },
            ReturnValues="UPDATED_NEW"
        )

        updated_value = response.get("Attributes", {}).get("progress", {}).get(question_type)
        print(f"[increment] {participant_id} now has {updated_value} questions answered for '{question_type}'")

        if question_id:
            # Update the answered questions list if question_id is provided
            append_response = HVP_PARTICIPANTS_REGISTRY_TABLE.update_item(
                Key={"participant_id": participant_id},
                UpdateExpression="SET answered_questions.#qt = list_append(if_not_exists(answered_questions.#qt, :empty_list), :qid)",
                ExpressionAttributeNames={
                    "#qt": question_type
                },
                ExpressionAttributeValues={
                    ":qid": [question_id],
                    ":empty_list": []
                }
            )

        print(f"[increment] Added question ID {question_id} to answered questions for {participant_id} under '{question_type}'")
        return updated_value if updated_value is not None else 0

    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationException":
            # If the item doesn't exist, create a new one
            print(f"[increment] Item not found, creating new registry entry for {participant_id}")
            try:
                HVP_PARTICIPANTS_REGISTRY_TABLE.put_item(
                    Item={
                        "participant_id": participant_id,
                        "progress": {question_type: count}
                    }
                )
                print(f"[increment] Created new registry record for {participant_id} with {count} answered for '{question_type}'")
                return count
            except Exception as e2:
                print(f"[increment] Failed to create item for {participant_id}: {e2}")
                return 0
        else:
            print(f"[increment] Unexpected error while updating registry: {e}")
            return 0



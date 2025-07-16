from hvp.core.question import Question
from typing import Dict, List, Optional 
from utils.aws_session import get_boto3_session
from botocore.exceptions import ClientError

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


def get_random_question_id(question_type: Optional[str]) -> Optional[str]:
    """
    Get a random question identifier from the DynamoDB table.
    
    If a type is specified, filter questions by that type.
    
    :param question_type: Optional QuestionType to filter questions.
    :return: A random question identifier or None if no questions found.
    """
    identifiers = get_question_identifiers(question_type)
    
    if not identifiers:
        logging.warning("No questions found in DynamoDB.")
        raise
    
    from random import sample
    # question_id = sample(identifiers, 1)
    from random import random
    random_index = int(random() * len(identifiers))
    question_id = identifiers[random_index]
    
    logging.debug(f"Selected random question ID: {question_id}")
    
    return question_id


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


def get_random_unanswered_question(participant_data: dict, question_type: str) -> Optional[Question]:
    """
    Return a random unanswered Question from DynamoDB for a given participant and question type.

    :param participant_data: A dict with 'answered_questions' as in your example
    :param question_type: Question type to pull from ("TRIAGE", "MANAGEMENT", etc.)
    :return: A single Question object or None if no new questions found
    """
    try:
        # Get the list of already answered question_ids
        answered_ids = set(participant_data.get("answered_questions", {}).get(question_type, []))

        # Scan all questions of this type
        response = QUESTIONS_TABLE.scan(
            FilterExpression="#type = :qtype",
            ExpressionAttributeNames={"#type": "type"},
            ExpressionAttributeValues={":qtype": question_type}
        )

        all_questions = response.get("Items", [])
        logging.debug(f"[get_random_unanswered_question] Found {len(all_questions)} total questions of type {question_type}")

        # Filter out already answered ones
        unanswered = [q for q in all_questions if q["identifier"] not in answered_ids]
        logging.debug(f"[get_random_unanswered_question] Remaining unanswered: {len(unanswered)}")

        if not unanswered:
            logging.info(f"No unanswered questions left for {question_type}")
            return None

        # Pick one at random
        import random
        selected = random.choice(unanswered)

        # Return as validated model (optional)
        return Question(**selected)

    except Exception as e:
        logging.error(f"[get_random_unanswered_question] Failed to fetch: {e}")
        return None
    

def get_unanswered_questions(participant_id: str, question_type: str, number_of_questions: int = 10, answered_question_ids: Optional[List[str]] = None) -> List[Question]:
    
    unanswered_questions = []
    max_attempts = number_of_questions * 10  # Safety to avoid infinite loop
    attempts = 0


    while len(unanswered_questions) < number_of_questions and attempts < max_attempts:
        random_question_id = get_random_question_id(question_type)

        if not random_question_id:
            logging.warning(f"No random question found for type '{question_type}'")
            attempts += 1
            continue

        answered, question = check_question_response_exists(participant_id, random_question_id)

        if question and answered == False:
            unanswered_questions.append(question)

        attempts += 1

    if len(unanswered_questions) < number_of_questions:
        raise ValueError(f"Not enough unanswered questions available for the participant. Found: {len(unanswered_questions)}, Required: {number_of_questions}, attempted: {attempts}")

    if len(unanswered_questions) == 0:
        logging.error(f"No unanswered questions found for participant {participant_id} of type {question_type}.")
        raise ValueError(f"No unanswered questions found for participant {participant_id} of type {question_type}.")
    

    return list(unanswered_questions)




def get_question_progress_by_type(participant_id: str, question_types: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Get the progress of a participant on questions of specified types.
    
    :param participant_id: The identifier of the participant.
    :param question_types: List of question types to check progress for.
    :return: Dictionary with question type as key and a dictionary of counts as value.
    """
    progress = {qtype: {'total': 0, 'answered': 0} for qtype in question_types}
    
    for qtype in question_types:
        identifiers = get_question_identifiers(qtype)
        progress[qtype]['total'] = len(identifiers)
        
        for qid in identifiers:
            answered, _ = check_question_response_exists(participant_id, qid)
            if answered:
                progress[qtype]['answered'] += 1
    
    return progress




def increment_question_progress(participant_id: str, question_type: str, count: int = 1, question_id: str = None) -> int:
    """
    Increment the number of questions answered by a participant for a given question type.
    Creates the item if it doesn't exist.

    :param participant_id: Unique identifier (usually email) of the participant.
    :param question_type: The type/category of questions (e.g., "TRIAGE").
    :param count: Number of questions to increment (default: 1).
    :return: The updated value after increment.
    """
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



from hvp.core.participant import Participant
from hvp.core.enums import SubjectType, ClinicalField
from utils.appparticipant import AppParticipant
from utils.aws_session import get_boto3_session

import logging 

dynamo_client_session = get_boto3_session()
d_client = dynamo_client_session.resource("dynamodb", region_name="us-east-2")
SURVEY_TABLE = d_client.Table("hvp-survey-registry")


def assign_question_types(participant: AppParticipant):
    types = []

    if  participant.subject_type == SubjectType.HEALTHCARE_PROVIDER:
        types.append("TRIAGE")

        # if 'Critical Care Medicine' in participant.clinical_field or 'Internal Medicine' in participant.clinical_field:
        #     types.append("MANAGEMENT")

    
    
    # Assign first one as enabled, rest as pending
    assigned = []
    for i, qtype in enumerate(types):
        assigned.append({
            "type": qtype,
            "status": "enabled" if i == 0 else "pending"
        })

    registry_item = {
        "participant_id": participant.identifier,
        "assigned_question_types": types,
        "progress": {q['type']: 0 for q in assigned},
        "answered_questions": {q['type']: [] for q in assigned}
    }

    logging.debug(f'Assigning question types for participant {participant.identifier}: {types} {registry_item}')

    try: 
        response = SURVEY_TABLE.put_item(
            Item=registry_item
        )
        logging.info(f"Assigned question types for participant {participant.identifier}: {types}")

    except Exception as e:
        logging.error(f"Error assigning question types for participant {participant.identifier}: {e}")
        raise e




def get_assigned_question_types_with_progress(participant_id: str, total_questions_dict: dict, threshold_for_type_dict: dict) -> list[dict]:
    try:
        response = SURVEY_TABLE.get_item(Key={"participant_id": participant_id})

        if "Item" not in response:
            logging.warning(f"No registry item found for participant {participant_id}")
            return []

        item = response["Item"]

        assigned_types = item.get("assigned_question_types", [])
        progress = item.get("progress", {})

        result = []
        for i, qtype in enumerate(assigned_types):
            answered = progress.get(qtype, 0)
            total = total_questions_dict.get(qtype, 0)
            minimum = threshold_for_type_dict.get(qtype, 0)
            status = "enabled" 

            if i == 0:
                if answered >= minimum:
                    status = "enabled"
            else:
                previous_answered = progress.get(assigned_types[i - 1], 0) 
                previous_minimum = threshold_for_type_dict.get(assigned_types[i - 1], 0) 
                if previous_answered >= previous_minimum:
                    status = "enabled"
                else:
                    status = "pending"
            

            # status = "enabled" if i == 0 or progress.get(assigned_types[i - 1], 0) >= minimum else "pending"

            result.append({
                "type": qtype,
                "status": status,
                "answered": answered,
                "total": total,
                "minimum": minimum
            })

        return result

    except Exception as e:
        logging.error(f"Error getting assigned question types for {participant_id}: {e}")
        raise e
        return []
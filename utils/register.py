
from hvp.core.question import Question 
from utils.aws_session import get_boto3_session



@staticmethod 
def REGISTRY_TABLE(): 

    client = get_boto3_session()
    dynamodb = client.resource("dynamodb", region_name="us-east-2")
    return dynamodb.Table("hvp-survey-registry")


def get_participant_registry(participant_id: str):
    """
    Retrieve the registry item for a participant.
    """
    table = REGISTRY_TABLE()
    response = table.get_item(Key={"participant_id": participant_id})
    
    if "Item" not in response:
        return None
    
    return response["Item"]
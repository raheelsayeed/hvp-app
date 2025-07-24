from utils.aws_session import get_boto3_session
from hvp.core.participant import Participant

email_assigned = f"""

Thank you for enrolling in the Clinical Decision Dynamics Study, part of the Human Values Project at Harvard Medical School.

Please begin your survey here:
https://study.hvp.global

We appreciate your contribution to this important research. If you have any questions, feel free to reply to this email.

The Clinical Decision Dynamics Study Team
Department of Biomedical Informatics
Harvard Medical School
"""


email_not_assigned = f"""

Thank you for completing your profile and enrolling in the Clinical Decision Dynamics Study, part of the Human Values Project at Harvard Medical School.

At this time, you have not yet been assigned a set of survey questions. We will notify you as soon as new question sets become available for you to complete.

Thank you for your patience and interest in our study. If you have any questions in the meantime, please don’t hesitate to reach out (https://study.hvp.global/contact)

The Clinical Decision Dynamics Study Team
Department of Biomedical Informatics
Harvard Medical School 
"""
# ----- SES ------- 
def dispatch_email_notification(participant: Participant, assigned_types):

    message = f'Dear {participant.first_name},' + (email_assigned if len(assigned_types) > 0 else email_not_assigned)
    session = get_boto3_session()
    ses = session.client("ses", region_name="us-east-2")
    try:
        response = ses.send_email(
            Source="humanvaluesproject@hms.harvard.edu",
            Destination={"ToAddresses": [participant.identifier]},
            Message={
                "Subject": {"Data": "Welcome to the Clinical Decision Dynamics Study"},
                "Body": {
                    "Text": {
                        "Data": (
                            message
                        )
                    }
                }
            }
        )
    except Exception as e: 
        raise e 
    
    return response


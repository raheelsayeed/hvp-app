from utils.aws_session import get_boto3_session
from hvp.core.participant import Participant

email_assigned = f"""

Thank you for enrolling in the Clinical Decision Dynamics Study, part of the Human Values Project at Harvard Medical School.

Please begin your survey here:
https://study.hvp.global

We appreciate your contribution to this important research. If you have any questions, please email us at humanvaluesproject@hms.harvard.edu or visit https://study.hvp.global/contact.

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

    source_arn_dbmi = 'arn:aws:ses:us-east-1:634525385963:identity/dbmi.hms.harvard.edu'
    message = f'Dear {participant.first_name},' + (email_assigned if len(assigned_types) > 0 else email_not_assigned)
    session = get_boto3_session()
    ses = session.client("ses", region_name="us-east-1")
    try:
        response = ses.send_email(
            Source="humanvaluesproject@dbmi.hms.harvard.edu",
            SourceArn=source_arn_dbmi,
            ReturnPathArn=source_arn_dbmi,
            Destination={"ToAddresses": [participant.identifier]},
            ReplyToAddresses=["no-reply@dbmi.hms.harvard.edu"],
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


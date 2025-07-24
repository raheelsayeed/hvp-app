from typing import Optional, List
from hvp.core.participant import Participant, ParticipantType
from hvp.core.survey import Survey
from utils.s3 import * 
import logging 
from datetime import timezone, datetime 
from botocore.exceptions import ClientError
from hvp.core.enums import SubjectType, ProviderTypeEnum, GeoContext

log = logging.getLogger(__name__)

class AppParticipant(Participant):

    subject_type: Optional[SubjectType] = None 
    provider_type: Optional[ProviderTypeEnum] = None
    geo_context: Optional[GeoContext] = None
    clinical_field: Optional[List[str]] = None

    @staticmethod
    def initial_entry(email, fn, ln):
        try:
            PARTICIPANT_TABLE.put_item(
                Item={
                    "identifier": email,
                    "first_name": fn,
                    "last_name": ln
                },
                ConditionExpression='attribute_not_exists(identifier)'
            )
            log.info(f"✅ Participant entry created for {email}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                log.warning(f"⚠️ Participant with email '{email}' already exists. Skipping initial insert.")
            else:
                log.error(f"❌ Unexpected error while creating participant {email}: {e}")
                raise
        except Exception as e:
            log.exception(f"❌ General error during initial entry for {email}")
            raise

    
    def persist(self):
        try:
            PARTICIPANT_TABLE.put_item(
                Item={
                    "identifier": self.identifier,
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "type": self.type.name,
                    "age": self.age,
                    "gender": self.gender,
                    "race_ethnicity": self.race_ethnicity,
                    "profession": self.profession,
                    "email": self.email,
                    "city": getattr(self, "city", None),
                    "country": getattr(self, "country", None),
                    "geo_context": self.geo_context.value if self.geo_context else None,
                    "healthcare_system": self.healthcare_system.value if self.healthcare_system else None,
                    "subject_type": self.subject_type.value if self.subject_type else None,
                    "provider_type": self.provider_type.value if self.provider_type else None,
                    "clinical_field": self.clinical_field,
                    "status": self.status.value,
                    "lat": getattr(self, "lat", None),
                    "long": getattr(self, "long", None),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as e:
            err = f'FAILED TO PERSIST PARTICIPANT: {e}'
            log.error(err)
            raise SystemError(err)
        

    
    def populate_from_key(self, key):
        data = get_participant_demographics(self.identifier)
        if key:
            self.age = data.get("age", None)
            self.gender = data.get("gender", None) 
            self.race_ethnicity = data.get("race_ethnicity", None)
            self.profession = data.get("profession", None)
            self.subject_type = SubjectType(data.get("subject_type")) if data.get("subject_type") else None 
            self.provider_type = ProviderTypeEnum(data.get("provider_type")) if data.get("provider_type") else None
            self.geo_context = GeoContext(data.get("geo_context")) if data.get("geo_context") else None
            self.clinical_field =  data.get("clinical_field", None)
            self.city = data.get("city", None)
            self.country = data.get("country", None)
            self.lat = data.get("lat", None)
            self.long = data.get("long", None)
    
    def populate_from_dynamo(self):
        data = get_participant_demographics(self.identifier)
        self.populate_from_key(data)

    @property
    def has_demographics(self):
        return self.age != None

    @staticmethod
    def load(participant_id):
        try:
            item = get_participant_demographics(participant_id)
            log.debug(f'Retrieved participant data= {item}')
            if item:
                ap = AppParticipant(
                    first_name=item.get("first_name", ""),
                    last_name=item.get("last_name", ""),
                    type=ParticipantType.HUMAN,
                    email=participant_id
                )
                ap.populate_from_key(item)
                return ap
        except Exception as e:
            log.error(f"[DynamoDB] Error loading participant {participant_id}: {e}")
        return None
     

    # def get_due_surveys(self):
        
        # all_survey_metadata = get_survey_metadata_for_participant(self.identifier)
        # log.debug(f'survey_metadata={all_survey_metadata}') 

        # due_surveys = []

        # for metadata in all_survey_metadata:
        #     key = metadata.get("filename")
        #     survey_data = download_survey(key)
        #     if survey_data:
        #         survey_obj = Survey(**survey_data)
        #         survey_item = SurveyItem(survey=survey_obj, metadata=metadata)
        #         due_surveys.append(survey_item)
        #     else:
        #         raise ValueError(f"Survey data not found; key={key}")
        
        # # if no due surveys found, create a  new one
        # if len(all_survey_metadata) == 0:
        #     new_survey = self.create_new_survey()
        #     survey_id = new_survey.identifier
        #     key = f"surveys/{self.identifier}/{survey_id}.json"
        #     upload_survey(data=new_survey.model_dump_json(), key=key)
        #     dispatch_email_notification(self.email, f"https://study.hvp.global")
        #     s_metadata = register_survey_metadata(
        #         participant_id=self.identifier,
        #         survey_id=survey_id,
        #         filename=key
        #     )
        #     log.debug(f'New Survey Registered={s_metadata}')
        #     survey_item = SurveyItem(survey=new_survey, metadata=s_metadata)
        #     due_surveys.append(survey_item)

        # return due_surveys
    

    # from utils.question_extension import get_unanswered_questions 
   
   



    # def create_new_survey(self, num_questions: int = 12) -> Survey:

    #     # get 10 ananswered questions
    #     from utils.question_extension import get_unanswered_questions

    #     # make sure they are new/unanswered 
    #     # make sure they belong to the right type
    #     questions = get_unanswered_questions(
    #         participant_id=self.identifier,
    #         question_type='TRIAGE',
    #         number_of_questions=num_questions
    #     )

    #     if questions is None or len(questions) == 0:
    #         raise ValueError("No unanswered questions available for the participant.")

    #     # create a Survey with these questions 
    #     survey = Survey(
    #         metadata={"question_type": "TRIAGE"},
    #         questions=questions,
    #         participant=self
    #     )

    #     # return the Survey object
    #     return survey
        

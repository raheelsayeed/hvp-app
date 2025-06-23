from typing import Optional
from hvp.core.participant import Participant, ParticipantType
from hvp.core.survey import Survey
from utils.survey_item import SurveyItem
from utils.s3 import * 
import logging 
from datetime import timezone, datetime 
from botocore.exceptions import ClientError
from hvp.core.enums import SubjectType, ProviderTypeEnum, GeoContext, ClinicalField

log = logging.getLogger(__name__)

class AppParticipant(Participant):

    subject_type: Optional[SubjectType] = None 
    provider_type: Optional[ProviderTypeEnum] = None
    geo_context: Optional[GeoContext] = None
    clinical_field: Optional[ClinicalField] = None

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
                    "clinical_field": self.clinical_field.value if self.clinical_field else None,
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
     

    def get_due_surveys(self):
        
        all_survey_metadata = get_survey_metadata_for_participant(self.identifier)
        log.debug(f'survey_metadata={all_survey_metadata}') 

        due_surveys = []

        for metadata in all_survey_metadata:
            key = metadata.get("filename")
            survey_data = download_survey(key)
            if survey_data:
                survey_obj = Survey(**survey_data)
                survey_item = SurveyItem(survey=survey_obj, metadata=metadata)
                due_surveys.append(survey_item)
            else:
                raise ValueError(f"Survey data not found; key={key}")
        
        # if no due surveys found, create a  new one
        if len(all_survey_metadata) == 0:
            new_survey = self.create_new_survey()
            survey_id = new_survey.identifier
            key = f"surveys/{self.identifier}/{survey_id}.json"
            upload_survey(data=new_survey.model_dump_json(), key=key)
            # dispatch_email_notification(self.email, f"https://dev.hvp.global/survey/start")
            s_metadata = register_survey_metadata(
                participant_id=self.identifier,
                survey_id=survey_id,
                filename=key
            )
            log.debug(f'New Survey Registered={s_metadata}')
            survey_item = SurveyItem(survey=new_survey, metadata=s_metadata)
            due_surveys.append(survey_item)

        return due_surveys






    def create_new_survey(self):
        
        from hvp.generator.generator import SurveyGenerator
        from hvp.core.question import QuestionSet
        from hvp.core.question import QuestionTypes
        from demo import Demo

        questions = Demo.QuestionsV2()

        QSet = QuestionSet(
                title="Triage and Diagnositic Questions",
                questions=questions,
                version="2.1"
            )
        
        survey = SurveyGenerator().create_and_assign(
            num_questions=3,
            question_set=QSet,
            participant=self,
            filter_func=lambda q, p: q.type in 
                [QuestionTypes.TRIAGE, QuestionTypes.DIAGNOSIS]
        )

        return survey





from pydantic import BaseModel
from hvp.core.survey import Survey

class SurveyItem(BaseModel):
    survey: Survey
    metadata: dict
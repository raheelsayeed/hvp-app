import json
from hvp.core.survey import Survey
from hvp.core.question import Question, QuestionSet


class Demo:

    @staticmethod
    def AssignedSurvey():

        demo_file = "/Users/raheel/dbmi/hvp_project/generated_data/survey_participant_gpt.json"
        with open(demo_file) as f:
            survey_data = json.load(f)
            assigned_survey = Survey(**survey_data)
            return assigned_survey
        

    @staticmethod 
    def Questions(): 
        demo_file = "/Users/raheel/dbmi/hvp_project/input_data/questions.json"
        with open(demo_file) as f:
            question_data = json.load(f)
            questions = [Question.from_json(q) for q in question_data]
            return questions

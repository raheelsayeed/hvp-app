import json, requests
from hvp.core.survey import Survey
from hvp.core.question import Question, QuestionSet


class Demo:

    @staticmethod
    def Questions():
        url = "https://raw.githubusercontent.com/raheelsayeed/hvp-pipeline/main/input_data/questions.json"
        
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            question_data = response.json()
            questions = [Question.from_json(q) for q in question_data]
            return questions
        except requests.RequestException as e:
            print(f"Failed to fetch questions: {e}")
            raise e
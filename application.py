from flask import Flask, render_template, redirect, session, request, url_for, g, current_app
from flask import request, redirect
import requests, os, json
import urllib.parse
from rich.console import Console
from utils.s3 import * 
import markdown
from flask import g, session
from utils.appparticipant import AppParticipant
import logging 
from rich.logging import RichHandler
from utils.auth import *
from hvp.core.survey import Survey

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
     handlers=[RichHandler()]
)

log = logging.getLogger(__name__)

p = Console().print

application = Flask(__name__)

if os.getenv("FLASK_ENV") == "production":
    from config.production import ProductionConfig
    config = ProductionConfig()
    application.config.from_object(config)
    log.debug('Loading PROD configuration')
else:
    from config.development import DevelopmentConfig
    config = DevelopmentConfig() 
    application.config.from_object(config)
    log.debug('Loading DEBUG configuration')

application.secret_key = application.config['CLIENT_ID']




# def enforce_https_in_production():
#     if current_app.debug:
#         return  # Do nothing if in debug mode (i.e., local dev)
    
#     if not request.is_secure:
#         return redirect(request.url.replace("http://", "https://", 1), code=301)

# @application.before_request    
# def before_request():
#     response = enforce_https_in_production()
#     if response:
#         return response

DUE_SURVEY_ID = 'due_survey_id'
DUE_SURVEY_METADATA = 'due_survey_metadata'

@application.template_filter('markdown')
def render_markdown(text):
    return markdown.markdown(text)

@application.template_filter('format_date')
def format_date(value, fmt="%B %d, %Y"):
    """
    Jinja filter to format ISO 8601 datetime strings or datetime objects.
    Usage: {{ metadata.created_at | format_date }}
    """
    if not value:
        return "Unknown date"

    # If it's a string, try to parse
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return "Invalid date"

    # If it's a datetime object
    if isinstance(value, datetime):
        return value.strftime(fmt)

    return "Invalid date"


def pkg(text=None, title=None, survey_list=None, due_item=None, show_resume=None):
    return {
        "user": session.get('user', None),
        "status": {"title": title, "text": text},
        "survey_list": survey_list,
        "due_survey_item": due_item,
        "show_resume": show_resume
    }
def rt(template, title=None, text=None):
    return render_template(template, **pkg(text, title))


@application.route('/governance')
def governance():
    return render_template('about.html', **pkg())

@application.route('/components')
def components():
    return render_template('about.html', **pkg())

@application.route('/contact')
def contact():
    return render_template('about.html', **pkg())


@application.before_request
def load_survey():
    if request.endpoint in ('logout',):  # or check request.path == '/logout'
        return
    
    log.debug("Loading survey for current session")
    survey_id = session.get(DUE_SURVEY_ID)
    if survey_id:
        participant_id = session.get('user', {}).get('email', None)
        s3_file = f"surveys/{participant_id}/{survey_id}.json"
        if s3_file:
            survey_dict = download_survey(key=s3_file)
            survey = Survey(**survey_dict)
            g.survey = survey
    else:
        g.survey = None


@application.route('/')
@login_required
def index():

    participant = AppParticipant.load(session.get('user', {}).get('email'))

    if participant and not participant.has_demographics:
        log.debug("Participant profile not in record")
        session['participant_id'] = participant.identifier
        return redirect(url_for('complete_profile'))

    survey_items = participant.get_due_surveys()
    due_survey_item = next(filter(lambda x: x.metadata['status'] == "pending", survey_items), None)
    survey_list = [s.metadata for s in survey_items]

    if due_survey_item:
        session[DUE_SURVEY_ID] = due_survey_item.survey.identifier
        return redirect(url_for('survey_start'))
        return render_template('main_page.html', **pkg(
            "You have a survey due and takes only XXX mins to complete",
            "📝 Survey is due",
            survey_list,
            due_survey_item,
            False
        ))
    else:
        session.pop(DUE_SURVEY_ID, None)
        return render_template('main_page.html', **pkg(
            "",
            "You will be notified when a new survey is assigned",
            survey_list,
            None,
            False
        ))



@application.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():

    if request.method == 'POST':
        from hvp.core.enums import SubjectType, ClinicalField, ProviderTypeEnum, GeoContext 

        participant_id = session.get('user', {}).get('email', None)
        if not participant_id:
            return "Participant not found in session", 400

        try:
            participant = AppParticipant.load(participant_id)
            if not participant:
                return f"Participant {participant_id} not found in DB", 404

            log.debug(f'Form submitted = {request.form}')
        
            participant.age = request.form.get('age')
            participant.gender = request.form.get('gender')
            participant.race_ethnicity = request.form.get('race_ethnicity')
            participant.country = request.form.get('country')
            participant.city = request.form.get('city')
            participant.subject_type = SubjectType(request.form.get('subject_type', None))

            participant.lat = request.form.get('latitude', None)
            participant.long = request.form.get('longitude', None)


            if participant.subject_type == SubjectType.HEALTHCARE_PROVIDER:
                
                    participant.provider_type = ProviderTypeEnum(request.form.get('provider_type', None))
                    participant.clinical_field = ClinicalField(request.form.get('clinical-field', None))
                    participant.geo_context = GeoContext(request.form.get('practice-context', None))

            
            
            participant.persist()
            return redirect(url_for('index'))

        except Exception as e:
            log.error(f"Error setting participant fields: {e}")



    # no profile found, needs completion
    from hvp.core.enums import CountryEnum, ProviderTypeEnum, GeoContext, ClinicalField, SubjectType
    return render_template(
        "profile.html",
        user=session.get('user'),
        country_options=CountryEnum,
        subject_types=SubjectType,
        provider_type_options=ProviderTypeEnum,
        field_options=ClinicalField,
        practice_context_options=GeoContext
    )


@application.route('/login')
def login():
    cognito_login_url = (
        f"https://{application.config['COGNITO_DOMAIN']}/login"
        f"?client_id={application.config['CLIENT_ID']}"
        f"&response_type=code"
        f"&scope=openid+email+profile"
        f"&redirect_uri={urllib.parse.quote(application.config['REDIRECT_URI'])}"
    )
    return redirect(cognito_login_url)

@application.route('/logout')
def logout():
    session.clear()
    logout_url = (
        f"https://{application.config['COGNITO_DOMAIN']}/logout"
        f"?client_id={application.config['CLIENT_ID']}"
        f"&logout_uri={application.config['MAIN_URI']}"
    )
    return redirect(logout_url)

@application.route('/callback')
def callback():
    return handle_callback()

@application.route('/about') 
def about():
    return render_template('about.html', user=session.get('user'))


    
def update_survey_status(status: str):
    if 'user' not in session or DUE_SURVEY_ID not in session:
        return

    participant_id = session["user"]["email"]
    survey_id = session.get(DUE_SURVEY_ID)

    if status == "complete":
        metadata = mark_survey_complete(participant_id, survey_id)
        session.pop(DUE_SURVEY_ID, None)
        return metadata

    
@application.route("/survey/start")
@login_required
def survey_start():
    if DUE_SURVEY_ID not in session:
        return redirect(url_for('index'))
    return redirect("/survey/question/0/set/0")


@application.route("/survey/question/<int:question_number>/set/<int:answer_set_index>", methods=["GET", "POST"])
@login_required
def answer_question(question_number, answer_set_index):
    # --- Authentication Check ---
    if 'user' not in session or DUE_SURVEY_ID not in session:
        return redirect(url_for('index'))

    load_survey()
    if not g.survey:
        return redirect(url_for('index'))

    participant_id = session['user']['email']
    survey_id = g.survey.identifier
    questions = g.survey.questions
    total_questions = len(questions)

    # --- End of Survey ---
    if question_number >= total_questions:
        update_survey_status("complete")
        return redirect(url_for('survey_complete'))

    current_question = questions[question_number]
    answer_sets = current_question.answers
    total_answer_sets = len(answer_sets)

    # --- Skip already answered sets safely ---
    while answer_set_index < total_answer_sets and response_exists_in_s3(
        participant_id,
        survey_id,
        current_question.identifier,
        answer_sets[answer_set_index].identifier
    ):
        answer_set_index += 1

    # --- Move to next question if all sets answered ---
    if answer_set_index >= total_answer_sets:
        return redirect(url_for('answer_question', question_number=question_number + 1, answer_set_index=0))

    current_answer_set = answer_sets[answer_set_index]

    # --- Handle submitted answer ---
    if request.method == "POST":
        field_name = f"answer_{current_answer_set.identifier}"
        selected = request.form.get(field_name)
        if selected:
            save_response_to_s3(
                participant_id=participant_id,
                survey_id=survey_id,
                question_id=current_question.identifier,
                answer_set_id=current_answer_set.identifier,
                answer_value=selected
            )
        return redirect(url_for('answer_question', question_number=question_number, answer_set_index=answer_set_index + 1))

    # --- Render the question ---
    return render_template(
        "question.html",
        user=session['user'],
        question=current_question,
        current_answer_set=current_answer_set,
        answer_set_index=answer_set_index,
        total_answer_sets=total_answer_sets,
        question_number=question_number,
        total_questions=total_questions
    )



@application.route("/survey/complete")
def survey_complete():
    return redirect(url_for('index')) 


@application.route("/response/survey/<survey_id>")
@login_required
def view_survey_responses(survey_id):
    from utils.s3 import list_response_keys
    participant_id = session['user']['email']

    try:
        # 1. Download survey object
        s_key = f"surveys/{participant_id}/{survey_id}.json"
        survey_dict = download_survey(s_key)
        if not survey_dict:
            return f"Survey with ID '{survey_id}' not found.", 404

        survey = Survey(**survey_dict)

        # 2. List all response keys in S3 for this participant + survey
        response_prefix = f"responses/{participant_id}/{survey_id}/"
        response_keys = list_response_keys(response_prefix)

        # 3. Download and parse all responses
        question_responses = []
        from hvp.core.response import SurveyResponse, QuestionResponse
        from pathlib import PurePosixPath

        # In your view_survey_responses function
        for key in response_keys:
            path_parts = PurePosixPath(key).parts  # safely handles the key like a path
            if len(path_parts) < 5:
                continue  # Skip malformed keys

            response_data = download_json_from_s3(key, bucket_name=BUCKET_NAME_RESPONSES)
            question_responses.append(
                QuestionResponse(
                    question_identifier=response_data['question_id'],
                    answer_set_identifier=response_data['answer_set_id'],
                    prompt='',
                    response=response_data
                )
            )

        # 4. Create survey response
        survey_response = SurveyResponse(
            survey=survey, 
            responses=question_responses
        )

        # 5. Render result (or return dict for API)
        return render_template(
            'response.html', 
            markdown_text=to_markdown2(survey_response),
            html_text='',
            user=session['user']
        )

    except Exception as e:
        log.exception("Error assembling survey response")
        return f"Internal error: {e}", 500


def to_html_response(sr) -> str:
    """Convert survey response object to styled HTML for rendering."""

    html = f"""
    <div class="card glass">
        <h3 class="card-title">📝 Survey: {sr.survey.identifier}</h3>
    """

    for i, question in enumerate(sr.survey.questions):
        html += f"""
        <div class="card-text" style="margin-top: 2rem;">
            <h4 class="component-title">Question {i+1}: {question.identifier}</h4>
            <div class="instruction-block">
                <p class="instruction"><strong>Instruction:</strong> {question.instruct_human}</p>
            </div>
            <div class="question-block">
                <p class="question-text">{question.text}</p>
            </div>
        """

        for answer_set in question.answers:
            question_response = next(
                (r for r in sr.responses if r.answer_set_identifier == answer_set.identifier),
                None
            )

            if question_response:
                selected_option = next(
                    (o for o in answer_set.options if o.value == question_response.response['answer_value']),
                    None
                )

                if selected_option:
                    answer_html = "<blockquote>"
                    for line in selected_option.text.splitlines():
                        answer_html += f"<p>{line}</p>"
                    answer_html += "</blockquote>"

                    html += f"""
                    <div class="answer-block">
                        <strong>Answer:</strong>
                        {answer_html}
                    </div>
                    """

        html += "<hr /></div>"

    html += "</div>"  # Close outer card

    return html



def to_markdown2(sr) -> str:
        # Convert survey_response to Markdown for rendering in template
        md = f"##### Survey: {sr.survey.identifier}\n\n"

        for i, question in enumerate(sr.survey.questions):
            md += f"### Question {i+1}: {question.identifier}\n"
            md += f"> Instruction: {question.instruct_human}\n\n"
            md += f"{question.text}\n\n"
            for answer_set in question.answers:

                question_response = next(filter(lambda r: r.answer_set_identifier == answer_set.identifier, sr.responses), None)


                if question_response:
                    selected_option = next(filter(lambda o: o.value == question_response.response['answer_value'], answer_set.options), None)
                    
                    block_quote = '\n'.join(f"> {line}" for line in selected_option.text.splitlines())
                    md += f"**Answer:**\n"
                    md += f"{block_quote}\n\n"
                
                md += "--------------\n\n"
        return md
    


if __name__ == '__main__':
    application.run(port=3000, debug=True)

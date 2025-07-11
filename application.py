from flask import Flask, flash, render_template, redirect, session, request, url_for, g, current_app
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
from utils.question_extension import *

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
     handlers=[RichHandler()]
)

log = logging.getLogger(__name__)

p = Console().print

application = Flask(__name__)

TOTAL_QUESTIONS = { 
    "TRIAGE": 200,
    "MANAGEMENT": 8
}

MINIMUM_QUESTIONS_PER_TYPE = {
    "TRIAGE": 4,
    "MANAGEMENT": 6
}


def require_profile_complete(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_email = session.get('user', {}).get('email')
        if not user_email:
            log.warning("No user email found in session")
            return redirect(url_for('login'))

        participant = AppParticipant.load(user_email)
        if not participant:
            log.warning("Participant record not found")
            return redirect(url_for('complete_profile'))
        
        g.participant = participant  # attach to global context for downstream use

        if not participant.has_demographics:
            log.debug("Participant profile incomplete, redirecting to profile form")
            session['participant_id'] = participant.identifier
            return redirect(url_for('complete_profile'))

        return f(*args, **kwargs)
    return decorated_function

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
    pass
    # if request.endpoint in ('logout',):  # or check request.path == '/logout'
    #     return
    
    # log.debug("Loading survey for current session")
    # survey_id = session.get(DUE_SURVEY_ID)
    # if survey_id:
    #     participant_id = session.get('user', {}).get('email', None)
    #     s3_file = f"surveys/{participant_id}/{survey_id}.json"
    #     if s3_file:
    #         survey_dict = download_survey(key=s3_file)
    #         survey = Survey(**survey_dict)
    #         g.survey = survey
    # else:
    #     g.survey = None


def build_question_progress(progress: dict, total_questions: dict, minimum_required: int) -> dict:
    merged = {}
    for qtype in total_questions:
        merged[qtype] = {
            "total": total_questions[qtype],
            "answered": int(progress.get(qtype, 0)),
            "minimum": minimum_required
        }
    return merged


@application.route('/')
@login_required
@require_profile_complete
def index():

    participant = g.participant

    # Define the question types assigned to this participant
    from utils.profile import get_assigned_question_types_with_progress 

    progress_arr = get_assigned_question_types_with_progress(
        participant_id=participant.identifier,
        total_questions_dict=TOTAL_QUESTIONS,
        threshold_for_type_dict=MINIMUM_QUESTIONS_PER_TYPE
    )
    

    log.debug(f"New: Participant progress: {progress_arr}")

    if not progress_arr:
        log.warning(f"No question types assigned for participant: {participant.identifier}")
        return render_template("study_page.html", progress=[], user=session.get('user', None))

    # return progress_dict
    has_due_block = any(item.get("answered", 0) < item.get("minimum", 0) for item in progress_arr)
    return render_template("study_page.html", progress=progress_arr, user=session.get('user', None), has_due_block=has_due_block)



@application.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():

    if request.method == 'POST':
        from hvp.core.enums import SubjectType, ProviderTypeEnum, GeoContext 

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


            # if participant.subject_type == SubjectType.HEALTHCARE_PROVIDER:
                
            # Ensure form returns plain string values
            subject_type_value = request.form.get('subject_type', None)
            provider_type_value = request.form.get('provider_type', None)
            clinical_field_values = request.form.getlist('clinical-field') or None
            geo_context_value = request.form.get('practice-context', None)

            participant.subject_type = SubjectType(subject_type_value)

            if participant.subject_type == SubjectType.HEALTHCARE_PROVIDER:
                if provider_type_value:
                    participant.provider_type = ProviderTypeEnum(provider_type_value)
                if clinical_field_values:
                    participant.clinical_field = clinical_field_values
                if geo_context_value:
                    participant.geo_context = GeoContext(geo_context_value)

            
            participant.persist()
            from utils.profile import assign_question_types
            assign_question_types(participant)


            return redirect(url_for('index'))

        except Exception as e:
            log.error(f"Error setting participant fields: {e}")



    # no profile found, needs completion
    import pycountry
    countries = list(pycountry.countries)
    countries_sorted = sorted([c for c in countries if c.alpha_2 != "US"], key=lambda c: c.name)
    us = next(c for c in countries if c.alpha_2 == "US")
    countries_sorted = [us] + countries_sorted


    from hvp.core.enums import ProviderTypeEnum, GeoContext, SubjectType
    return render_template(
        "profile.html",
        user=session.get('user'),
        country_options=countries_sorted,
        subject_types=SubjectType,
        provider_type_options=ProviderTypeEnum,
        field_options='',
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




@application.route('/survey/start/<question_type>/<cmode>', methods=['GET', 'POST'])
@login_required
@require_profile_complete
def survey_start(question_type, cmode=None):

    session['current_question_type'] = question_type
    participant = g.participant
    # random_question = get_unanswered_questions(participant_id=participant.identifier, question_type=question_type, number_of_questions=1)

    from utils.register import get_participant_registry 
    participant_registry = get_participant_registry(participant_id=participant.identifier)
    
    random_question = get_random_unanswered_question(participant_data=participant_registry, question_type=question_type)

    if not random_question:
        log.warning(f"No unanswered questions found for type '{question_type}' for participant {participant.identifier}")
        return redirect(url_for('index'))

    return redirect(url_for('answer_question', question_id=random_question.identifier, answer_set_index=0, cmode=cmode))



@application.route('/survey/question/<question_id>/set/<answer_set_index>/<cmode>', methods=['GET', 'POST'])
@login_required
@require_profile_complete 
def answer_question(question_id, answer_set_index, cmode=None):

    participant = g.participant

    if request.method == "POST":
        
        form_answerset_id = request.form.get('answer_set_identifier', None)
        form_question_id = request.form.get('question_identifier', None)
        form_question_type = request.form.get('question_type', None)
        form_answerset_index = int(request.form.get('answer_set_index'))
        form_answerset_count = int(request.form.get('answer_set_count'))

        selected_answer = request.form.get('selected_answer', None)
        cmode = request.form.get('cmode')

        # Save flag if submitted
        if request.form.get("flag_question") == "on":
            comment = request.form.get("flag_comment", "").strip()
            save_flag_to_s3(
                participant_id=g.participant.identifier,
                question_type=form_question_type,
                question_id=form_question_id,
                answer_set_id=form_answerset_id,
                comment=comment
            )
        
        if selected_answer:
            logging.debug(f"Saving response for participant {participant.identifier}, question {form_question_id}, answer set {form_answerset_id}, value: {selected_answer}")
            save_response_to_s3(
                participant_id=participant.identifier,
                question_type=form_question_type,
                question_id=form_question_id,
                answer_set_id=form_answerset_id,
                answer_value=selected_answer
            )

            answer_count = increment_question_progress(
                    participant_id=participant.identifier,
                    question_type=form_question_type,
                    question_id=form_question_id
                )
            has_answered_minimum = int(answer_count) >= MINIMUM_QUESTIONS_PER_TYPE[form_question_type]
            print(has_answered_minimum) 
            print(answer_count) 
            print(MINIMUM_QUESTIONS_PER_TYPE[form_question_type])
            print(f'cmode={cmode}, type={type(cmode)}')
            

            retline =  str(has_answered_minimum) + '\n' + str(cmode) + '\n' + str(form_question_type) + '\n' + str(answer_count) + '\n' + str(MINIMUM_QUESTIONS_PER_TYPE[form_question_type]) + '\n' + str(participant.identifier) + '\n' + str(form_question_id) + '\n' + str(form_answerset_id)

            was_last_answer_set = form_answerset_index + 1 >= form_answerset_count

            if was_last_answer_set:
                if has_answered_minimum:
                    if cmode == 'False':
                        flash(f"You have completed answering {form_question_type} questions! You may continue answering more or return to My Study to choose a new category.", "success") 
                        return redirect(url_for('index'))
                    else: 
                        if answer_count < TOTAL_QUESTIONS[form_question_type]:
                            flash(f"{form_question_type} Question #{answer_count+1} ", "success") 
                            return redirect(url_for('survey_start', question_type=form_question_type, cmode=cmode))
                        else:
                            flash(f"You have completed answering all {form_question_type} questions", "success") 
                            return redirect(url_for('index'))
            else:
                # If not the last answer set, redirect to next one
                return redirect(url_for('answer_question', question_id=form_question_id, answer_set_index=form_answerset_index + 1, cmode=cmode))
            
    





    question = get_question_by_id(question_id)
    if not question:
        print(f"Question with ID {question_id} not found.")
        log.error(f"Question with ID {question_id} not found.")
        # raise ValueError(f"Question with ID {question_id} not found.")
        return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
    answer_sets = question.answers
    total_answer_sets = len(answer_sets)

    answer_set_index = int(answer_set_index)

    print(f'in answer_question, question_id={question_id}, answer_set_index={answer_set_index}, cmode={cmode}')

    # --- Check if answer_set_index is valid ---
    if answer_set_index >= total_answer_sets:
        print(f"Invalid answer_set_index {answer_set_index} for question {question_id}. Total sets: {total_answer_sets}")
        # raise ValueError(f"Invalid answer_set_index {answer_set_index} for question {question_id}. Total sets: {total_answer_sets}")
        return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
    # # --- Skip already answered sets safely ---
    while answer_set_index < total_answer_sets:
        try: 
            if not response_exists_in_s3(
                    participant_id=participant.identifier,
                    question_type=question.type,
                    question_id=question.identifier,
                    answer_set_id=answer_sets[answer_set_index].identifier
            ):
                break 
        except Exception as e:
            raise e 
        answer_set_index += 1

    # --- Move to next question if all sets answered ---
    if answer_set_index >= total_answer_sets:
        log.debug(f"All answer sets for question {question_id} answered. Redirecting to survey start.")
        return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
    g.current_question = question 
    current_answer_set = answer_sets[answer_set_index]  
    
    return render_template(
        "question.html",
        user=session['user'],
        question=question,
        current_answer_set=current_answer_set,
        answer_set_index=answer_set_index,
        total_answer_sets=len(answer_sets),
        cmode=cmode
    )

# def answer_question(question_id, answer_set_index, cmode=None): 

#     participant = g.participant
#     question = get_question_by_id(question_id)

#     if not question:
#         log.error(f"Question with ID {question_id} not found.")
#         return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
#     answer_sets = question.answers
#     total_answer_sets = len(answer_sets)

#     answer_set_index = int(answer_set_index)

#     if answer_set_index >= total_answer_sets:
#         return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
#     # --- Skip already answered sets safely ---
#     while answer_set_index < total_answer_sets and response_exists_in_s3(
#         participant_id=participant.identifier,
#         question_id=question.identifier,
#         answer_set_id=answer_sets[answer_set_index].identifier
#     ):
#         answer_set_index += 1

#     # --- Move to next question if all sets answered ---
#     if answer_set_index >= total_answer_sets:
#         return redirect(url_for('survey_start', question_type=session.get('current_question_type', None), cmode=cmode))
    
#     g.current_question = question 
#     current_answer_set = answer_sets[answer_set_index]  

#     if request.method == "POST":
#         field_name = f"answer_{current_answer_set.identifier}"
#         selected = request.form.get(field_name)
        
#         cmode = request.form.get('cmode')
#         print(cmode)

#             # Save flag if submitted
#         if request.form.get("flag_question") == "on":
#             comment = request.form.get("flag_comment", "").strip()
#             save_flag_to_s3(
#                 participant_id=g.participant.identifier,
#                 question_id=question.identifier,
#                 answer_set_id=current_answer_set.identifier,
#                 comment=comment
#             )
        

#         if selected:
#             logging.debug(f"Saving response for participant {participant.identifier}, question {question.identifier}, answer set {current_answer_set.identifier}, value: {selected}")
#             save_response_to_s3(
#                 participant_id=participant.identifier,
#                 question_id=question.identifier,
#                 answer_set_id=current_answer_set.identifier,
#                 answer_value=selected
#             )

#             from utils.question_extension import increment_question_progress 
#             answer_count = increment_question_progress(participant_id=participant.identifier, question_type=question.type)
#             has_answered_minimum = int(answer_count) >= MINIMUM_QUESTIONS_PER_TYPE[question.type]
#             print(has_answered_minimum) 
#             print(answer_count) 
#             print(MINIMUM_QUESTIONS_PER_TYPE[question.type])
#             print(f'cmode={cmode}')


# #             if has_answered_minimum:
# #                 if cmode == False:
# #                     return redirect(url_for('index', user=session['user'])
# # )
# #                 else: 
# #                     return redirect(url_for('answer_question', question_id=question_id, answer_set_index=answer_set_index + 1, cmode=cmode))


#                 # flash(f"You have completed answering {session.get('current_question_type', None)} questions! You may continue answering more or return to My Study to choose a new category.", "success") 
#                 # else:

#         return redirect(url_for('answer_question', question_id=question_id, answer_set_index=answer_set_index + 1, cmode=cmode))
    
#     # --- Render the question ---
#     return render_template(
#         "question2.html",
#         user=session['user'],
#         question=question,
#         current_answer_set=current_answer_set,
#         answer_set_index=answer_set_index,
#         total_answer_sets=len(answer_sets),
#         cmode=cmode
#     )




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

        p(survey_response)


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

                question_response = next(filter(lambda r: r.answer_set_identifier == answer_set.identifier and r.question_identifier == question.identifier, sr.responses), None)


                if question_response:
                    selected_option = next(filter(lambda o: o.value == question_response.response['answer_value'], answer_set.options), None)
                    
                    block_quote = '\n'.join(f"> {line}" for line in selected_option.text.splitlines())
                    md += f"**Answer:**\n"
                    md += f"{block_quote}\n\n"
                
                md += "--------------\n\n"
        return md
    


if __name__ == '__main__':
    application.run(port=3000, debug=True)


  








from flask import Flask, flash, make_response, render_template, redirect, session, request, url_for, g, current_app
from flask import request, redirect
from flask_talisman import Talisman, talisman
from werkzeug.middleware.proxy_fix import ProxyFix
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
from utils.register import get_participant_registry 




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

# Order matters: wrap FIRST
application.wsgi_app = ProxyFix(
    application.wsgi_app,
    x_for=1,          # keep original client IP, optional
    x_host=1,         # trust Host header
    x_proto=1         # <<< trust scheme (http/https)
)


TOTAL_QUESTIONS = { 
    "TRIAGE": 200,
    "MANAGEMENT": 8
}

MINIMUM_QUESTIONS_PER_TYPE = {
    "TRIAGE": 35,
    "MANAGEMENT": 6
}


@application.after_request
def add_no_cache_headers(response):
    if request.endpoint and request.endpoint.startswith(("question")):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0, private"
        )
        response.headers["Pragma"] = "no-cache"        # for older HTTP/1.0 caches
        response.headers["Expires"] = "0"

    return response

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




def nocache(view):
    """Decorator: add no-store headers so the page is not stored in history."""
    def wrapper(*args, **kwargs):
        resp = make_response(view(*args, **kwargs))
        resp.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0")
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    wrapper.__name__ = view.__name__
    return wrapper


@application.template_filter('markdown')
def render_markdown(text):
    return markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br', "attr_list"])

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


@application.route('/contact')
def contact():
    return render_template('about.html', user=session.get('user'))


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
        return render_template("study_page.html", progress=[], user=session.get('user', None), participant=participant)

    # return progress_dict
    has_due_block = any(item.get("answered", 0) < item.get("minimum", 0) for item in progress_arr)
    return render_template("study_page.html", progress=progress_arr, user=session.get('user', None), has_due_block=has_due_block, participant=participant)



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

@application.route('/terms')
def terms_of_service():
    return render_template('tos.html', user=session.get('user'))

@application.route('/privacy-policy')
def privacy_policy():
    return render_template('privacypolicy.html', user=session.get('user'))

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



@application.route('/survey/start/<question_type>/<cmode>', methods=['GET', 'POST'])
@login_required
@require_profile_complete
def survey_start(question_type, cmode=None):

    session['current_question_type'] = question_type
    participant = g.participant

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
            was_last_answer_set = form_answerset_index + 1 >= form_answerset_count

            if was_last_answer_set:
                if has_answered_minimum:
                    if cmode == 'False':
                        # flash(f"You have completed answering {form_question_type} questions! You may continue answering more or return to My Study to choose a new category.", "success") 
                        return redirect(url_for('index'))
                    else: 
                        if answer_count < TOTAL_QUESTIONS[form_question_type]:
                            # flash(f"{form_question_type} Question #{answer_count+1} ", "success") 
                            return redirect(url_for('survey_start', question_type=form_question_type, cmode=cmode))
                        else:
                            # flash(f"You have completed answering all {form_question_type} questions", "success") 
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









@application.route('/demo-questions', methods=['GET'])
def demo_questions():
    from pathlib import Path
    from flask import abort
    # ------------------------------------------------------------------ #
    # 1. Locate & load the JSON file
    # ------------------------------------------------------------------ #
    file_name = request.args.get("file", "demo.json")
    q_idx     = int(request.args.get("index", 0))

    demo_dir  = Path(application.root_path) / "static" / "demo"
    json_path = demo_dir / file_name

    if not json_path.exists():
        abort(404, description=f"Demo file {file_name!r} not found in /static/demo")

    with json_path.open("r", encoding="utf-8") as f:
        try:
            raw_questions = json.load(f)
        except json.JSONDecodeError as e:
            abort(400, description=f"Malformed JSON: {e}")

    if not isinstance(raw_questions, list) or not raw_questions:
        abort(400, description="The JSON must be a non-empty list of questions.")

    if q_idx < 0 or q_idx >= len(raw_questions):
        abort(400, description="Index out of range.")

    # ------------------------------------------------------------------ #
    # 2. Build a Question object (re-use your existing Pydantic class)
    # ------------------------------------------------------------------ #
    try:
        from hvp.core.question import Question                # adjust import path if needed
        demo_question = Question(**raw_questions[q_idx])
    except Exception as e:
        abort(500, description=f"Error instantiating Question model: {e}")


    return render_template(
        "question.html",
        user=session.get("user"),
        question=demo_question,
        current_answer_set=demo_question.answers[0],
        answer_set_index=0,
        total_answer_sets=len(demo_question.answers),
        # these next two don’t matter for a one-off preview
        question_number=0,
        total_questions=len(raw_questions),
        cmode="demo"             # flag so template can hide nav buttons, etc.
    )


@application.route('/view-responses') 
@login_required
@require_profile_complete 
def view_responses(): 

    participant = g.participant 
    #1. List every response object participant stored in S3 
    from utils.s3 import list_response_keys 
    s3_prefix = f"responses/{participant.identifier}/" 
    response_keys = list_response_keys(s3_prefix)

    if not response_keys:
        flash("No survey responses found for this participant.", "info")
        return render_template('responses.html', user=session.get('user'))
    

    responses_json = [] 
    for key in response_keys:
        log.debug(f"Found response key: {key}")
        #2. Download each response object and parse it
        from utils.s3 import download_response
        response_data = download_response(key=key) 
        if response_data:
            responses_json.append(response_data)
    

    questions = { } 
    from utils.question_extension import get_question_by_id 
    for response in responses_json:
        question_id = response.get('question_id')
        if question_id and question_id not in questions:
            question = get_question_by_id(question_id)
            if question:
                questions[question_id] = question
                # return question.model_dump_json()


    

    
    rendering_text = "" 

    from hvp.core.response import QuestionResponse 

    

    from markdown import markdown 
    for i, response in enumerate(responses_json):

        q_id = response.get('question_id') 
        set_id = response.get('answer_set_id') 
        response_value = response.get('answer_value')
        question = questions.get(q_id) 
        answer_set = next(
                (a for a in question.answers if a.identifier == set_id),None)
        selected_response = next((r for r in answer_set.options if r.value == response_value), None)

        rendering_text += f"<p>{i+1}. {question.type}</p>"
        rendering_text += f"<p>Set ID: {set_id}</p>"
        rendering_text += f"<p><strong>Responded: {selected_response.text} (Value:{selected_response.value})</strong></p>"
        rendering_text += markdown(question.text, extensions=["tables"])
        rendering_text += f"<small>Question: {question.identifier}; Set_ID: {set_id}</small>"
        rendering_text += "<hr />"
        

    return render_template('response.html', text=rendering_text)

        

def save_response(participant_id, question_type, question_id, answer_set_id, answer_set_index, answer_set_count, selected_answer, flag_question=None, flag_comment=None):

    try: 
        if flag_question:
            save_flag_to_s3(
                    participant_id=participant_id,
                    question_type=question_type,
                    question_id=question_id,
                    answer_set_id=answer_set_id,
                    comment=flag_comment
                )
        
        resp = save_response_to_s3(
                participant_id=participant_id,
                question_type=question_type,
                question_id=question_id,
                answer_set_id=answer_set_id,
                answer_value=selected_answer
            )
        logging.debug(f'Saving response to S3: {resp}')
        answer_count = increment_question_progress(
                    participant_id=participant_id,
                    question_type=question_type,
                    question_id=question_id
                )
        return answer_count
        
    except Exception as e: 
        raise e 





# application.py  (add near the other routes)
# -------------------------------------------------------------
@application.route('/partial/next-question', methods=["GET", "POST"])
@login_required
@require_profile_complete
def next_question():
    participant = g.participant

    form      = request.form
    args      = request.args

    # -------- 1. Read context ---------------------------------
    question_type = form.get("question_type") or args.get("question_type")
    cmode = form.get('cmode') or args.get('cmode')
    cmode         = str(cmode)               # keep as string for hidden input

    end_qa_session = False 
    question = None
    

    # -------- 2. If POST – store answer -----------------------
    if request.method == "POST":

        form_answerset_id = request.form.get('answer_set_identifier')
        form_question_id = request.form.get('question_identifier')
        form_question_type = request.form.get('question_type')
        form_answerset_index = int(request.form.get('answer_set_index'))
        form_answerset_count = int(request.form.get('answer_set_count'))
        form_flag_question = request.form.get("flag_question", "off") == "on"
        form_flag_comment = request.form.get("flag_comment", "").strip()
        form_assigned_question_types = int(request.form.get('number_of_assigned_question_types'))
        selected_answer = request.form.get('selected_answer')

        cmode = request.form.get('cmode')

        answer_count = save_response(
            participant_id=participant.identifier,
            question_type=form_question_type,
            question_id=form_question_id,
            answer_set_id=form_answerset_id,
            answer_set_index=form_answerset_index,
            selected_answer=selected_answer,
            answer_set_count=form_answerset_count,
            flag_question=form_flag_question,
            flag_comment=form_flag_comment
        )

        has_answered_minimum = int(answer_count) >= MINIMUM_QUESTIONS_PER_TYPE[form_question_type] and int(answer_count) < TOTAL_QUESTIONS[form_question_type]
        completed_question_and_answerset = form_answerset_index + 1 >= form_answerset_count

        if completed_question_and_answerset:
            if has_answered_minimum: 
                if cmode == 'set-mode':
                    # flash(f"You have completed answering {form_question_type} questions! You may continue answering more or return to My Study to choose a new category.", "success") 
                    # redirect to main index 
                    # do not end session if 
                    end_qa_session = False if form_assigned_question_types == 1 else True
                else:
                    # IN CONTINUE SET MODE 
                    if answer_count < TOTAL_QUESTIONS[form_question_type]:
                        # flash(f"{form_question_type} Question #{answer_count+1} ", "success") 
                        # Begin new
                        question = None 
                    else:
                        # flash(f"You have completed answering all {form_question_type} questions", "success") 
                        end_qa_session = True 
        else:
            question = get_question_by_id(form_question_id)
            answer_set_index += 1


    if end_qa_session:
        resp = make_response("")              # empty body
        resp.headers["HX-Redirect"] = url_for("index")
        
        return resp

    if not question:
        participant_registry = get_participant_registry(participant_id=participant.identifier)
        print(participant_registry)
        assigned_questions_types = participant_registry.get('assigned_question_types') 
        

        question = get_random_unanswered_question(participant_data=participant_registry, question_type=question_type)
        total_sets        = len(question.answers)
        answer_set_index = 0 
        current_set       = question.answers[0]
        total_sets        = len(question.answers)
    
    return render_template(
        "_question_partial.html",
        question          = question,
        current_answer_set= current_set,
        answer_set_index  = answer_set_index,
        total_answer_sets = total_sets,
        cmode             = cmode,
        number_of_assigned_question_types = len(assigned_questions_types)
    )

@application.route('/question/<question_type>', methods=["GET"])
@application.route('/question', methods=["POST"])
@login_required
@require_profile_complete
def question(question_type=None):

    if request.method == "GET":
        return render_template('question_shell.html', question_type=question_type, cmode='True', user=session['user'])
    else:
        question_type = request.form.get('question_type') 
        cmode = request.form.get('cmode') 

        if not question_type:
            raise ValueError('Missing question_type in POST')
        return render_template('question_shell.html', question_type=question_type, cmode=cmode, user=session['user'])

    


if __name__ == '__main__':
    application.run(port=3000, debug=True)


  








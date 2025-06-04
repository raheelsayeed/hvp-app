import requests
from flask import session, redirect, url_for, current_app as app
from functools import wraps
from datetime import datetime, timedelta, timezone
import logging
from jose import jwt
from jose.exceptions import JWTError, JWTClaimsError
from .appparticipant import AppParticipant

log = logging.getLogger(__name__)


def tokens_into_session(tokens): 
    session['id_token'] = tokens.get('id_token')
    session['expires_in'] = int(tokens.get('expires_in', 3600))
    session['auth_time'] = datetime.now(timezone.utc).isoformat()
    refresh_token = tokens.get('refresh_token', None) 
    if refresh_token: 
        session["refresh_token"] = tokens.get("refresh_token")


def refresh_tokens():
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return False

    token_url = f"https://{app.config['COGNITO_DOMAIN']}/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": app.config['CLIENT_ID'],
        "refresh_token": refresh_token
    }

    auth = (app.config['CLIENT_ID'], app.config['CLIENT_SECRET'])
    response = requests.post(token_url, data=data, auth=auth)

    if response.status_code == 200:
        tokens = response.json()
        tokens_into_session(tokens)
        log.info("🔁 Token refreshed successfully")
        return True
    else:
        log.warning(f"❌ Token refresh failed: {response.text}")
        session.clear()
        return False


from functools import wraps
from flask import session, redirect, url_for,  render_template
from datetime import datetime, timedelta, timezone
import logging

log = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        
        id_token = session.get('id_token')
        auth_time_str = session.get('auth_time')
        expires_in = session.get('expires_in')

        if not id_token or not auth_time_str or not expires_in:
            log.debug("Missing auth session data. Redirecting to login.")
            return render_template('login.html')
            return redirect(url_for('login'))

        try:
            auth_time = datetime.fromisoformat(auth_time_str)
        except ValueError as e:
            log.debug(f"Invalid auth_time format: {e}. Redirecting to login.")
            return render_template('login.html')
            return redirect(url_for('login'))

        now = datetime.now(timezone.utc)
        expiry_time = auth_time + timedelta(seconds=int(expires_in))

        if now > expiry_time:
            log.debug("Session expired. Attempting to refresh tokens...")
            if not refresh_tokens():
                log.debug("Token refresh failed. Redirecting to login.")
                return render_template('login.html')
                return redirect(url_for('login'))
            else:
                log.debug("Token refresh successful.")

        return f(*args, **kwargs)
    return decorated_function






def verify_token_response(token_response: dict) -> dict:
    

    id_token = token_response.get("id_token")
    access_token = token_response.get("access_token")
    JWKS_URL = f"{app.config['PUBLIC_KEY_URL']}/.well-known/jwks.json"

    if not id_token or not access_token:
        raise ValueError("Both id_token and access_token are required in the response")

    # Step 1: Get public keys
    jwks = requests.get(JWKS_URL).json()["keys"]

    def get_key(token):
        headers = jwt.get_unverified_header(token)
        kid = headers["kid"]
        return next((k for k in jwks if k["kid"] == kid), None)

    def verify_token(token, key, token_type):
        options = {
            "verify_aud": True,
            "verify_iss": True,
            "verify_exp": True,
            "verify_at_hash": token_type == "id_token"
        }

        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=app.config['CLIENT_ID'],
            issuer=app.config['PUBLIC_KEY_URL'],
            access_token=access_token if token_type == "id_token" else None,
            options=options
        )

    try:
        id_key = get_key(id_token)
        if not id_key:
            raise Exception("No matching key for ID token")

        access_key = get_key(access_token)
        if not access_key:
            raise Exception("No matching key for Access token")

        id_claims = verify_token(id_token, id_key, token_type="id_token")
        access_claims = verify_token(access_token, access_key, token_type="access_token")

        return {
            "id_claims": id_claims,
            "access_claims": access_claims
        }

    except JWTClaimsError as ce:
        raise Exception(f"Token claim validation error: {ce}")
    except JWTError as e:
        raise Exception(f"Token verification failed: {e}")
    except Exception as ex:
        raise Exception(f"Unexpected error during token verification: {ex}")
    


def handle_callback():
    from flask import request  # must be inside if using outside app context
    code = request.args.get("code")
    token_url = f"https://{app.config['COGNITO_DOMAIN']}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": app.config['CLIENT_ID'],
        "code": code,
        "redirect_uri": app.config['REDIRECT_URI']
    }

    auth = (app.config['CLIENT_ID'], app.config['CLIENT_SECRET'])
    token_response = requests.post(token_url, data=data, auth=auth)
    tokens = token_response.json()

    try: 
        claims = verify_token_response(tokens)

        tokens_into_session(tokens)

        session["user"] = {
            "email": claims["id_claims"].get("email"),
            "sub": claims["id_claims"].get("sub"),
            "name": claims["id_claims"].get("name"),
        }

        user_data = session.get('user')

        log.debug(user_data)
        full_name = user_data.get("name", None)
        if full_name:
            parts = full_name.strip().split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            first_name = user_data.get("given_name", "") or "Participant"
            last_name = user_data.get("family_name", "") or ""

        AppParticipant.initial_entry(session['user']['email'], first_name, last_name)
        log.info("✅ User session created")
        return redirect(url_for("index"))
    except Exception as e:
        return f"Login failed: {e}", 403
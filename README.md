Human Values Project 
====================

Participant-facing app + website 


##### Setup 

Designed for AWS



##### Notes: 

```
eb setenv SERVER_NAME=dev.hvp.global
export AWS_LOGIN_PROFILE_NAME=<hms-hvp>
export FLASK_ENV=<dev/production>
```


### Sequence flow 

note over User[WebApp]: 1. Enroll via Website: OAuth2/iCloud/Google/X\nComplete form: TODO-1**: [characteristics]

User[WebApp]->Server-Layer: OAuth Credentials

Server-Layer->db-Participant: Create/Persist: Participant-DB

Server-Layer<--db-Participant: id: Participant_1

Server-Layer->db-Questions: Filter Questions for Participant-1

note over Server-Layer,db-Questions: **TODO-2**: Question-Participant match function

db-Questions-->Server-Layer: n Question Items

note over Server-Layer: Assign Participant & Create Survey

Server-Layer->Bucket: Persist survey Survey-Participant-1.json

Server-Layer-->User[WebApp]: "Ready to begin"\nEmail survey-web-app link

note over User[WebApp]: 2. Begin Survey-Session (stateless) [webApp]

User[WebApp]->Bucket: Persist SurveyResponse-Participant-1.json


## Server components

1. Database for participant data 
2. ?? Database for questions ?? Necessary only if we anticipate a huge number 
3. Server-layer (Python)
4. Authentication server ()



### Todo 

- [ ] From-email address for email notifications
- [ ] Welcome email notification
- [ ] handle error if session has survey reference but item was deleted in s3
- [x] Website domain address 
- [x] Main/Index page needed or not (After login, jump straight to the first question)
- [x] Previous browsing
- [x] Previous question editing
- [x] BUG: user_name on Apple sign-in 
- [x] Profile Form selections should be populated from ENUMs
- [x] App-Participant attributes in HVP and then App 
- [x] Replace Question -> Scenario
- [x] Replace AnswerSet -> Decision
- [x] terms and conditions page
- [ ] !!! Check idToken status on load
- [ ] !! downloadable survey_item
- [ ] !! jupyter notebook dataframe of "survey_items" 
- [x] Random assignment check
        - survey/question/<q_id>/set/<q_set_id>/    
- [x] Continue answering
- [x] We have 200 TRIAGE questions 
- [x]We need some stats to show at the end of Surveys 
- [x] Disclaimer (You may wish to decide other decisions, consequence)
- [x] zak concordance measure- link preprint
- [x] Flag Question Feature (Flag question) 
- [x] Gender-Text: Prefer not say, Other
- [x] All Countries
- [x] Dropdownn multiple selections
- [x] Privacy policy and terms of service specific to CDDS

--- DEMO Qs 

- http://study.hvp.global/demo-questions?file=management_v3.json&index=0

--- Fatigue inducing similarity: 
- 9cefe718851b81108eb3b5942662753df6a84b6b318a313bb5c3b4aa2b49ba53
- ec66badafea938081965b2012aa52236954d571ea1639d84d7a125eeea6b8655
- seeing  'acute onset vertigo' too many times 
- Age: 38, Sex: Female, Status: Healthy

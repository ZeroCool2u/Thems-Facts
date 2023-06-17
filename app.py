import logging
import os
import phonenumbers
from dash import Dash, html, dcc, Output, Input, State
from dash.exceptions import PreventUpdate
from datetime import datetime as dt
from google.cloud import firestore
from google.cloud import tasks as gtasks
from google.cloud.exceptions import NotFound
from google.protobuf import timestamp_pb2
from orjson import dumps
from pandas import date_range

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.WARNING)

if not os.getenv('GAE_ENV', '').startswith('standard'):
    os.environ[
        'GOOGLE_APPLICATION_CREDENTIALS'] = r'/home/theo/PycharmProjects/thems_facts/front_end_service/facts-sender-owner.json'


def gcp_support() -> dict:

    try:
        db = firestore.Client()
        api_keys_ref = db.collection(u'api_keys').document(u'gvRhG4XnOHccmty4UoBU')
        doc = api_keys_ref.get()
        api_keys = doc.to_dict()
        logging.info('API Keys successfully retrieved.')
        return api_keys
    except NotFound as e:
        api_keys = {'twilio_sid': 'TWILIO_SID_NOT_FOUND'}
        logging.error(f'The API keys could not be retrieved from Firestore: {str(e)}')
        return api_keys
    except Exception as e:
        api_keys = {'twilio_sid': 'TWILIO_SID_NOT_FOUND'}
        logging.error(f'Firestore client failed to init. The front end will run in local only mode: {str(e)}')
        return api_keys


API_KEYS = gcp_support()

external_css = ["https://fonts.googleapis.com/css?family=VT323&amp;subset=latin-ext"]

app = Dash(__name__, external_stylesheets=external_css)
server = app.server

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-9C1SZ59XE4"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-9C1SZ59XE4');
</script>
        {%metas%}
        <title>Thems Facts</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

app.layout = html.Div(id='app_container', className='container', children=[
    html.Div(className='row', children=[
        html.Div(className='column', style={'textAlign': 'center'}, children=[
            html.H1('Thems Facts'),
            html.Hr(),
            html.H4(
                """Select the kind of information you'd like to have sent to your target or just set it to random. 
                Then give your target a name and a phone number where they can be reached.
                 Now, subtly suggest to your target that someone else has signed them up for facts 
                 and let chaos reign."""),
            html.Br(),
            dcc.Loading(id='loader', type='cube', fullscreen=False, color='#32CD32', children=[
                dcc.Dropdown(id='fact-dropdown',
                             options=[
                                 {'label': 'Random Fact or Quote or GIF', 'value': 'random'},
                                 {'label': 'Random GIF', 'value': '/random_gif'},
                                 {'label': 'Kanye Quote', 'value': '/kanye'},
                                 {'label': 'Cat Fact', 'value': '/cat'},
                                 {'label': 'Design Quote', 'value': '/design'},
                                 {'label': 'Inspirational Quote', 'value': '/inspirational'},
                                 {'label': 'Simpsons Quote', 'value': '/simpsons'},
                                 {'label': 'Ron Swanson Quote', 'value': '/swanson'},
                                 {'label': 'Chuck Norris Facts', 'value': '/norris'},
                                 {'label': 'Embarrassing Trump Quotes', 'value': '/shitty-trump'},
                                 {'label': 'Dad Jokes', 'value': '/dad_joke'}
                             ],
                             value='random'),
                html.Br(),
                dcc.DatePickerRange(id='date-range-picker',
                                    min_date_allowed=dt.now(),
                                    start_date=dt.now()),
                html.Br(),
                html.Br(),
                dcc.Input(id='target-name',
                          type='text',
                          placeholder='Target Name',
                          required=True),
                html.Br(),
                html.Br(),
                dcc.Input(id='target-phone-number',
                          inputMode='tel',
                          type='tel',
                          placeholder='2128675309',
                          required=True,
                          pattern="[0-9]{10}"),
                html.Br(),
                html.Div(id='output-notification'),
                html.Br(),
                html.Button('Send the facts!',
                            id='submit-button')

            ]),
            html.Hr(),
            html.Div(children=[
                html.H2('Unsolicited User Testimonials:'),
                html.H4('''"This isn't what I thought you meant when you said you were building an app. " - Mel'''),
                html.H4('''"What do you mean a billion facts per second?" - Stu'''),
                html.H4('''"Why's it called 'Thems Facts'? Most of these are just quotes." - Katherine'''),
                html.H4('''"I'm blocking this number." - Mark'''),
                html.H4('''"Hey wait, no really, please, you gotta stop." - Mij'''),
                html.H4('''"3 years!?" - Jim'''),
                html.H4('''"Wtf is this you weirdo." - Alex's Sister'''),
                html.H4('''"Am I getting 'Punkd'?!" - Julia''')
            ], style={'textAlign': 'center'})

        ])
    ])
])


def create_fact_task(task: dict, target_phone: str, target_name: str, fact_type: str, send_time: dt, task_queue_size=1,
                     first_task: bool = False) -> dict:
    payload = {'fact_type': fact_type,
               'target_name': target_name,
               'target_phone': target_phone,
               'account_sid': API_KEYS['twilio_sid'],
               'is_first_task': first_task,
               'task_queue_size': task_queue_size}

    # The API expects a payload of type bytes.
    converted_payload = dumps(payload)

    # Add the payload to the request.
    task['app_engine_http_request']['body'] = converted_payload

    # Create Timestamp protobuf.
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromDatetime(send_time)

    # Add the timestamp to the tasks.
    task['schedule_time'] = timestamp

    return task


def schedule_fact_tasks(target_phone: str, target_name: str, fact_type: str, start_dt: dt, end_dt: dt,
                        frequency: str = 'D') -> int:
    tasks = []
    dr = date_range(start=start_dt, end=end_dt, freq=frequency)
    FIRST_FLAG: bool = True
    for d in dr:
        # Construct the request body.
        task = {
            'app_engine_http_request': {  # Specify the type of request.
                'http_method': 'POST',
                'relative_uri': '/send'
            }
        }
        tasks.append(create_fact_task(task, target_phone, target_name, fact_type, send_time=d, task_queue_size=len(dr),
                                      first_task=FIRST_FLAG))
        FIRST_FLAG = False

    # Create a client.
    client = gtasks.CloudTasksClient()

    project = 'facts-sender'
    queue = 'facts-queue'
    location = 'us-east4'
    # Construct the fully qualified queue name.
    parent = client.queue_path(project, location, queue)

    for t in tasks:
        try:
            # Use the client to build and send the task.
            response = client.create_task(parent, t)
            logging.info('Task creation response: ' + str(response.name))

        except Exception as e:
            logging.error('Exception while scheduling task: ' + str(e))

    return len(tasks)


@app.callback(
    Output('output-notification', 'children'),
    [Input('submit-button', 'n_clicks')],
    [State('fact-dropdown', 'value'),
     State('date-range-picker', 'start_date'),
     State('date-range-picker', 'end_date'),
     State('target-name', 'value'),
     State('target-phone-number', 'value')])
def update_output(n_clicks: int, fact_type: str, start_date: dt, end_date: dt, target_name: str,
                  target_phone: str) -> str:
    if n_clicks is None or start_date is None or end_date is None:
        raise PreventUpdate

    if not target_name or not target_phone:
        return 'Yeah, gonna need a name and phone number.'

    try:
        target_phone_number = phonenumbers.parse(target_phone, "US")

    except phonenumbers.NumberParseException as e:
        logging.info(
            f"An invalid phone number was supplied: {target_phone}"
            f" and caused the following exception to be thrown: {str(e)}")
        return f'You supplied {target_phone} as your phone number and we\'re pretty sure that\'s not a valid number.'

    if phonenumbers.is_possible_number(target_phone_number) and phonenumbers.is_valid_number(target_phone_number):
        n_facts = schedule_fact_tasks(target_phone, target_name, fact_type, start_date, end_date)

        return 'Your ' + str(n_facts) + ' facts have been scheduled!'

    else:
        return f'You supplied {target_phone} as your phone number and we\'re pretty sure that\'s not a valid number.'


@app.callback([Output('date-range-picker', 'min_date_allowed'),
               Output('date-range-picker', 'start_date')],
              [Input('submit-button', 'n_clicks')],
              [State('date-range-picker', 'start_date')])
def update_calendar(n_clicks: int, start_date: str) -> (dt, dt):
    if n_clicks is None or start_date is None:
        raise PreventUpdate

    now: dt = dt.now()

    if len(start_date) > 11:
        start_date: dt = dt.strptime(start_date, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        start_date: dt = dt.strptime(start_date, "%Y-%m-%d")
    if start_date <= now:
        return now, now
    else:
        return start_date, start_date

# Uncomment this if running locally.
# if __name__ == '__main__':
#     app.run_server(debug=True)

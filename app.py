import logging
from datetime import datetime as dt

import dash
import dash_core_components as dcc
import dash_html_components as html
import gc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from google.cloud import firestore
from google.cloud import tasks_v2beta3
from google.cloud.exceptions import NotFound
from google.protobuf import timestamp_pb2
from pandas import date_range
from ujson import dumps

try:
    import googleclouddebugger

    googleclouddebugger.enable()
except ImportError as e:
    logging.error('Unable to import stackdriver debugger: ' + str(e))
    pass

db = firestore.Client()
api_keys_ref = db.collection(u'api_keys').document(u'gvRhG4XnOHccmty4UoBU')

try:
    doc = api_keys_ref.get()
    API_KEYS = doc.to_dict()
    logging.info('API Keys successfully retrieved.')
except NotFound as e:
    API_KEYS = {}
    logging.error('The API keys could not be retrieved from Firestore!')

external_css = ["https://fonts.googleapis.com/css?family=VT323&amp;subset=latin-ext"]

app = dash.Dash(__name__, external_css=external_css)
server = app.server

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        <!-- Global site tag (gtag.js) - Google Analytics -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=UA-137904877-1"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', 'UA-137904877-1');
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

app.layout = html.Div(children=[
    html.H1('Thems Facts'),
    html.Br(),
    dcc.Dropdown(id='fact-dropdown',
                 options=[
                     {'label': 'Random Fact or Quote', 'value': 'random'},
                     {'label': 'Kanye Quote', 'value': '/kanye'},
                     {'label': 'Cat Fact', 'value': '/cat'},
                     {'label': 'Design Quote', 'value': '/design'},
                     {'label': 'Inspirational Quote', 'value': '/inspirational'},
                     {'label': 'Simpsons Quote', 'value': '/simpsons'}
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
              inputmode='tel',
              type='tel',
              placeholder='2128675309',
              required=True,
              pattern="[0-9]{10}"),
    html.Br(),
    html.Div(id='output-notification'),
    html.Br(),
    html.Button('Send the facts!',
                id='submit-button')

])


def create_fact_task(task: dict, target_phone: str, target_name: str, fact_type: str, send_time: dt,
                     first_task: bool = False) -> dict:
    payload = {'fact_type': fact_type,
               'target_name': target_name,
               'target_phone': target_phone,
               'account_sid': API_KEYS['twilio_sid'],
               'is_first_task': first_task}

    # The API expects a payload of type bytes.
    converted_payload = dumps(payload).encode()

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
        tasks.append(create_fact_task(task, target_phone, target_name, fact_type, send_time=d, first_task=FIRST_FLAG))
        FIRST_FLAG = False

    # Create a client.
    client = tasks_v2beta3.CloudTasksClient()

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
            logging.warning('Exception while scheduling task: ' + str(e))

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
    if n_clicks == None or start_date == None or end_date == None:
        raise PreventUpdate

    if not target_name or not target_phone:
        return 'Yeah, gonna need a name and phone number.'

    n_facts = schedule_fact_tasks(target_phone, target_name, fact_type, start_date, end_date)

    gc.collect()

    return 'Your ' + str(n_facts) + ' facts have been scheduled!'


@app.callback([Output('date-range-picker', 'min_date_allowed'),
               Output('date-range-picker', 'start_date')],
              [Input('submit-button', 'n_clicks')],
              [State('date-range-picker', 'start_date')])
def update_calendar(n_clicks: int, start_date: str) -> (dt, dt):
    now: dt = dt.now()
    if len(start_date) > 11:
        start_date: dt = dt.strptime(start_date, "%Y-%m-%d %H:%M:%S.%f")
    else:
        start_date: dt = dt.strptime(start_date, "%Y-%m-%d")
    if start_date <= now:
        return now, now
    else:
        return start_date, start_date


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
    app.run_server(debug=False)

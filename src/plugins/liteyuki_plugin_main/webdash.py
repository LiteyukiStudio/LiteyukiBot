import nonebot
import psutil
from dash import Dash, Input, Output, dcc, html
from starlette.middleware.wsgi import WSGIMiddleware

from src.utils.language import Language

app = nonebot.get_app()


def get_system_info():
    cpu_percent = psutil.cpu_percent()
    memory_info = psutil.virtual_memory()
    memory_percent = memory_info.percent
    return {
            "cpu_percent"   : cpu_percent,
            "memory_percent": memory_percent
    }


@app.get("/system_info")
async def system_info():
    return get_system_info()

lang = Language()
dash_app = Dash(__name__)
dash_app.layout = dash_app.layout = html.Div(children=[
    html.H1(children=lang.get("main.monitor.title"), style={
        'textAlign': 'center'
    }),

    dcc.Graph(id='live-update-graph'),
    dcc.Interval(
        id='interval-component',
        interval=1 * 1000,  # in milliseconds
        n_intervals=0
    )
])


@dash_app.callback(Output('live-update-graph', 'figure'),
                   [Input('interval-component', 'n_intervals')])
def update_graph_live(n):
    lang = Language()
    system_inf = get_system_info()
    dash_app.layout = html.Div(children=[
            html.H1(children=lang.get("main.monitor.title"), style={
                    'textAlign': 'center'
            }),

            dcc.Graph(id='live-update-graph'),
            dcc.Interval(
                id='interval-component',
                interval=1 * 1000,  # in milliseconds
                n_intervals=0
            )
    ])
    figure = {
            'data'  : [
                    {
                            'x'   : [lang.get('main.monitor.cpu')],
                            'y'   : [system_inf['cpu_percent']],
                            'type': 'bar',
                            'name': f"{lang.get('main.monitor.cpu')} {lang.get('main.monitor.usage')}"
                    },
                    {
                            'x'   : [lang.get('main.monitor.memory')],
                            'y'   : [system_inf['memory_percent']],
                            'type': 'bar',
                            'name': f"{lang.get('main.monitor.memory')} {lang.get('main.monitor.usage')}"
                    },
            ],
            'layout': {
                    'title': lang.get('main.monitor.description'),
            }
    }
    return figure


app.mount("/", WSGIMiddleware(dash_app.server))

# import nonebot
# import psutil
# from dash import Dash, Input, Output, dcc, html
# from starlette.middleware.wsgi import WSGIMiddleware
#
# from src.utils.language import Language
# from src.utils.tools import convert_size
#
# app = nonebot.get_app()
#
#
# def get_system_info():
#     cpu_percent = psutil.cpu_percent()
#     memory_info = psutil.virtual_memory()
#     memory_percent = memory_info.percent
#     return {
#             "cpu_percent"   : cpu_percent,
#             "memory_percent": memory_percent
#     }
#
#
# @app.get("/system_info")
# async def system_info():
#     return get_system_info()
#
#
# lang = Language()
# dash_app = Dash(__name__)
# dash_app.layout = dash_app.layout = html.Div(children=[
#         html.H1(children=lang.get("main.monitor.title"), style={
#                 'textAlign': 'center'
#         }),
#
#         dcc.Graph(id='live-update-graph'),
#         dcc.Interval(
#             id='interval-component',
#             interval=1 * 1000,  # in milliseconds
#             n_intervals=0
#         )
# ])
#
#
# @dash_app.callback(Output('live-update-graph', 'figure'),
#                    [Input('interval-component', 'n_intervals')])
# def update_graph_live(n):
#     lang = Language()
#     system_inf = get_system_info()
#     dash_app.layout = html.Div(children=[
#             html.H1(children=lang.get("main.monitor.title"), style={
#                     'textAlign': 'center'
#             }),
#
#             dcc.Graph(id='live-update-graph'),
#             dcc.Interval(
#                 id='interval-component',
#                 interval=2 * 1000,  # in milliseconds
#                 n_intervals=0
#             )
#     ])
#     mem = psutil.virtual_memory()
#     cpu_f = psutil.cpu_freq()
#     figure = {
#             'data'  : [
#                     {
#                             'x'   : [f"{cpu_f.current / 1000:.2f}GHz {psutil.cpu_count(logical=False)}c{psutil.cpu_count()}t"],
#                             'y'   : [system_inf['cpu_percent']],
#                             'type': 'bar',
#                             'name': f"{lang.get('main.monitor.cpu')} {lang.get('main.monitor.usage')}"
#
#                     },
#                     {
#                             'x'   : [f"{convert_size(mem.used, add_unit=False)}/{convert_size(mem.total)}({mem.used / mem.total * 100:.2f}%)"],
#                             'y'   : [system_inf['memory_percent']],
#                             'type': 'bar',
#                             'name': f"{lang.get('main.monitor.memory')} {lang.get('main.monitor.usage')}"
#                     },
#             ],
#             'layout': {
#                     'title': lang.get('main.monitor.description'),
#                     # 'xaxis': {
#                     #         'range': [0, 10]
#                     #         },  # 设置x轴的范围
#                     'yaxis': {
#                             'range': [0, 100]
#                     },  # 设置y轴的范围
#             }
#     }
#     return figure
#
#
# app.mount("/", WSGIMiddleware(dash_app.server))

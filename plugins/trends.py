from pytrends.request import TrendReq
from config import *


import plotly.plotly as py
import plotly.graph_objs as go
import plotly

import os
import random
import string

pytrend = TrendReq(GOOGLE_USERNAME, GOOGLE_PASSWORD, custom_useragent='test')
plotly.tools.set_credentials_file(username=PLOTLY_USERNAME, api_key=PLOTLY_API_KEY)


def graph(argument, country=None):
    trend_payload = {'q': argument}
    if country is not None:
        trend_payload = {'q': argument, 'geo': country}

    try:
        trend = pytrend.trend(trend_payload)
    except IndexError:
        return False

    x = []
    y = []
    for value in trend['table']['rows']:
        y += [value['c'][1]['v']]
        x += [value['c'][0]['v']]

    line = go.Scatter(
        x=x,
        y=y,
        name='Trend',
        line=dict(
            color='rgb(205, 12, 24)',
            width=1)
    )

    title = 'Google Trends: ' + trend_payload['q'] + '. Generated by @CompleteGoogleBot'
    layout = dict(title=title,
                  xaxis=dict(title='Date'),
                  yaxis=dict(title='Trend (100% is max peak)'),)

    filename = os.path.dirname(os.path.realpath(__file__)) + "/trend@{x}.png"\
        .format(x=''.join(random.choice(string.ascii_uppercase) for _ in range(9)))
    fig = dict(data=[line], layout=layout)
    py.image.save_as(fig, filename=filename)
    return filename


def process_message(update):
    message = update.message
    chat = update.chat
    usr = update.user
    bot = update.bot

    if usr.state() == 'trends1':
        msg = message.reply(usr.getstr('generating_graph'))
        file = graph(message.text)
        if not file:
            bot.api.call('editMessageText', {
                'chat_id': chat.id, 'message_id': msg.message_id,
                'text': usr.getstr('trends_not_found'), 'parse_mode': 'HTML',
                'reply_markup': '{"inline_keyboard": ['
                                '[{"text": "' + usr.getstr('back_button') + '", "callback_data": "home"}]]}'
            })
            usr.state('home')
            return True

        message.reply_with_photo(file)
        os.remove(file)  # Disk space is sacred
        msg.edit(usr.getstr('generated_graph'))

        usr.state('home')
        return True

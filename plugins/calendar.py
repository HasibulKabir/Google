from apiclient import discovery
import httplib2

from datetime import datetime
from objects import callback
from objects import user as _user

import sqlite3
conn = sqlite3.connect('users.db')
c = conn.cursor()


def build_rfc3339_phrase(datetime_obj):
    datetime_phrase = datetime_obj.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    return datetime_phrase


def login(user):
    credentials = user.credentials()
    http = credentials.authorize(httplib2.Http())
    return discovery.build('calendar', 'v3', http=http)


def formatevents(user, result):
    events = result.get('items', [])

    text = user.getstr('header')
    events_number = 0
    for event in events:
        events_number += 1

        if event['start'].get('date') is not None:
            day = datetime.strptime(event['start'].get('date'), '%Y-%m-%d').strftime('%d/%m/%y')
            date = user.getstr('all_day_time').format(day=day)
        else:
            start = datetime.strptime(event['start'].get('dateTime'), '%Y-%m-%dT%H:%M:%S+%f:00')
            end = datetime.strptime(event['end'].get('dateTime'), '%Y-%m-%dT%H:%M:%S+%f:00')
            date = (
                user.getstr('start_event_time').format(hour=start.strftime('%H:%M'), date=start.strftime('%d/%m/%y')) +
                ' ' + user.getstr('end_event_time').format(hour=end.strftime('%H:%M'), date=end.strftime('%d/%m/%y')))

        location, description = '', ''
        creator = event.get('creator').get('displayName')

        if event.get('location', None) is not None:
            location = '• ' + event.get('location')

        if event.get('description', None) is not None and event.get('description', None) != event.get('summary'):
            description = '\n<i>{description}</i>'.format(description=event.get('description'))

        if event.get('creator').get('self'):
            creator = user.getstr('your_self')

        text += (
            '\n🔸 <b>{title}</b> • {by} {creator} • {date} {location} {description}\n'.format(
                title=event.get('summary', user.getstr('no_title')), by=user.getstr('event_by'), creator=creator,
                date=date, location=location, description=description
            )
        )
        del event  # Temporary fix for dict.get() bug (or feature?)

    if events_number == 0:
        return user.getstr('no_events')

    return text


def getevents(user, elements_range):
    service = login(user)
    command = service.events().list(
        calendarId='primary', timeMin=datetime.utcnow().isoformat() + 'Z',
        maxResults=elements_range[1], singleEvents=True, orderBy='startTime', pageToken=elements_range[0]
    )
    result = command.execute()
    text = formatevents(user, result)
    pagetoken = result.get('nextPageToken', None)

    if elements_range[0] is not None:
        firstpage = '{"text": "' + user.getstr('first_page') + '", "callback_data": "cd@list@first"}'
    else:
        firstpage = ''
    if pagetoken is not None:
        nextpage = '{"text": "' + user.getstr('next_page') + '", "callback_data": "cd@list@' + pagetoken + '"}'
    else:
        nextpage = ''
    if firstpage == '' and nextpage == '':
        br1, br2 = '', ''
    else:
        br1 = '['
        br2 = '], '

    inline_keyboard = '{"inline_keyboard": ' \
                      '[' + br1 + firstpage + (',' if firstpage != '' and nextpage != '' else '') + nextpage \
                      + br2 + '[{"text": "' + user.getstr('add_event_button') + '", "callback_data": "cd@add"}],' +\
                      '[{"text": "' + user.getstr('back_button') + '", "callback_data": "home"}]]}'
    return text, inline_keyboard


def process_callback(bot, chains, update):
    cb = callback.Callback(update)
    user = _user.User(cb.sender)

    if 'cd@' in cb.query:
        if 'cd@list@' in cb.query:
            page = cb.query.replace('cd@list@', '')

            if page == "first":
                text, inline_keyboard = getevents(user, elements_range=[None, 3])
            else:
                text, inline_keyboard = getevents(user, elements_range=[page, 3])

            bot.api.call('editMessageText',
                         {'chat_id': cb.chat.id, 'message_id': cb.message.message_id,
                          'text': text, 'parse_mode': 'HTML',
                          'reply_markup': inline_keyboard
                          })

        if 'cd@add' in cb.query:
            bot.api.call('editMessageText', {
                'chat_id': cb.chat.id, 'message_id': cb.message.message_id, 'parse_mode': 'HTML',
                'text': user.getstr('create_event_header') + user.getstr('create_event_first_step'), 'reply_markup':
                '{"inline_keyboard": [[{"text": "' + user.getstr('back_button') + '", "callback_data": "calendar"}]]}'
            })
            user.state('calendar_create_event_1')


def process_message(update):
    message = update.message
    chat = update.chat
    user = update.user
    bot = update.bot

    if message.text is None:
        if user.state() == 'calendar_create_event_1':
            bot.api.call('sendMessage', {
                'chat_id': chat.id, 'parse_mode': 'HTML',
                'text': user.getstr('create_event_header') + user.getstr('create_event_notext_error'), 'reply_markup':
                '{"inline_keyboard": [[{"text": "' + user.getstr('back_button') + '", "callback_data": "calendar"}]]}'
            })

    if user.state() == 'calendar_create_event_1':
        c.execute('DELETE FROM calendar_create_event WHERE id=?', (user.id,))
        conn.commit()

        if '.' in message.text:
            summary = message.text.split('.')[0].lstrip().rstrip()
            description = message.text.split('.')[1].lstrip().rstrip()
        else:
            summary = message.text.lstrip().rstrip()
            description = None

        c.execute('INSERT INTO calendar_create_event VALUES(?, ?, ?)', (user.id, summary, description,))
        conn.commit()
        user.state('calendar_create_event_2')

        bot.api.call('sendMessage', {
            'chat_id': chat.id, 'parse_mode': 'HTML',
            'text': user.getstr('create_event_header') + user.getstr('create_event_second_step'), 'reply_markup':
                '{"inline_keyboard": [[{"text": "' + user.getstr('back_button') + '", "callback_data": "calendar"}]]}'
        })

    elif user.state() == 'calendar_create_event_2':
        if message.text is None:
            if user.state() == 'calendar_create_event_1':
                bot.api.call('sendMessage', {
                    'chat_id': chat.id, 'parse_mode': 'HTML',
                    'text': user.getstr('create_event_header') + user.getstr('create_event_notext_error'),
                    'reply_markup':
                        '{"inline_keyboard": [[{"text": "' + user.getstr(
                            'back_button') + '", "callback_data": "calendar"}]]}'
                })

        try:
            start = message.text.split('-')[0].lstrip().rstrip()
            end = message.text.split('-')[1].lstrip().rstrip()

            start = build_rfc3339_phrase(datetime.strptime(start, '%H:%M %d/%m/%Y'))
            end = build_rfc3339_phrase(datetime.strptime(end, '%H:%M %d/%m/%Y'))
        except IndexError:
            bot.api.call('sendMessage', {
                'chat_id': chat.id, 'parse_mode': 'HTML',
                'text': user.getstr('create_event_header') + user.getstr('create_event_timeformatting_error'),
                'reply_markup':
                    '{"inline_keyboard": [[{"text": "' + user.getstr(
                        'back_button') + '", "callback_data": "calendar"}]]}'
            })
            return
        except ValueError:
            bot.api.call('sendMessage', {
                'chat_id': chat.id, 'parse_mode': 'HTML',
                'text': user.getstr('create_event_header') + user.getstr('create_event_timeformatting_error'),
                'reply_markup':
                    '{"inline_keyboard": [[{"text": "' + user.getstr(
                        'back_button') + '", "callback_data": "calendar"}]]}'
            })
            return

        c.execute('SELECT * FROM calendar_create_event WHERE id=?', (user.id,))
        row = c.fetchone()
        summary = row[1]
        description = row[2]

        service = login(user)
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start,
            },
            'end': {
                'dateTime': end,
            },
            'reminders': {
                'useDefault': True,
            },
        }
        event = service.events().insert(calendarId='primary', body=event).execute()
        c.execute('DELETE FROM calendar_create_event WHERE id=?', (user.id,))
        conn.commit()

        text = user.getstr('create_event_completed').format(name=summary, url=event.get('htmlLink'),
                                                            description=(
                                                                user.getstr('create_event_completed_description')
                                                                .format(description=description)
                                                                if description is not None else ''))
        message.reply(text)

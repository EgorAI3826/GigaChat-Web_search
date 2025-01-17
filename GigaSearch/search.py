import argparse
import json
import logging
import random
import re
import requests
import sys
import threading
import time
from duckduckgo_search import DDGS
from flask import Flask, render_template, request, jsonify
from urllib.parse import urlparse

APPNAME = 'LAISer'
VERSION = '0.2'

# Конфигурация
BINDING_ADDRESS = '127.0.0.1'
BINDING_PORT = 5000
LMSTUDIO_IP = 'localhost'
LMSTUDIO_PORT = 1234
OLLAMA_BASE_URL = 'http://localhost:11434'
OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'llama2'
API_TO_USE = 'lmstudio'  # Используем LM Studio
SILENT = False
SEARCH_RESULT_COUNT = 5
NEWS_RESULT_COUNT = 3
TRIM_WIKIPEDIA_SUMMARY = True
TRIM_WIKIPEDIA_LINES = 3

def search(search_query: str, num_results_to_return: int) -> list:
    try:
        results = DDGS().text(
            search_query,
            max_results=num_results_to_return
        )
        text_container = []
        for result in results[:num_results_to_return]:
            text = {
                'title': result['title'],
                'href': result['href'],
                'body': result['body']
            }
            text_container.append(text)
            source_links.append(result['href'])
        return text_container
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []

def news(search_query: str, num_results_to_return: int) -> list:
    try:
        results = DDGS().news(
            search_query,
            max_results=num_results_to_return
        )
        news_container = []
        for result in results[:num_results_to_return]:
            news = {
                'title': result['title'],
                'url': result['url'],
                'body': result['body'],
                'source': result['source']
            }
            news_container.append(news)
            source_links.append(result['url'])
        return news_container
    except Exception as e:
        print(f"Ошибка при получении новостей: {e}")
        return []

def _wikipedia_summary(page_title: str) -> list:
    url = f"https://en.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&exintro=&explaintext=&redirects=1&titles={page_title}"
    response = requests.get(url)
    data = response.json()
    pages = data.get('query', {}).get('pages', {})
    if pages:
        page = next(iter(pages.values()))
        if 'extract' in page:
            text = page['extract']
            if TRIM_WIKIPEDIA_SUMMARY:
                sentences = text.split('.')
                trimmed_text = '. '.join(sentences[:TRIM_WIKIPEDIA_LINES]) + '.'
                return [{'summary': trimmed_text}]
            else:
                return [{'summary': text}]
    return [{'summary': 'Нет доступного резюме.'}]

def wikipedia(search_arg) -> str:
    def trim_url(url):
        parsed_url = urlparse(url)
        path = parsed_url.path
        last_part = path.rsplit('/', 1)[-1]
        return last_part
    search_result = search(f"site:wikipedia.org {search_arg}", 1)
    if search_result:
        source_links.append(search_result[0]['href'])
        wiki_page_title = trim_url(search_result[0]['href'])
        summary = _wikipedia_summary(wiki_page_title)
        return summary
    return [{'summary': 'Нет доступного резюме из Википедии.'}]

def wait_between_queries(timeout_duration=1.0):
    time.sleep(timeout_duration)

def perform_searches(search_query: str) -> list:
    print("Получение резюме из Википедии...") if not SILENT else None
    wikipedia_summary = wikipedia(search_query)
    wikipedia_summary = format_llama_request(wikipedia_summary, "wikipedia")
    wait_between_queries()
    print("Получение результатов поиска...") if not SILENT else None
    search_result = search(search_query, SEARCH_RESULT_COUNT)
    search_result = format_llama_request(search_result, "search")
    wait_between_queries()
    print("Получение новостей...") if not SILENT else None
    news_result = news(search_query, NEWS_RESULT_COUNT)
    news_result = format_llama_request(news_result, "news")
    wait_between_queries()
    search_results = {
        'wikipedia_summary': wikipedia_summary,
        'search_result': search_result,
        'news_result': news_result
    }
    return search_results

def _is_llama_online() -> bool:
    try:
        if API_TO_USE == 'ollama':
            response = requests.get(OLLAMA_BASE_URL)
            if response.status_code == 200 and response.text == 'Ollama is running':
                return True
        elif API_TO_USE == 'lmstudio':
            response = requests.get(f"http://{LMSTUDIO_IP}:{LMSTUDIO_PORT}/health")
            if response.status_code == 200:
                return True
    except Exception as e:
        print(f"Ошибка при подключении к API: {e}")
    return False

def feed_the_llama(query: str) -> str:
    if API_TO_USE == 'ollama':
        url = OLLAMA_URL
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": OLLAMA_MODEL,
            "prompt": query,
            "stream": False
        }
    elif API_TO_USE == 'lmstudio':
        url = f"http://{LMSTUDIO_IP}:{LMSTUDIO_PORT}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": "ai-sage/gigachat-20b-a3b-instruct",
            "messages": [
                {"role": "system", "content": "Ты помощник для поиска в интернете."},
                {"role": "user", "content": query}
            ],
            "temperature": 0.7,
            "max_tokens": -1,
            "stream": False
        }
    else:
        return {
            "success": False,
            "content": "Неверный тип API."
        }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            response_json = response.json()
            if API_TO_USE == 'ollama':
                return {
                    "success": True,
                    "content": response_json['response']
                }
            elif API_TO_USE == 'lmstudio':
                return {
                    "success": True,
                    "content": response_json['choices'][0]['message']['content']
                }
        else:
            error_msg = f"Ошибка: {response.status_code}\n{response.text}"
            print(error_msg)
            return {
                "success": False,
                "content": error_msg
            }
    except Exception as e:
        error_msg = f"Ошибка при выполнении запроса: {e}"
        print(error_msg)
        return {
            "success": False,
            "content": error_msg
        }

def format_llama_request(data: list, data_source: str) -> str:
    if data_source == "search":
        search_result = "Результаты поиска в интернете:\n```\n"
        for entry in data:
            title = entry['title']
            url = entry['href']
            meta = entry['body']
            search_result = f"{search_result}Заголовок страницы: {title}\n"
            search_result = f"{search_result}URL: {url}\n"
            search_result = f"{search_result}Мета-описание: {meta}\n"
            search_result = f"{search_result}\n"
        search_result = f"{search_result}```\n"
        return search_result
    elif data_source ==  "news":
        news_result = "Результаты поиска новостей:\n```\n"
        for entry in data:
            title = entry['title']
            url = entry['url']
            meta = entry['body']
            source = entry['source']
            news_result = f"{news_result}Заголовок страницы: {title}\n"
            news_result = f"{news_result}URL: {url}\n"
            news_result = f"{news_result}Мета-описание: {meta}\n"
            news_result = f"{news_result}Источник новости: {source}\n"
            news_result = f"{news_result}\n"
        news_result = f"{news_result}```\n"
        return news_result
    elif data_source ==  "wikipedia":
        wikipedia_summary = "Википедия:\n```\n"
        summary_data = data[0]['summary']
        wikipedia_summary = f"{wikipedia_summary}{summary_data}\n"
        wikipedia_summary = f"{wikipedia_summary}```\n"
        return wikipedia_summary
    elif data_source ==  "reddit":
        for x in data:
            dictionary = x
            if 'reply' in dictionary:
                dict_reply = dictionary['reply']
                print(f"Ответ:\n{dict_reply}\n")
            if 'op' in dictionary:
                dict_op = dictionary['op']
                print(f"Оригинальный пост:\n{dict_op}\n")
    else:
        print("Ошибка: неверный источник данных")

def format_sources(collected_source_links: list) -> str:
    global source_links
    collected_source_links = list(dict.fromkeys(collected_source_links))
    if SEARCH_TYPE == "web":
        sources = "<ul id='sources' class='sources'>\n"
        for link in collected_source_links:
            constructed_link = f"<li class='source-item'><a href='{link}' target='_blank' class='source-link'>{link}</a></li>\n"
            sources = f"{sources} {constructed_link}"
        sources = f"{sources} </ul>"
        source_links = []
        return sources
    if SEARCH_TYPE == "cli":
        sources = ""
        for link in collected_source_links:
            link = f"{link} \n"
            sources = f"{sources} {link}"
        source_links= []
        return sources

def remove_incomplete_sentence(input_text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', input_text.strip())
    if len(sentences) > 0 and not re.search(r'[.!?]$', sentences[-1]):
        del sentences[-1]
    result = ' '.join(sentences)
    return result

def process_search_query(search_query: str) -> str:
    search_answers = perform_searches(search_query)
    wikipedia_summary = search_answers.get('wikipedia_summary', "")
    search_result = search_answers.get('search_result', "")
    news_result = search_answers.get('news_result', "")
    search_data = f"{wikipedia_summary}\n{search_result}\n{news_result}\n"
    return search_data

def generate_llamatize_text(search_query: str, search_data: str) -> str:
    llamatize = (
        f"Я выполнил поиск в интернете по запросу `{search_query}`.\n"
        f"Сформулируй ответ на основе моих результатов поиска:\n\n"
        f"{search_data}\n"
        f"Кроме того, ответь на мой вопрос "
        f"`{search_query}` "
        f"напрямую, не учитывая предоставленную мной информацию. "
        f"Наконец, предоставь резюме, которое учитывает оба твоих ответа.\n"
    )
    return llamatize

def process_and_display_results(search_query: str) -> str:
    if _is_llama_online():
        search_data = process_search_query(search_query)
        llamatize = generate_llamatize_text(search_query, search_data)
        print("Кормление ламы... ^°π°^") if not SILENT else None
        answer = feed_the_llama(llamatize)
        if answer["success"] == False:
            return answer["content"]
        else:
            answer = remove_incomplete_sentence(answer["content"])
            return answer
    else:
        error_msg = (
            f"Сервер {API_TO_USE} выключен или его статус не 'ok'.\n"
            f"Пожалуйста, проверьте настройки {API_TO_USE}.\n"
        )
        print(error_msg)
        return error_msg

def web_input(search_query: str) -> str:
    answer = process_and_display_results(search_query)
    sources = format_sources(source_links)
    answer_content = (
        "<div id='answer-response'>"
        f"{answer}"
        "</div>\n"
        f"{sources}"
    )
    print("Возвращаю результат...")
    return answer_content

def web_server() -> None:
    print(f"Запуск сервера по адресу: http://{BINDING_ADDRESS}:{BINDING_PORT}")
    app = Flask(__name__)
    app.name = f"{APPNAME} v{VERSION}"
    @app.route('/', methods=['GET', 'POST'])
    def index():
        return render_template('index.html')
    @app.route('/search', methods=['POST'])
    def web_search():
        start_time = time.time()
        question = request.form['input_text']
        print(f"━━━━━━━━┫ Получен веб-запрос: {question}")
        if lock.locked():
            error_msg = "Извините, я могу обрабатывать только один запрос за раз и сейчас занят."
            return jsonify({'result': error_msg})
        with lock:
            answer = web_input(question)
        end_time = time.time()
        print(f"Завершено за {end_time - start_time:.2f} секунд.")
        return jsonify({'result': answer})
    app.run(host=BINDING_ADDRESS, port=BINDING_PORT)

def cli(search_query: str) -> None:
    answer = process_and_display_results(search_query)
    print("━━━━━━━━┫ ОТВЕТ") if not SILENT else None
    print(answer)
    sources = format_sources(source_links)
    print("\nИСТОЧНИКИ:")
    print(sources)

def arguments() -> str:
    parser = argparse.ArgumentParser(description=f"{APPNAME} v{VERSION} - Локальный поиск с ИИ")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--query', '-q', type=str, help='Запрос для поиска')
    group.add_argument('--server', '-s', action='store_true', help='Подключиться к серверу')
    args = parser.parse_args()
    server = False
    if args.query:
        query = args.query
        return query
    elif args.server:
        return False
    else:
        parser.error("Необходимо указать либо --query, либо --server.")

if __name__ == "__main__":
    get_arguments = arguments()
    lock = threading.Lock()
    global SEARCH_TYPE
    SEARCH_TYPE = ""
    global source_links
    source_links = []
    global results
    results = ""
    print(f"Используется {API_TO_USE}") if not SILENT else None
    if not get_arguments:
        SEARCH_TYPE = "web"
        web_server()
    else:
        SEARCH_TYPE = "cli"
        search_query = get_arguments
        if not search_query:
            sys.exit("Введите поисковый запрос в кавычках.")
        else:
            start_time = time.time()
            cli(search_query)
            source_links = []
            end_time = time.time()
            print(f"Завершено за {end_time - start_time:.2f} секунд.") if not SILENT else None
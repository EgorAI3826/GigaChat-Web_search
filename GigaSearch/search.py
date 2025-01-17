import argparse
import configparser
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
    return [{'summary': 'No summary available.'}]

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
    return [{'summary': 'No Wikipedia summary available.'}]

def wait_between_queries(timeout_duration=1.0):
    time.sleep(timeout_duration)

def perform_searches(search_query: str) -> list:
    print("Getting Wikipedia summary...") if not SILENT else None
    wikipedia_summary = wikipedia(search_query)
    wikipedia_summary = format_llama_request(wikipedia_summary, "wikipedia")
    wait_between_queries()
    print("Getting search results...") if not SILENT else None
    search_result = search(search_query, SEARCH_RESULT_COUNT)
    search_result = format_llama_request(search_result, "search")
    wait_between_queries()
    print("Getting news results...") if not SILENT else None
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
        elif API_TO_USE == 'llama.cpp':
            response = requests.get(f"http://{LLAMA_IP}:{LLAMA_PORT}/health")
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
    elif API_TO_USE == 'llama.cpp':
        url = f"http://{LLAMA_IP}:{LLAMA_PORT}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": "ai-sage/gigachat-20b-a3b-instruct",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": query}
            ],
            "temperature": 0.7,
            "max_tokens": -1,
            "stream": False
        }
    else:
        return {
            "success": False,
            "content": "Invalid API type."
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
            elif API_TO_USE == 'llama.cpp':
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
        search_result = "Web search results:\n```\n"
        for entry in data:
            title = entry['title']
            url = entry['href']
            meta = entry['body']
            search_result = f"{search_result}Page title: {title}\n"
            search_result = f"{search_result}URL: {url}\n"
            search_result = f"{search_result}Page meta: {meta}\n"
            search_result = f"{search_result}\n"
        search_result = f"{search_result}```\n"
        return search_result
    elif data_source ==  "news":
        news_result = "News search results:\n```\n"
        for entry in data:
            title = entry['title']
            url = entry['url']
            meta = entry['body']
            source = entry['source']
            news_result = f"{news_result}Page title: {title}\n"
            news_result = f"{news_result}URL: {url}\n"
            news_result = f"{news_result}Page meta: {meta}\n"
            news_result = f"{news_result}News source: {source}\n"
            news_result = f"{news_result}\n"
        news_result = f"{news_result}```\n"
        return news_result
    elif data_source ==  "wikipedia":
        wikipedia_summary = "Wikipedia:\n```\n"
        summary_data = data[0]['summary']
        wikipedia_summary = f"{wikipedia_summary}{summary_data}\n"
        wikipedia_summary = f"{wikipedia_summary}```\n"
        return wikipedia_summary
    elif data_source ==  "reddit":
        for x in data:
            dictionary = x
            if 'reply' in dictionary:
                dict_reply = dictionary['reply']
                print(f"Reply:\n{dict_reply}\n")
            if 'op' in dictionary:
                dict_op = dictionary['op']
                print(f"Original post:\n{dict_op}\n")
    else:
        print("Error: invalid data source")

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
        f"I performed a web search for `{search_query}`.\n"
        f"Formulate a response based upon my search results:\n\n"
        f"{search_data}\n"
        f"In addition, separately answer my question of "
        f"`{search_query}` "
        f"directly without considering the information I provided "
        f"previously. Finally, "
        f"provide a summary which considers both of your answers.\n"
    )
    return llamatize

def process_and_display_results(search_query: str) -> str:
    if _is_llama_online():
        search_data = process_search_query(search_query)
        llamatize = generate_llamatize_text(search_query, search_data)
        print("Feeding the llama... ^°π°^") if not SILENT else None
        answer = feed_the_llama(llamatize)
        if answer["success"] == False:
            return answer["content"]
        else:
            answer = remove_incomplete_sentence(answer["content"])
            return answer
    else:
        error_msg = (
            f"{API_TO_USE} server is offline or status is not 'ok'.\n"
            f"Please check your {API_TO_USE} settings.\n"
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
    print("Returning result...")
    return answer_content

def web_server() -> None:
    print(f"Starting server at: http://{BINDING_ADDRESS}:{BINDING_PORT}")
    app = Flask(__name__)
    app.name = f"{APPNAME} v{VERSION}"
    @app.route('/', methods=['GET', 'POST'])
    def index():
        return render_template('index.html')
    @app.route('/search', methods=['POST'])
    def web_search():
        start_time = time.time()
        question = request.form['input_text']
        print(f"━━━━━━━━┫ Received web request: {question}")
        if lock.locked():
            error_msg = "Sorry, I can only handle one request at a time and I'm currently busy."
            return jsonify({'result': error_msg})
        with lock:
            answer = web_input(question)
        end_time = time.time()
        print(f"Completed in {end_time - start_time:.2f} seconds.")
        return jsonify({'result': answer})
    app.run(host=BINDING_ADDRESS, port=BINDING_PORT)

def cli(search_query: str) -> None:
    answer = process_and_display_results(search_query)
    print("━━━━━━━━┫ ANSWER") if not SILENT else None
    print(answer)
    sources = format_sources(source_links)
    print("\nSOURCES:")
    print(sources)

def load_config() -> None:
    parser = configparser.ConfigParser()
    parser.read('settings.ini')
    global BINDING_ADDRESS
    global BINDING_PORT
    global LLAMA_IP
    global LLAMA_PORT
    global OLLAMA_BASE_URL
    global OLLAMA_URL
    global OLLAMA_MODEL
    global API_TO_USE
    global SILENT
    global SEARCH_RESULT_COUNT
    global NEWS_RESULT_COUNT
    global TRIM_WIKIPEDIA_SUMMARY
    global TRIM_WIKIPEDIA_LINES
    BINDING_ADDRESS = parser.get('laiser', 'BINDING_ADDRESS')
    BINDING_PORT = parser.get('laiser', 'BINDING_PORT')
    LLAMA_IP = parser.get('llamaCPP', 'LLAMA_IP')
    LLAMA_PORT = parser.get('llamaCPP', 'LLAMA_PORT')
    OLLAMA_BASE_URL = parser.get('ollama', 'OLLAMA_BASE_URL')
    OLLAMA_URL = parser.get('ollama', 'OLLAMA_URL')
    OLLAMA_MODEL = parser.get('ollama', 'OLLAMA_MODEL')
    API_TO_USE = parser.get('default_API', 'API_TO_USE')
    SILENT = parser.getboolean('status_messages', 'silent')
    SEARCH_RESULT_COUNT = parser.getint('advanced', 'SEARCH_RESULT_COUNT')
    NEWS_RESULT_COUNT = parser.getint('advanced', 'NEWS_RESULT_COUNT')
    TRIM_WIKIPEDIA_SUMMARY = parser.getboolean('advanced', 'TRIM_WIKIPEDIA_SUMMARY')
    TRIM_WIKIPEDIA_LINES = parser.getint('advanced', 'TRIM_WIKIPEDIA_LINES')

def arguments() -> str:
    parser = argparse.ArgumentParser(description=f"{APPNAME} v{VERSION} - Local AI Search")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--query', '-q', type=str, help='The query to search for')
    group.add_argument('--server', '-s', action='store_true', help='Connect to the server')
    args = parser.parse_args()
    server = False
    if args.query:
        query = args.query
        return query
    elif args.server:
        return False
    else:
        parser.error("Either --query or --server must be specified.")

if __name__ == "__main__":
    get_arguments = arguments()
    load_config()
    lock = threading.Lock()
    global SEARCH_TYPE
    SEARCH_TYPE = ""
    global source_links
    source_links = []
    global results
    results = ""
    print(f"Using {API_TO_USE}") if not SILENT else None
    if not get_arguments:
        SEARCH_TYPE = "web"
        web_server()
    else:
        SEARCH_TYPE = "cli"
        search_query = get_arguments
        if not search_query:
            sys.exit("Enter a search query enclosed in quotes.")
        else:
            start_time = time.time()
            cli(search_query)
            source_links = []
            end_time = time.time()
            print(f"Completed in {end_time - start_time:.2f} seconds.") if not SILENT else None